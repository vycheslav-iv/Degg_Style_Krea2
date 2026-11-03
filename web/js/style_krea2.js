// Degg Style Krea2 — интерфейс нод.
//
// Работает только с ПОДПИСЯМИ combo «Сила стиля». Значения combo — протокол
// (light / balanced / strong) — не трогаем: их читает Python, и подмена списка
// options.values молча увела бы ноду в дефолт.
//
// Язык берётся из Comfy.Locale при создании ноды и переприменяется по событию
// Comfy.Locale.change, без перезапуска ComfyUI. Подписи остальных входов,
// имени ноды и описания приходят из locales/{en,ru}/nodeDefs.json.
(() => {
  const { app } = window.comfyAPI?.app ?? {};
  if (!app || typeof app.registerExtension !== 'function') return;

  const NODE_KEYS = ['DeggKrea2StyleReference', 'DeggKrea2StyleFusion'];
  const WIDGET = 'style_strength';

  const STRENGTH_LABELS = {
    en: {
      light: 'Light',
      balanced: 'Balanced',
      strong: 'Strong',
    },
    ru: {
      light: 'Слабый',
      balanced: 'Сбалансированный',
      strong: 'Сильный',
    },
  };

  function readLocale() {
    try {
      const value = app?.extensionManager?.setting?.get?.('Comfy.Locale');
      if (typeof value === 'string' && value) return value.toLowerCase();
    } catch {
      /* фронтенд без менеджера настроек */
    }
    return 'en';
  }

  function strengthLabels() {
    return readLocale().startsWith('ru') ? STRENGTH_LABELS.ru : STRENGTH_LABELS.en;
  }

  function applyWidgetLabels(node) {
    const widget = (node?.widgets || []).find((item) => item?.name === WIDGET);
    if (!widget) return;
    widget.options = widget.options || {};
    const labels = strengthLabels();
    widget.options.getOptionLabel = (value) => labels[value] ?? String(value ?? '');
    try {
      node.setDirtyCanvas?.(true, true);
    } catch {
      /* нода вне canvas — подписи всё равно применены */
    }
  }

  const tracked = new Set();

  function track(node) {
    applyWidgetLabels(node);
    tracked.add(node);
    const previous = node.onRemoved;
    node.onRemoved = function () {
      tracked.delete(node);
      return previous?.apply(this, arguments);
    };
  }

  const onLocaleChange = () => {
    for (const node of tracked) applyWidgetLabels(node);
  };

  try {
    app?.ui?.settings?.addEventListener?.('Comfy.Locale.change', onLocaleChange);
  } catch {
    /* фронтенд без legacy-событий настроек */
  }

  app.registerExtension({
    name: 'Degg.StyleKrea2',
    beforeRegisterNodeDef(nodeType, nodeData) {
      if (!NODE_KEYS.includes(nodeData?.name)) return;
      const previous = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function () {
        const result = previous?.apply(this, arguments);
        track(this);
        return result;
      };
    },
  });

  globalThis.__DEGG_STYLE_KREA2__ = {
    NODE_KEYS,
    STRENGTH_LABELS,
    readLocale,
    strengthLabels,
    applyWidgetLabels,
  };
})();
