// JS-смоук Degg_Style_Krea2: исполняет web/js/style_krea2.js в vm-контексте с
// заглушкой window/comfyAPI и проверяет:
//   • расширение регистрируется и трогает только свои два класса;
//   • подписи combo «стиль» меняются RU/EN через getOptionLabel;
//   • ПРОТОКОЛЬНЫЕ значения (light/balanced/strong) и options.values не
//     подменяются — иначе Python молча уйдёт в дефолт;
//   • смена Comfy.Locale переприменяет подписи на лету (без перезапуска);
//   • onRemoved снимает ноду со слежения;
//   • нет таймеров/retry-регистрации.
//
// Запуск:  cd Degg_Style_Krea2 && node tests/_smoke_style_krea2.mjs
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const JS = path.join(ROOT, "web", "js", "style_krea2.js");

const errors = [];
const oks = [];
const check = (label, cond, extra = "") => {
  (cond ? oks : errors).push(label);
  if (!cond) console.log(`  FAIL  ${label}${extra ? "  [" + extra + "]" : ""}`);
  else console.log(`  ok    ${label}`);
};

// ── заглушка Nodes 2.0 ──────────────────────────────────────────────────────
const registered = [];
const localeEvents = [];
const state = { locale: "ru" };

const app = {
  registerExtension: (ext) => registered.push(ext),
  ui: {
    settings: {
      addEventListener: (event, fn) => localeEvents.push({ event, fn }),
      removeEventListener: () => {},
    },
  },
  extensionManager: {
    setting: {
      get: (key) => {
        if (key !== "Comfy.Locale") return undefined;
        if (state.throwOnRead) throw new Error("stub failure");
        return state.locale;
      },
    },
  },
};

const ctx = {
  console,
  Math,
  JSON,
  Number,
  String,
  Array,
  Object,
  Set,
  Date,
  window: { comfyAPI: { app: { app } } },
};
ctx.globalThis = ctx;
vm.createContext(ctx);

const src = fs.readFileSync(JS, "utf8");
vm.runInContext(src, ctx, { filename: JS });

const hooks = ctx.__DEGG_STYLE_KREA2__;
const REF = "DeggKrea2StyleReference";
const FUSION = "DeggKrea2StyleFusion";

check("test hooks exposed", !!hooks && typeof hooks.applyWidgetLabels === "function");
check("two node keys", !!hooks && hooks.NODE_KEYS.length === 2 && hooks.NODE_KEYS.includes(REF) && hooks.NODE_KEYS.includes(FUSION));
check("extension registered", registered.length === 1, String(registered.length));
check("extension name", registered[0]?.name === "Degg.StyleKrea2", registered[0]?.name);
check("one locale listener", localeEvents.length === 1 && localeEvents[0].event === "Comfy.Locale.change", JSON.stringify(localeEvents.map((e) => e.event)));

// ── нода-заглушка ──────────────────────────────────────────────────────────
function makeNode(values = ["light", "balanced", "strong"], initial = "light") {
  const widget = {
    name: "style_strength",
    value: initial,
    options: { values: values.slice() },
    label: "Style strength",
  };
  const node = {
    widgets: [widget],
    dirty: 0,
    setDirtyCanvas() {
      this.dirty += 1;
    },
  };
  return { node, widget };
}

function makeWired({ values, initial } = {}) {
  const nodeType = function NodeType() {};
  nodeType.prototype.onNodeCreated = function () {};
  registered[0].beforeRegisterNodeDef(nodeType, { name: REF }, app);
  const { node, widget } = makeNode(values, initial);
  const instance = Object.create(nodeType.prototype);
  instance.widgets = node.widgets;
  instance.setDirtyCanvas = node.setDirtyCanvas.bind(node);
  instance.onNodeCreated();
  return { instance, node, widget };
}

const { node, widget } = makeWired();
check("getOptionLabel installed", typeof widget.options.getOptionLabel === "function");
check("RU label light", widget.options.getOptionLabel("light") === "Слабый", widget.options.getOptionLabel("light"));
check("RU label balanced", widget.options.getOptionLabel("balanced") === "Сбалансированный");
check("RU label strong", widget.options.getOptionLabel("strong") === "Сильный");
check("unknown protocol value passes through", widget.options.getOptionLabel("custom") === "custom");
check("protocol values untouched", JSON.stringify(widget.options.values) === JSON.stringify(["light", "balanced", "strong"]));
check("widget value untouched", widget.value === "light");
check("option bag preserved", widget.options.values.length === 3);
check("canvas marked dirty", node.dirty > 0);

