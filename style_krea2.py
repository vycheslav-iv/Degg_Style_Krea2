"""Degg Krea2 style nodes: reference-image style via the Qwen3-VL vision path.

Two nodes:
  * DeggKrea2StyleReference — style CONDITIONING only (text-to-image).
  * DeggKrea2StyleFusion    — style CONDITIONING plus a VAE-encoded target
    image as the starting latent (image-to-image style transfer).

The reference image is not injected as tokens into the diffusion model. It is
described by the Krea2 text encoder (Qwen3-VL) and the description becomes part
of the positive conditioning. That is why the effect is semantic, not a
mathematical style adapter, and why KSampler denoise stays in charge of how
much structure survives.

Python is the English source of truth. Russian labels and tooltips live in
locales/ru/nodeDefs.json and never inside this file.
"""

from __future__ import annotations

import math


STYLE_VALUES = ("light", "balanced", "strong")

STYLE_INSTRUCTIONS = {
    "light": (
        "Use the attached reference image as a subtle style guide. Borrow only the broad color palette, "
        "surface texture, lighting mood, and visual rhythm. Do not copy the depicted subject."
    ),
    "balanced": (
        "Use the attached reference image as a style guide. Transfer its visual language, color palette, "
        "material texture, brushwork, lighting, composition rhythm, and overall mood. Do not copy the "
        "depicted subject unless the target prompt asks for it."
    ),
    "strong": (
        "Use the attached reference image as a strong style guide. Strongly adopt its visual language, "
        "color palette, material texture, brushwork, lighting, composition rhythm, and overall mood, while "
        "keeping the target prompt as the subject and scene."
    ),
}

FUSION_CLAUSE = (
    "Keep the target image latent as the source of subject, spatial structure, pose, and composition; "
    "use the attached reference image only as the style guide."
)

FALLBACK_VAE_RATIO = 8


def _normalize_strength(value, default: str = "balanced") -> str:
    """Return a protocol value that exists in STYLE_INSTRUCTIONS."""
    if value in STYLE_INSTRUCTIONS:
        return value
    if default in STYLE_INSTRUCTIONS:
        return default
    return "balanced"


def _build_style_text(prompt, style_strength="light", custom_instruction="", fusion=False):
    """Preset (or custom) instruction + target prompt (+ fusion clause)."""
    instruction = (custom_instruction or "").strip()
    if not instruction:
        instruction = STYLE_INSTRUCTIONS[_normalize_strength(style_strength)]
    if fusion:
        instruction = f"{instruction} {FUSION_CLAUSE}"
    return f"{instruction}\n\nTarget prompt: {prompt}"


def _vision_target_size(width: int, height: int, vision_resolution: int):
    """Scale a frame so its area equals vision_resolution^2, keeping its ratio."""
    total_pixels = max(1, int(vision_resolution) * int(vision_resolution))
    source_pixels = max(1, int(width) * int(height))
    scale_by = math.sqrt(total_pixels / source_pixels)
    target_w = max(1, int(round(int(width) * scale_by)))
    target_h = max(1, int(round(int(height) * scale_by)))
    return target_w, target_h


def _resize_reference_for_vision(style_image, vision_resolution):
    """BCHW-ish resize of the reference, back to HWC with three channels."""
    samples = style_image.movedim(-1, 1)
    width, height = _vision_target_size(samples.shape[3], samples.shape[2], vision_resolution)
    try:
        import comfy.utils

        samples = comfy.utils.common_upscale(samples, width, height, "area", "disabled")
    except ModuleNotFoundError:
        import torch.nn.functional as F

        samples = F.interpolate(samples, size=(height, width), mode="area")
    return samples.movedim(1, -1)[:, :, :, :3]


def _encode_style_conditioning(
    clip,
    style_image,
    prompt,
    style_strength="light",
    vision_resolution=384,
    custom_instruction="",
    fusion=False,
):
    image_for_clip = _resize_reference_for_vision(style_image, vision_resolution)
    text = _build_style_text(prompt, style_strength, custom_instruction, fusion=fusion)
    tokens = clip.tokenize(text, images=[image_for_clip])
    return clip.encode_from_tokens_scheduled(tokens)


def _vae_downscale_ratio(vae) -> int:
    """Spatial compression of the VAE, with a safe fallback for Qwen/Krea2."""
    if hasattr(vae, "spacial_compression_encode"):
        try:
            return max(1, int(vae.spacial_compression_encode()))
        except Exception:
            pass
    return FALLBACK_VAE_RATIO


