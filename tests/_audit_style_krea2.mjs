// Статический аудит Degg_Style_Krea2 — без ComfyUI и без браузера.
// Проверяет контракт проекта, который нельзя увидеть в юнит-тестах:
//   • обязательные файлы и UTF-8 без BOM;
//   • Python = EN-источник (ни кириллицы, ни китайского);
//   • протокольные значения combo и запрет подмены options.values;
//   • локализация: паритет ключей en/ru, русские подписи, нет CJK;
//   • запрещённые приёмы Nodes 2.0 (таймеры, computeSize, scripts/app.js);
//   • check.json ссылается на существующие тесты и ждёт FAIL: 0;
//   • README/SPECIFICATION/workflows на русском и без китайского.
//
// Запуск:  cd Degg_Style_Krea2 && node tests/_audit_style_krea2.mjs
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const errors = [];
const oks = [];
const check = (label, cond, extra = "") => {
  (cond ? oks : errors).push(label);
  if (!cond) console.log(`  FAIL  ${label}${extra ? "  [" + extra + "]" : ""}`);
  else console.log(`  ok    ${label}`);
};

const p = (...parts) => path.join(ROOT, ...parts);
const exists = (rel) => fs.existsSync(p(rel));
const read = (rel) => fs.readFileSync(p(rel), "utf8");
const bytes = (rel) => fs.readFileSync(p(rel));
const CJK = /[\u4e00-\u9fff\u3040-\u30ff]/;
const CYR = /[\u0400-\u04FF]/;

// ── файлы ─────────────────────────────────────────────────────────────────
const REQUIRED = [
  "__init__.py",
  "style_krea2.py",
  "locales/en/nodeDefs.json",
  "locales/ru/nodeDefs.json",
  "web/js/style_krea2.js",
  "tests/_test_style_krea2.py",
  "tests/_smoke_style_krea2.mjs",
  "tests/_audit_style_krea2.mjs",
  "check.json",
  "README.md",
  "SPECIFICATION.md",
  ".gitignore",
];
for (const rel of REQUIRED) check(`exists ${rel}`, exists(rel));

for (const rel of ["style_krea2.py", "__init__.py", "locales/en/nodeDefs.json", "locales/ru/nodeDefs.json", "web/js/style_krea2.js", "README.md", "SPECIFICATION.md", "check.json"]) {
  if (!exists(rel)) continue;
  const raw = bytes(rel);
  check(`${rel}: UTF-8 without BOM`, !(raw.length >= 3 && raw[0] === 0xef && raw[1] === 0xbb && raw[2] === 0xbf));
}

