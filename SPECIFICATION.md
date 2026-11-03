# Degg_Style_Krea2 — спецификация

## Назначение

Перенос визуального стиля картинки-референса на генерацию Krea 2 двумя нодами:

| Класс | EN-имя | RU-имя | Назначение |
|-------|--------|--------|------------|
| `DeggKrea2StyleReference` | Degg Krea2 Style Reference | Degg Krea2 · Стиль по референсу | CONDITIONING со стилем, text2img |
| `DeggKrea2StyleFusion` | Degg Krea2 Style Fusion | Degg Krea2 · Совмещение | CONDITIONING + LATENT целевой картинки, img2img |

Категория меню: `My_custom_nodes/Degg_Style_Krea2`. Функция выполнения у обеих нод: `encode`.

## Файлы

```
Degg_Style_Krea2/
├── __init__.py                  # маппинги + WEB_DIRECTORY = "web"
├── style_krea2.py               # классы нод и хелперы
├── locales/en/nodeDefs.json     # EN-подписи и tooltip (зеркало Python)
├── locales/ru/nodeDefs.json     # RU-подписи и tooltip
├── web/js/style_krea2.js        # подписи combo + смена языка на лету
├── workflows/
│   ├── style_reference_example.json
│   └── style_fusion_example.json
├── tests/
│   ├── _test_style_krea2.py
│   ├── _smoke_style_krea2.mjs
│   └── _audit_style_krea2.mjs
├── check.json
├── README.md
└── SPECIFICATION.md
```

Тесты и `workflows/` живут в исходнике; `sync.py` копирует только код ноды (`.py`, `.js`, `.json` локалей и `check.json`), без `tests/`, `__pycache__/`, `.git/`.

## Механика

### Reference

1. `_resize_reference_for_vision` переводит IMAGE `[B,H,W,C]` в `[B,C,H,W]`, считает целевой размер `_vision_target_size(W, H, vision_resolution)` (площадь ≈ `vision_resolution²`, пропорции сохранены), вызывает `comfy.utils.common_upscale(..., "area", "disabled")` (в тестах — заглушка, при отсутствии `comfy` — `F.interpolate(mode="area")`), возвращает `[B,H,W,3]`.
2. `_build_style_text` собирает текст: пресет по `style_strength` (или `custom_instruction`, если он непустой), у Fusion добавляется `FUSION_CLAUSE`, затем `"\n\nTarget prompt: " + prompt`.
3. `clip.tokenize(text, images=[reference])` → `clip.encode_from_tokens_scheduled(tokens)` → `CONDITIONING`.

### Fusion

Дополнительно: `_vae_downscale_ratio` берёт `vae.spacial_compression_encode()`, при отсутствии или ошибке — `8`, и не меньше `1`. `_crop_box(height, width, ratio)` возвращает центральный кроп `(y0, y1, x0, x1)`, кратный ratio; при нулевом размере бросает `ValueError` со словом `too small`. `vae.encode(cropped)` упаковывается в `{"samples": ...}`.

Референс в Fusion идёт **только** в зрительный путь CLIP; целевая картинка — **только** в VAE. Смешивать их нельзя.

## Контракт входов и выходов

Reference — required: `clip` (CLIP), `style_image` (IMAGE), `prompt` (STRING, multiline), `style_strength` (COMBO `light`/`balanced`/`strong`, default `light`), `vision_resolution` (INT, default 384, min 128, max 1024, step 32). Optional: `custom_instruction` (STRING, default `""`).

Fusion — required: `clip`, `vae` (VAE), `style_image`, `target_image` (IMAGE), `prompt`, `style_strength` (default `balanced`), `vision_resolution`. Optional: `custom_instruction`.

Выходы: Reference — `("CONDITIONING",)` / `("conditioning",)`. Fusion — `("CONDITIONING","LATENT")` / `("conditioning","latent")`. У обеих нод заполнен `OUTPUT_TOOLTIPS` той же длины.

`IS_CHANGED` не переопределяется: значения виджетов входят в кэш-ключ штатно, а входные изображения приходят проводами.

## Локализация

Python остаётся EN-источником: в `.py` нет кириллицы и CJK, только английские tooltip. Имена классов и ключи входов — протокол, они не переводятся. Русские `display_name`, `description`, `inputs.*.name/tooltip`, `outputs.*.name/tooltip` лежат в `locales/ru/nodeDefs.json`; EN-зеркало — в `locales/en/nodeDefs.json` с тем же набором ключей.

Значения combo — протокол (`light`/`balanced`/`strong`). Переводятся только подписи: `web/js/style_krea2.js` ставит `widget.options.getOptionLabel`, текущий язык читает из `app.extensionManager.setting.get("Comfy.Locale")` (`ru*` → русский, иначе английский), переприменяет подписи по одному модульному слушателю `Comfy.Locale.change` и снимает ноду с трекинга в `onRemoved`. `options.values` и `widget.value` не подменяются: это увело бы ноду в дефолт без ошибок.

## Запреты фронтенда

- нет `setTimeout`/`setInterval` для layout и языка;
- нет перезаписи `computeSize`/`computeLayoutSize`;
- нет импорта `scripts/app.js` — только `window.comfyAPI.app`;
- расширение не трогает чужие классы нод: проверка по `NODE_KEYS`.

## Тесты и приёмка

- `tests/_test_style_krea2.py` — torch-free: заглушки `FakeTensor`, `FakeClip`, `FakeVAE`, `comfy.utils`; проверяет тексты инструкций, нормализацию силы, размер зрения, ресайз, кроп, порядок CLIP→conditioning и VAE→latent, схему входов/выходов, паритет locales.
- `tests/_smoke_style_krea2.mjs` — `vm` + заглушка `window.comfyAPI.app`: регистрация расширения, обёртка `onNodeCreated` только для двух классов, `getOptionLabel`, отсутствие подмены значений, смена языка, `onRemoved`, запрещённые приёмы.
- `tests/_audit_style_krea2.mjs` — статика: обязательные файлы, UTF-8 без BOM, EN-источник, паритет locales, `check.json`, README/SPECIFICATION, два workflow без китайского текста.

`check.json` содержит три проверки с `expect: ["FAIL: 0", ...]`; итоговый прогон — `python _process/check.py Degg_Style_Krea2`.

## Ограничения

Стиль передаётся описанием Qwen3-VL, а не адаптером: пиксельного совпадения нет, мелкий текст и точные детали референса не переносятся. Работает только с CLIP типа `krea2`. Fusion кропит цель по центру до кратности VAE.
