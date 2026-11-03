"""Functional test for Degg_Style_Krea2 (Python) — no ComfyUI, no torch.

The node is a thin layer over three pure helpers (style text, vision target
size, VAE crop box) plus two entry points that touch `clip`/`vae`. The pure
helpers are tested directly; the entry points are tested through a small
tensor stub that preserves torch shape semantics for the operations the node
uses: `movedim`, basic `__getitem__` slicing, and `shape`.

`comfy.utils.common_upscale` is replaced by a stub that records the requested
size, so the test verifies WHICH resolution is sent to Qwen3-VL, not merely
that some tensor came back.

Run:  cd Degg_Style_Krea2 && python tests/_test_style_krea2.py
"""

import importlib.util
import json
import math
import re
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NODE = ROOT / "style_krea2.py"
INIT = ROOT / "__init__.py"
LOCALES = ROOT / "locales"

fails = []
oks = []


def _p(text):
    """Console-safe printing (Windows cp1251 cannot encode every glyph)."""
    try:
        enc = sys.stdout.encoding or "utf-8"
        sys.stdout.write(str(text).encode(enc, "replace").decode(enc, "replace") + "\n")
    except Exception:
        pass


def check(name, cond, extra=""):
    (oks if cond else fails).append(name)
    _p(("  ok  " if cond else "  FAIL") + f"  {name}" + (f"  [{extra}]" if extra and not cond else ""))


def _fail_fast(message):
    _p("  FAIL  " + message)
    _p(f"FAIL: {len(fails) + 1}")
    sys.exit(1)


if not NODE.exists():
    _fail_fast("style_krea2.py exists")

# ──────────────────────────── tensor / comfy stubs ─────────────────────────


class FakeTensor:
    """Shape-only tensor with torch-compatible movedim and basic slicing."""

    def __init__(self, shape):
        self.shape = tuple(int(s) for s in shape)

    def movedim(self, source, destination):
        dims = list(self.shape)
        moved = dims.pop(source if source >= 0 else len(dims) + source)
        index = destination if destination >= 0 else len(dims) + destination + 1
        dims.insert(max(0, min(index, len(dims))), moved)
        return FakeTensor(dims)

    def __getitem__(self, key):
        if not isinstance(key, tuple):
            key = (key,)
        dims = list(self.shape)
        out = []
        cursor = 0
        for item in key:
            if item is Ellipsis:
                out.extend(dims[cursor:])
                cursor = len(dims)
                continue
            if item is None:
                out.append(1)
                continue
            if cursor >= len(dims):
                break
            if isinstance(item, slice):
                start, stop, step = item.indices(dims[cursor])
                out.append(len(range(start, stop, step)))
            else:
                number = int(item)
                number = number if number >= 0 else dims[cursor] + number
                if number < 0 or number >= dims[cursor]:
                    raise IndexError("index out of range")
            cursor += 1
        out.extend(dims[cursor:])
        return FakeTensor(out)


class FakeClip:
    def __init__(self):
        self.tokenize_calls = []
        self.encode_calls = []

    def tokenize(self, text, images=None):
        self.tokenize_calls.append((text, images))
        return {"tokens": "stub"}

    def encode_from_tokens_scheduled(self, tokens):
        self.encode_calls.append(tokens)
        return [["conditioning", {"pooled_output": None}]]


class FakeVAE:
    def __init__(self, shape=(1, 16, 2, 2), ratio=None, boom=False):
        self.shape = shape
        self.ratio = ratio
        self.boom = boom
        self.seen_pixels = []

    def spacial_compression_encode(self):
        if self.boom:
            raise RuntimeError("stub failure")
        return self.ratio

    def encode(self, pixels):
        self.seen_pixels.append(pixels)
        return FakeTensor(self.shape)


_upcalls = []


def _common_upscale(samples, width, height, method, crop):
    _upcalls.append((tuple(samples.shape), width, height, method, crop))
    return FakeTensor((samples.shape[0], samples.shape[1], height, width))