// ── EN / RU через событие локали ───────────────────────────────────────────
state.locale = "en";
localeEvents[0].fn();
check("EN label after event", widget.options.getOptionLabel("light") === "Light", widget.options.getOptionLabel("light"));
state.locale = "ru-RU";
localeEvents[0].fn();
check("ru-RU counts as Russian", widget.options.getOptionLabel("balanced") === "Сбалансированный");
state.locale = "de";
localeEvents[0].fn();
check("other locale falls back to English", widget.options.getOptionLabel("strong") === "Strong");

// ── чтение локали ─────────────────────────────────────────────────────────
check("readLocale sees current value", hooks.readLocale() === "de", hooks.readLocale());
state.throwOnRead = true;
check("readLocale survives a throwing settings manager", hooks.readLocale() === "en", hooks.readLocale());
state.throwOnRead = false;

// ── регистрация через beforeRegisterNodeDef ───────────────────────────────
function prototypeWith(node) {
  return function NodeType() {};
}

{
  const nodeType = function NodeType() {};
  nodeType.prototype.onNodeCreated = function onCreated() {
    this.created = true;
  };
  registered[0].beforeRegisterNodeDef(nodeType, { name: REF }, app);
  const { widget: w2 } = makeNode();
  const instance = Object.create(nodeType.prototype);
  instance.widgets = [w2];
  instance.setDirtyCanvas = () => {};
  instance.onNodeCreated();
  check("original onNodeCreated preserved", instance.created === true);
  check("Reference node wired by class name", typeof w2.options.getOptionLabel === "function");
}

{
  const nodeType = function NodeType() {};
  let called = false;
  nodeType.prototype.onNodeCreated = () => {
    called = true;
  };
  registered[0].beforeRegisterNodeDef(nodeType, { name: FUSION }, app);
  const { widget: w3 } = makeNode();
  const instance = Object.create(nodeType.prototype);
  instance.widgets = [w3];
  instance.onNodeCreated();
  check("Fusion node wired", called === true && typeof w3.options.getOptionLabel === "function");
}

{
  const nodeType = function NodeType() {};
  const before = nodeType.prototype.onNodeCreated;
  registered[0].beforeRegisterNodeDef(nodeType, { name: "SomeOtherNode" }, app);
  check("foreign node untouched", nodeType.prototype.onNodeCreated === before);
}

// ── нода без виджета / без options ────────────────────────────────────────
check("node without widget does not crash", (() => {
  try {
    hooks.applyWidgetLabels({ widgets: [] });
    return true;
  } catch {
    return false;
  }
})());
{
  const bare = { name: "style_strength", value: "light", options: null };
  let ok = true;
  try {
    hooks.applyWidgetLabels({ widgets: [bare], setDirtyCanvas() {} });
  } catch {
    ok = false;
  }
  check("null options created", ok && typeof bare.options?.getOptionLabel === "function");
}

// ── снятие с учёта ────────────────────────────────────────────────────────
{
  state.locale = "ru";
  const nodeType = function NodeType() {};
  nodeType.prototype.onNodeCreated = function () {};
  registered[0].beforeRegisterNodeDef(nodeType, { name: REF }, app);
  const { widget: w4 } = makeNode();
  const instance = Object.create(nodeType.prototype);
  instance.widgets = [w4];
  instance.onNodeCreated();
  check("tracked node labelled", w4.options.getOptionLabel("light") === "Слабый");
  instance.onRemoved?.();
  state.locale = "en";
  localeEvents[0].fn();
  check("removed node is no longer updated", w4.options.getOptionLabel("light") === "Слабый", w4.options.getOptionLabel("light"));
  state.locale = "ru";
}

// ── запрещённые приёмы ────────────────────────────────────────────────────
check("no setTimeout", !/setTimeout\s*\(/.test(src));
check("no setInterval", !/setInterval\s*\(/.test(src));
check("no options.values assignment", !/options\s*\.\s*values\s*=/.test(src));
check("no widget.value assignment", !/\.value\s*=/.test(src.replace(/\/\/.*$/gm, "")));
check("no legacy scripts/app.js import", !/scripts\/app\.js/.test(src));

console.log("");
console.log(`ok: ${oks.length}   FAIL: ${errors.length}`);
if (errors.length) {
  console.log("SMOKE FAIL");
  process.exit(1);
}
console.log("SMOKE OK");