def _crop_box(height: int, width: int, ratio: int):
    """Centre crop box (y0, y1, x0, x1) snapped to the VAE ratio."""
    ratio = max(1, int(ratio))
    cropped_h = (int(height) // ratio) * ratio
    cropped_w = (int(width) // ratio) * ratio
    if cropped_h <= 0 or cropped_w <= 0:
        raise ValueError(
            f"target_image is too small for VAE downscale ratio {ratio}: "
            f"got {int(width)}x{int(height)}, need at least {ratio}x{ratio}"
        )
    y0 = (int(height) - cropped_h) // 2
    x0 = (int(width) - cropped_w) // 2
    return y0, y0 + cropped_h, x0, x0 + cropped_w


def _crop_image_for_vae(target_image, vae):
    """Centre crop the HWC target to a multiple of the VAE ratio."""
    y0, y1, x0, x1 = _crop_box(target_image.shape[1], target_image.shape[2], _vae_downscale_ratio(vae))
    return target_image[:, y0:y1, x0:x1, :3]


class DeggKrea2StyleReference:
    """Style-only conditioning for Krea2 text-to-image."""

    DESCRIPTION = (
        "Builds a CONDITIONING from a reference image through the Krea2/Qwen3-VL vision path. "
        "It does not patch the diffusion model and does not inject latent tokens: the reference is "
        "described semantically, so use it for text-to-image with Krea2."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "clip": ("CLIP", {
                    "tooltip": "Text encoder loaded with type krea2 (Qwen3-VL). The node calls clip.tokenize(..., images=[...]) so the reference reaches the vision path.",
                }),
                "style_image": ("IMAGE", {
                    "tooltip": "Reference image used ONLY for style: palette, materials, brushwork, light and overall visual language. The depicted subject is not copied unless the prompt asks for it.",
                }),
                "prompt": ("STRING", {
                    "tooltip": "Describe the image you want. The reference already speaks for style, so describe the subject and the scene instead of repeating the reference.",
                    "multiline": True,
                    "dynamic_prompts": True,
                }),
                "style_strength": (list(STYLE_VALUES), {
                    "tooltip": "How assertively the reference should steer the result. This is wording, not a sampler value: light is conservative, strong is assertive.",
                    "default": "light",
                }),
                "vision_resolution": ("INT", {
                    "tooltip": "The reference is scaled to roughly this many pixels per side before it reaches Qwen3-VL. 384 is stable, 512 keeps more detail but costs more time.",
                    "default": 384,
                    "min": 128,
                    "max": 1024,
                    "step": 32,
                }),
            },
            "optional": {
                "custom_instruction": ("STRING", {
                    "tooltip": "Optional. Leave empty to use the strength preset. When filled it replaces the preset instruction; the target prompt is still appended.",
                    "default": "",
                    "multiline": True,
                }),
            },
        }

    RETURN_TYPES = ("CONDITIONING",)
    RETURN_NAMES = ("conditioning",)
    OUTPUT_TOOLTIPS = (
        "Positive conditioning with the reference described by Krea2/Qwen3-VL.",
    )
    FUNCTION = "encode"
    CATEGORY = "My_custom_nodes/Degg_Style_Krea2"

    def encode(
        self,
        clip,
        style_image,
        prompt,
        style_strength="light",
        vision_resolution=384,
        custom_instruction="",
    ):
        conditioning = _encode_style_conditioning(
            clip,
            style_image,
            prompt,
            style_strength,
            vision_resolution,
            custom_instruction,
        )
        return (conditioning,)


class DeggKrea2StyleFusion:
    """Style conditioning plus a VAE-encoded target image as the start latent."""

    DESCRIPTION = (
        "Adds the target image as a VAE-encoded starting latent on top of the semantic style "
        "conditioning. With a low KSampler denoise the subject and composition stay, while the style "
        "of the reference image is transferred."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "clip": ("CLIP", {
                    "tooltip": "Text encoder loaded with type krea2 (Qwen3-VL). Only the style reference image enters clip.tokenize(..., images=[...]).",
                }),
                "vae": ("VAE", {
                    "tooltip": "Krea2/Qwen image VAE. It encodes the target image into the starting latent for KSampler.",
                }),
                "style_image": ("IMAGE", {
                    "tooltip": "Reference image used ONLY for style: palette, materials, brushwork, light and overall visual language. It enters the Qwen3-VL vision path.",
                }),
                "target_image": ("IMAGE", {
                    "tooltip": "Image that supplies subject, pose and composition. It is encoded by the VAE into the starting latent and never enters the CLIP image path.",
                }),
                "prompt": ("STRING", {
                    "tooltip": "Describe the image you want. Describe the target subject and result; do not repeat the reference image subject.",
                    "multiline": True,
                    "dynamic_prompts": True,
                }),
                "style_strength": (list(STYLE_VALUES), {
                    "tooltip": "How assertively the reference should steer the result. This is wording, not a sampler value; how much structure survives is set by KSampler denoise.",
                    "default": "balanced",
                }),
                "vision_resolution": ("INT", {
                    "tooltip": "The style reference is scaled to roughly this many pixels per side before it reaches Qwen3-VL. 384 is stable, 512 keeps more detail but costs more time.",
                    "default": 384,
                    "min": 128,
                    "max": 1024,
                    "step": 32,
                }),
            },
            "optional": {
                "custom_instruction": ("STRING", {
                    "tooltip": "Optional. Leave empty to use the strength preset. When filled it replaces the preset instruction; the target prompt is still appended.",
                    "default": "",
                    "multiline": True,
                }),
            },
        }

    RETURN_TYPES = ("CONDITIONING", "LATENT")
    RETURN_NAMES = ("conditioning", "latent")
    OUTPUT_TOOLTIPS = (
        "Positive conditioning with the reference described by Krea2/Qwen3-VL.",
        "Starting latent made from the target image; feed it to KSampler.latent_image.",
    )
    FUNCTION = "encode"
    CATEGORY = "My_custom_nodes/Degg_Style_Krea2"

    def encode(
        self,
        clip,
        vae,
        style_image,
        target_image,
        prompt,
        style_strength="balanced",
        vision_resolution=384,
        custom_instruction="",
    ):
        conditioning = _encode_style_conditioning(
            clip,
            style_image,
            prompt,
            style_strength,
            vision_resolution,
            custom_instruction,
            fusion=True,
        )
        target_pixels = _crop_image_for_vae(target_image, vae)
        latent = {"samples": vae.encode(target_pixels)}
        return (conditioning, latent)


NODE_CLASS_MAPPINGS = {
    "DeggKrea2StyleReference": DeggKrea2StyleReference,
    "DeggKrea2StyleFusion": DeggKrea2StyleFusion,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "DeggKrea2StyleReference": "Degg Krea2 Style Reference",
    "DeggKrea2StyleFusion": "Degg Krea2 Style Fusion",
}