comfy_pkg = types.ModuleType("comfy")
comfy_utils = types.ModuleType("comfy.utils")
comfy_utils.common_upscale = _common_upscale
comfy_pkg.utils = comfy_utils
sys.modules["comfy"] = comfy_pkg
sys.modules["comfy.utils"] = comfy_utils

spec = importlib.util.spec_from_file_location("degg_style_krea2", NODE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

# ─────────────────────────────── contract ─────────────────────────────────


NODE_KEY_REF = "DeggKrea2StyleReference"
NODE_KEY_FUSION = "DeggKrea2StyleFusion"
EXPECTED_VALUES = ["light", "balanced", "strong"]

check("NODE_CLASS_MAPPINGS has exactly two nodes", set(mod.NODE_CLASS_MAPPINGS) == {NODE_KEY_REF, NODE_KEY_FUSION}, str(sorted(mod.NODE_CLASS_MAPPINGS)))
check("display name Reference is EN", mod.NODE_DISPLAY_NAME_MAPPINGS.get(NODE_KEY_REF) == "Degg Krea2 Style Reference", mod.NODE_DISPLAY_NAME_MAPPINGS.get(NODE_KEY_REF))
check("display name Fusion is EN", mod.NODE_DISPLAY_NAME_MAPPINGS.get(NODE_KEY_FUSION) == "Degg Krea2 Style Fusion", mod.NODE_DISPLAY_NAME_MAPPINGS.get(NODE_KEY_FUSION))

ref = mod.NODE_CLASS_MAPPINGS[NODE_KEY_REF]
fusion = mod.NODE_CLASS_MAPPINGS[NODE_KEY_FUSION]

for label, cls in (("Reference", ref), ("Fusion", fusion)):
    check(f"{label}: category", cls.CATEGORY == "My_custom_nodes/Degg_Style_Krea2", getattr(cls, "CATEGORY", None))
    check(f"{label}: description is non-empty EN", bool(cls.DESCRIPTION) and not re.search(r"[\u0400-\u04FF\u4e00-\u9fff]", cls.DESCRIPTION))
    check(f"{label}: OUTPUT_TOOLTIPS matches outputs", isinstance(getattr(cls, "OUTPUT_TOOLTIPS", None), tuple) and len(cls.OUTPUT_TOOLTIPS) == len(cls.RETURN_TYPES))

ref_schema = ref.INPUT_TYPES()
fusion_schema = fusion.INPUT_TYPES()

check("Reference: required input set", set(ref_schema["required"]) == {"clip", "style_image", "prompt", "style_strength", "vision_resolution"}, str(sorted(ref_schema["required"])))
check("Reference: optional custom_instruction", set(ref_schema.get("optional", {})) == {"custom_instruction"}, str(sorted(ref_schema.get("optional", {}))))
check("Fusion: required input set", set(fusion_schema["required"]) == {"clip", "vae", "style_image", "target_image", "prompt", "style_strength", "vision_resolution"}, str(sorted(fusion_schema["required"])))
check("Fusion: optional custom_instruction", set(fusion_schema.get("optional", {})) == {"custom_instruction"}, str(sorted(fusion_schema.get("optional", {}))))

for label, schema in (("Reference", ref_schema), ("Fusion", fusion_schema)):
    meta = dict(schema["required"])
    meta.update(schema.get("optional", {}))
    for name, entry in meta.items():
        tooltip = (entry[1] or {}).get("tooltip", "")
        check(f"{label}.{name}: EN tooltip", bool(tooltip) and not re.search(r"[\u0400-\u04FF\u4e00-\u9fff]", tooltip))

for label, cls, schema, default in (
    ("Reference", ref, ref_schema, "light"),
    ("Fusion", fusion, fusion_schema, "balanced"),
):
    values, options = schema["required"]["style_strength"]
    check(f"{label}: protocol values", values == EXPECTED_VALUES, str(values))
    check(f"{label}: strength default", options.get("default") == default, options.get("default"))
    check(f"{label}: vision_resolution bounds", schema["required"]["vision_resolution"][1].get("min") == 128 and schema["required"]["vision_resolution"][1].get("max") == 1024 and schema["required"]["vision_resolution"][1].get("step") == 32)
    check(f"{label}: prompt multiline", schema["required"]["prompt"][1].get("multiline") is True)

check("Reference: outputs", ref.RETURN_TYPES == ("CONDITIONING",) and ref.RETURN_NAMES == ("conditioning",), str(ref.RETURN_TYPES))
check("Fusion: outputs", fusion.RETURN_TYPES == ("CONDITIONING", "LATENT") and fusion.RETURN_NAMES == ("conditioning", "latent"), str(fusion.RETURN_TYPES))
check("FUNCTION is encode", ref.FUNCTION == "encode" and fusion.FUNCTION == "encode")

# ─────────────────────────── pure helper logic ────────────────────────────

check("STYLE_INSTRUCTIONS keys", list(mod.STYLE_INSTRUCTIONS) == EXPECTED_VALUES, str(list(mod.STYLE_INSTRUCTIONS)))
check("instructions differ", len(set(mod.STYLE_INSTRUCTIONS.values())) == 3)
check("instructions are EN", all(not re.search(r"[\u0400-\u04FF\u4e00-\u9fff]", text) for text in mod.STYLE_INSTRUCTIONS.values()))

check("normalize known", mod._normalize_strength("strong") == "strong")
check("normalize unknown falls back", mod._normalize_strength("bogus") == "balanced", mod._normalize_strength("bogus"))
check("normalize None falls back", mod._normalize_strength(None) == "balanced")
check("normalize honours explicit default", mod._normalize_strength("bogus", "light") == "light")

light = mod._build_style_text("a red fox", "light")
balanced = mod._build_style_text("a red fox", "balanced")
strong = mod._build_style_text("a red fox", "strong")
check("style text: light contains prompt", light.endswith("Target prompt: a red fox"), light[-40:])
check("style text: light instruction", mod.STYLE_INSTRUCTIONS["light"] in light)
check("style text: balanced instruction", mod.STYLE_INSTRUCTIONS["balanced"] in balanced)
check("style text: strong instruction", mod.STYLE_INSTRUCTIONS["strong"] in strong)
check("style text: presets differ", len({light, balanced, strong}) == 3)
check("style text: unknown strength falls back to balanced", mod._build_style_text("x", "bogus") == mod._build_style_text("x", "balanced"))

custom = mod._build_style_text("a red fox", "strong", "  paint it like a watercolor  ")
check("style text: custom instruction replaces preset", "paint it like a watercolor" in custom and mod.STYLE_INSTRUCTIONS["strong"] not in custom)
check("style text: custom keeps prompt", custom.endswith("Target prompt: a red fox"))
check("style text: blank custom uses preset", mod._build_style_text("x", "light", "   ") == mod._build_style_text("x", "light"))

fusion_text = mod._build_style_text("a red fox", "balanced", fusion=True)
check("fusion text: adds target-latent clause", "target image latent" in fusion_text, fusion_text[-120:])
check("fusion text: clause comes before prompt", fusion_text.index("target image latent") < fusion_text.index("Target prompt: a red fox"))
check("fusion text: no clause without fusion", "target image latent" not in balanced)

# vision target size — total pixels == resolution² (within rounding)
for source_w, source_h, resolution in ((16, 32, 384), (1920, 1080, 384), (512, 512, 512), (100, 100, 128)):
    target_w, target_h = mod._vision_target_size(source_w, source_h, resolution)
    ratio = (source_w * source_h) / (target_w * target_h)
    expected = (source_w * source_h) / (resolution * resolution)
    check(f"vision size {source_w}x{source_h}@{resolution} keeps aspect", abs(ratio - expected) / expected < 0.02, f"{target_w}x{target_h}")
    check(f"vision size {source_w}x{source_h}@{resolution} keeps ratio", abs((target_w / target_h) - (source_w / source_h)) < 0.02, f"{target_w}x{target_h}")

check("vision size is positive", mod._vision_target_size(1, 1, 128) == (128, 128), str(mod._vision_target_size(1, 1, 128)))

# VAE crop box
check("crop box 17x19 @8", mod._crop_box(17, 19, 8) == (0, 16, 1, 17), str(mod._crop_box(17, 19, 8)))
check("crop box even passes through", mod._crop_box(64, 32, 8) == (0, 64, 0, 32), str(mod._crop_box(64, 32, 8)))
try:
    mod._crop_box(4, 8, 8)
    check("crop box too small raises", False)
except ValueError as exc:
    check("crop box too small raises", "too small" in str(exc), str(exc))

check("vae ratio from method", mod._vae_downscale_ratio(FakeVAE(ratio=4)) == 4)
check("vae ratio fallback on raise", mod._vae_downscale_ratio(FakeVAE(boom=True)) == 8)
check("vae ratio fallback without method", mod._vae_downscale_ratio(object()) == 8)

# ───────────────────────────── entry points ───────────────────────────────

_upcalls.clear()
clip = FakeClip()
image = FakeTensor((1, 32, 16, 4))
out = mod._encode_style_conditioning(clip, image, "a red fox", "strong", 384, "")
check("semantic: conditioning returned", out == [["conditioning", {"pooled_output": None}]])
check("semantic: one tokenize call", len(clip.tokenize_calls) == 1)
text, images = clip.tokenize_calls[0]
check("semantic: text carries prompt", text.endswith("Target prompt: a red fox"))
check("semantic: images list of one", isinstance(images, list) and len(images) == 1, str(type(images)))
check("semantic: reference resized to HWC", images[0].shape == (1, 543, 272, 3), str(images[0].shape))
check("semantic: only three channels", images[0].shape[-1] == 3)
check("semantic: upscale asked for 272x543", _upcalls and _upcalls[-1][1:3] == (272, 543), str(_upcalls))
check("semantic: encode scheduled", clip.encode_calls == [{"tokens": "stub"}])

_upcalls.clear()
clip2 = FakeClip()
target = FakeTensor((1, 17, 19, 3))
vae = FakeVAE(ratio=8)
cond, latent = mod.NODE_CLASS_MAPPINGS[NODE_KEY_FUSION]().encode(clip2, vae, image, target, "a red fox", "balanced", 384, "")
check("fusion: returns two values", isinstance(cond, list) and isinstance(latent, dict) and "samples" in latent)
check("fusion: latent is VAE output", isinstance(latent["samples"], FakeTensor) and latent["samples"].shape == (1, 16, 2, 2))
check("fusion: VAE got centred HWC crop", vae.seen_pixels and vae.seen_pixels[0].shape == (1, 16, 16, 3), str(vae.seen_pixels[0].shape if vae.seen_pixels else None))
check("fusion: text has fusion clause", "target image latent" in clip2.tokenize_calls[0][0])

# Reference.encode signature order must match INPUT_TYPES
check("Reference.encode accepts keyword contract", ref().encode(clip=FakeClip(), style_image=FakeTensor((1, 32, 32, 3)), prompt="x", style_strength="light", vision_resolution=384, custom_instruction="")[0][0][0] == "conditioning")

# ─────────────────────────────── locales ─────────────────────────────────

en_path = LOCALES / "en" / "nodeDefs.json"
ru_path = LOCALES / "ru" / "nodeDefs.json"
check("locales/en exists", en_path.exists())
check("locales/ru exists", ru_path.exists())

if en_path.exists() and ru_path.exists():
    en_raw = en_path.read_bytes()
    ru_raw = ru_path.read_bytes()
    check("locales/en is UTF-8 without BOM", not en_raw.startswith(b"\xef\xbb\xbf"))
    check("locales/ru is UTF-8 without BOM", not ru_raw.startswith(b"\xef\xbb\xbf"))
    en = json.loads(en_raw.decode("utf-8"))
    ru = json.loads(ru_raw.decode("utf-8"))
    check("locales: node keys match", set(en) == set(ru) == {NODE_KEY_REF, NODE_KEY_FUSION}, str(sorted(en)))
    for key in (NODE_KEY_REF, NODE_KEY_FUSION):
        check(f"locale {key}: EN display_name", en[key]["display_name"] == mod.NODE_DISPLAY_NAME_MAPPINGS[key], en[key]["display_name"])
        check(f"locale {key}: RU display_name translated", bool(ru[key]["display_name"]) and re.search(r"[\u0400-\u04FF]", ru[key]["display_name"]) and ru[key]["display_name"] != en[key]["display_name"], ru[key]["display_name"])
        check(f"locale {key}: descriptions present", bool(en[key].get("description")) and bool(ru[key].get("description")))
        check(f"locale {key}: RU description translated", re.search(r"[\u0400-\u04FF]", ru[key]["description"]) is not None)
        schema = (ref if key == NODE_KEY_REF else fusion).INPUT_TYPES()
        names = set(schema["required"]) | set(schema.get("optional", {}))
        for lang, data in (("en", en[key]), ("ru", ru[key])):
            check(f"locale {key}/{lang}: input keys match", set(data.get("inputs", {})) == names, str(sorted(data.get("inputs", {}))))
            for name in names:
                entry = data.get("inputs", {}).get(name, {})
                check(f"locale {key}/{lang}: {name} name+tooltip", bool(entry.get("name")) and bool(entry.get("tooltip")))
        outputs = set(str(i) for i in range(len((ref if key == NODE_KEY_REF else fusion).RETURN_TYPES)))
        for lang, data in (("en", en[key]), ("ru", ru[key])):
            check(f"locale {key}/{lang}: output keys match", set(data.get("outputs", {})) == outputs, str(sorted(data.get("outputs", {}))))
            for slot in outputs:
                entry = data.get("outputs", {}).get(slot, {})
                check(f"locale {key}/{lang}: output {slot} name+tooltip", bool(entry.get("name")) and bool(entry.get("tooltip")))
        check(f"locale {key}: RU ends with no CJK", not re.search(r"[\u4e00-\u9fff]", json.dumps(ru[key], ensure_ascii=False)))

# ───────────────────────────── source hygiene ─────────────────────────────

source = NODE.read_text(encoding="utf-8")
check("Python has no Cyrillic", not re.search(r"[\u0400-\u04FF]", source))
check("Python has no CJK", not re.search(r"[\u4e00-\u9fff\u3040-\u30ff]", source))
check("Python has no legacy Chinese values", "\u8f7b\u5fae" not in source and "\u5e73\u8861" not in source and "\u5f3a\u70c8" not in source)

check("__init__.py exists", INIT.exists())
if INIT.exists():
    init_src = INIT.read_text(encoding="utf-8")
    check("__init__ imports the node module", "from .style_krea2 import" in init_src, init_src[:80])
    check("__init__ exports both mappings", "NODE_CLASS_MAPPINGS" in init_src and "NODE_DISPLAY_NAME_MAPPINGS" in init_src)
    check("__init__ declares WEB_DIRECTORY", "WEB_DIRECTORY" in init_src and '"web"' in init_src)

# ─────────────────────────────── report ──────────────────────────────────

_p("")
_p(f"ok: {len(oks)}   FAIL: {len(fails)}")
if fails:
    _p("ТЕСТ НЕ ПРОЙДЕН")
    sys.exit(1)
_p("ТЕСТ ПРОЙДЕН")