// ── Python ────────────────────────────────────────────────────────────────
const py = exists("style_krea2.py") ? read("style_krea2.py") : "";
check("Python: no Cyrillic (EN source)", !CYR.test(py));
check("Python: no Chinese", !CJK.test(py));
check("Python: no legacy Chinese style keys", !/轻微|平衡|强烈/.test(py));
check("Python: both class keys", py.includes('"DeggKrea2StyleReference"') && py.includes('"DeggKrea2StyleFusion"'));
check("Python: EN display names", py.includes('"Degg Krea2 Style Reference"') && py.includes('"Degg Krea2 Style Fusion"'));
check("Python: category", py.includes('CATEGORY = "My_custom_nodes/Degg_Style_Krea2"'));
check("Python: protocol values", py.includes('"light"') && py.includes('"balanced"') && py.includes('"strong"'));
check("Python: no CJK inside tooltips/descriptions", !CJK.test(py));
check("Python: images passed to tokenizer", /images\s*=\s*\[/.test(py));
check("Python: scheduled encode", py.includes("encode_from_tokens_scheduled"));
check("Python: vision resize via comfy.utils", py.includes("common_upscale"));
check("Python: VAE token ratio", py.includes("spacial_compression_encode"));
check("Python: VAE crop + encode", py.includes('{"samples"') && py.includes("vae.encode"));
check("Python: OUTPUT_TOOLTIPS", py.includes("OUTPUT_TOOLTIPS"));
check("Python: no hardcoded absolute path", !/[A-Za-z]:\\/.test(py));
check("Python: no print/trace debug", !/\bprint\s*\(/.test(py));

const init = exists("__init__.py") ? read("__init__.py") : "";
check("__init__: imports module", init.includes("from .style_krea2 import"));
check("__init__: mappings", init.includes("NODE_CLASS_MAPPINGS") && init.includes("NODE_DISPLAY_NAME_MAPPINGS"));
check("__init__: WEB_DIRECTORY", /WEB_DIRECTORY\s*=\s*"web"/.test(init));

// ── JS ────────────────────────────────────────────────────────────────────
const js = exists("web/js/style_krea2.js") ? read("web/js/style_krea2.js") : "";
check("JS: comfyAPI import", /window\.comfyAPI\??\.app/.test(js));
check("JS: getOptionLabel", js.includes("getOptionLabel"));
check("JS: locale event", js.includes("Comfy.Locale.change"));
check("JS: settings listener", /ui\??\.settings\??\.addEventListener/.test(js));
check("JS: known class names", js.includes("DeggKrea2StyleReference") && js.includes("DeggKrea2StyleFusion"));
check("JS: RU + EN labels", js.includes("Слабый") && js.includes("Light"));
check("JS: no Chinese", !CJK.test(js));
check("JS: no options.values assignment", !/options\s*\.\s*values\s*=/.test(js));
check("JS: no widget.value assignment", !/\.value\s*=/.test(js.replace(/\/\/[^\n]*/g, "")));
check("JS: no timers", !/setInterval\s*\(/.test(js) && !/setTimeout\s*\(/.test(js));
check("JS: no computeSize override", !/\.computeSize\s*=/.test(js));
check("JS: no legacy import", !/scripts\/app\.js/.test(js));
check("JS: no network calls", !/\bfetch\s*\(/.test(js));
check("JS: cleans up onRemoved", js.includes("onRemoved"));

// ── локали ────────────────────────────────────────────────────────────────
const loadJson = (rel) => JSON.parse(read(rel));
const en = exists("locales/en/nodeDefs.json") ? loadJson("locales/en/nodeDefs.json") : {};
const ru = exists("locales/ru/nodeDefs.json") ? loadJson("locales/ru/nodeDefs.json") : {};
const KEYS = ["DeggKrea2StyleReference", "DeggKrea2StyleFusion"];
check("locales: same node keys", JSON.stringify(Object.keys(en).sort()) === JSON.stringify([...KEYS].sort()) && JSON.stringify(Object.keys(ru).sort()) === JSON.stringify([...KEYS].sort()));
for (const key of KEYS) {
  if (!en[key] || !ru[key]) continue;
  check(`locale ${key}: EN display`, !CYR.test(en[key].display_name) && !CJK.test(en[key].display_name));
  check(`locale ${key}: RU display`, CYR.test(ru[key].display_name) && !CJK.test(ru[key].display_name));
  check(`locale ${key}: RU description`, CYR.test(ru[key].description) && !CJK.test(ru[key].description));
  const enInputs = Object.keys(en[key].inputs || {}).sort();
  const ruInputs = Object.keys(ru[key].inputs || {}).sort();
  check(`locale ${key}: input parity`, JSON.stringify(enInputs) === JSON.stringify(ruInputs), `${enInputs} vs ${ruInputs}`);
  check(`locale ${key}: has custom_instruction`, enInputs.includes("custom_instruction") && ruInputs.includes("custom_instruction"));
  const enOut = Object.keys(en[key].outputs || {}).sort();
  const ruOut = Object.keys(ru[key].outputs || {}).sort();
  check(`locale ${key}: output parity`, JSON.stringify(enOut) === JSON.stringify(ruOut));
  for (const [name, entry] of Object.entries(ru[key].inputs || {})) {
    check(`locale ${key}: RU ${name} is Cyrillic`, CYR.test(entry.name || "") && CYR.test(entry.tooltip || ""));
  }
  for (const [slot, entry] of Object.entries(ru[key].outputs || {})) {
    check(`locale ${key}: RU output ${slot} is Cyrillic`, CYR.test(entry.name || "") && CYR.test(entry.tooltip || ""));
  }
}

// ── check.json ────────────────────────────────────────────────────────────
let manifest = null;
try {
  manifest = exists("check.json") ? loadJson("check.json") : null;
} catch (error) {
  check("check.json parses", false, String(error));
}
if (manifest) {
  check("check.json: three checks", Array.isArray(manifest.checks) && manifest.checks.length === 3, String(manifest.checks?.length));
  for (const item of manifest.checks || []) {
    const script = String(item.cmd || "").split(/\s+/).pop();
    check(`check.json: ${item.label} script exists`, exists(script), script);
    check(`check.json: ${item.label} label/description`, !!item.label && !!item.description);
    check(`check.json: ${item.label} expects FAIL: 0`, (item.expect || []).includes("FAIL: 0"), JSON.stringify(item.expect));
  }
}

// ── документация ──────────────────────────────────────────────────────────
const readme = exists("README.md") ? read("README.md") : "";
check("README: Russian", CYR.test(readme));
check("README: no Chinese", !CJK.test(readme));
check("README: both node names", readme.includes("Стиль по референсу") && readme.includes("Совмещение"));
check("README: models", readme.includes("qwen3vl_4b_fp8_scaled") && readme.includes("qwen_image_vae"));
check("README: denoise guidance", /denoise/i.test(readme));
check("README: protocol values documented", readme.includes("light") && readme.includes("balanced") && readme.includes("strong"));
check("README: honest scope (not official adapter)", /не\s+(?:является\s+)?официальн/i.test(readme.replace(/\s+/g, " ")));
check("README: meaningful length", readme.length > 4000, String(readme.length));

const spec = exists("SPECIFICATION.md") ? read("SPECIFICATION.md") : "";
check("SPECIFICATION: Russian", CYR.test(spec));
check("SPECIFICATION: no Chinese", !CJK.test(spec));
check("SPECIFICATION: class keys", spec.includes("DeggKrea2StyleReference") && spec.includes("DeggKrea2StyleFusion"));
check("SPECIFICATION: locale architecture", /locales/.test(spec) && /getOptionLabel/.test(spec));
check("SPECIFICATION: tests listed", /_test_style_krea2|_smoke_style_krea2|_audit_style_krea2/.test(spec));

// ── workflows ─────────────────────────────────────────────────────────────
const wfDir = p("workflows");
const wfFiles = fs.existsSync(wfDir) ? fs.readdirSync(wfDir).filter((n) => n.endsWith(".json")) : [];
check("workflows: two examples", wfFiles.length === 2, JSON.stringify(wfFiles));
for (const file of wfFiles) {
  const raw = fs.readFileSync(path.join(wfDir, file), "utf8");
  check(`workflow ${file}: no Chinese`, !CJK.test(raw));
  let graph = null;
  try {
    graph = JSON.parse(raw);
    check(`workflow ${file}: parses`, true);
  } catch (error) {
    check(`workflow ${file}: parses`, false, String(error));
  }
  if (!graph) continue;
  const nodes = Array.isArray(graph.nodes) ? graph.nodes : [];
  const types = nodes.map((n) => n.type);
  check(`workflow ${file}: has nodes`, nodes.length > 0);
  check(`workflow ${file}: notes in Russian`, nodes.some((n) => /Note/.test(n.type) && CYR.test(JSON.stringify(n.widgets_values || ""))));
  if (file.includes("reference")) {
    check(`workflow ${file}: uses Reference node`, types.includes("DeggKrea2StyleReference"));
    check(`workflow ${file}: combo protocol EN`, nodes.some((n) => n.type === "DeggKrea2StyleReference" && (n.widgets_values || []).includes("light")));
  } else if (file.includes("fusion")) {
    check(`workflow ${file}: uses Fusion node`, types.includes("DeggKrea2StyleFusion"));
    check(`workflow ${file}: combo protocol EN`, nodes.some((n) => n.type === "DeggKrea2StyleFusion" && (n.widgets_values || []).includes("balanced")));
  } else {
    check(`workflow ${file}: known name`, false, file);
  }
}

// ── гигиена ───────────────────────────────────────────────────────────────
const ignore = exists(".gitignore") ? read(".gitignore") : "";
check(".gitignore: __pycache__", ignore.includes("__pycache__"));
check(".gitignore: pyc", ignore.includes("*.pyc"));

console.log("");
console.log(`ok: ${oks.length}   FAIL: ${errors.length}`);
if (errors.length) {
  console.log("аудит НЕ чист");
  process.exit(1);
}
console.log("аудит чист");
