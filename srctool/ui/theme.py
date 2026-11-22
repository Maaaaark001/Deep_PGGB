"""SonarSRC 设计系统：色彩、字体、间距、组件样式。

设计意图（写给未来的自己）：
  * 这个工具的隐喻是 **测量仪器**，不是 SaaS 后台。参考的是实验室的示波器、
    广播机架、校准铭牌 —— 因此：方正、克制、边界清晰、数字对齐、没有圆角泡泡。
  * 刻意回避的"生成式默认"：柔和圆角卡片阵、每张卡一样的阴影、渐变洗色、
    近黑底 + 单根荧光绿、全大写小标签、'·' 分隔的元信息串。
  * 两个强调色各有语义，不混用：**黄铜 brass = 参考/输入/测量基准**，
    **铜绿 patina = 信号/输出/主操作**。警报色只在真的出问题时出现。
  * 字体：Bahnschrift（DIN 1451 衍生，工业铭牌感）负责拉丁字母与标题，
    Microsoft YaHei 兜底中文，Consolas 负责所有数字与单位（等宽才能对齐小数点）。
"""
from __future__ import annotations

FONT_UI = "'Bahnschrift', 'Microsoft YaHei', 'Segoe UI', sans-serif"
FONT_NUM = "'Consolas', 'Cascadia Mono', monospace"

DARK = {
    "bg": "#14181A", "panel": "#1B2124", "panel2": "#222A2D", "sunk": "#101416",
    "line": "#2C3639", "line_soft": "#232C2F",
    "ink": "#E9E6DD", "ink2": "#C4C8C0", "muted": "#8B9793",
    "brass": "#C8A24A", "patina": "#52A8A2", "alert": "#C96442",
    "good": "#74A96A", "warn": "#C79A3E",
}
LIGHT = {
    "bg": "#E9E7E1", "panel": "#F6F5F0", "panel2": "#FFFFFF", "sunk": "#DEDBD3",
    "line": "#CFCCC2", "line_soft": "#DEDBD2",
    "ink": "#1B1F1D", "ink2": "#3C4441", "muted": "#6B736F",
    "brass": "#8A6A1F", "patina": "#0F6E68", "alert": "#A33A2E",
    "good": "#2F7D4F", "warn": "#8A6A1F",
}


def _vars(d: dict) -> str:
    return "\n".join("  --%s: %s;" % (k.replace("_", "-"), v) for k, v in d.items())


CSS = """
:root {
__LIGHT__
  --r: 2px;
  --font-ui: __FONT_UI__;
  --font-num: __FONT_NUM__;
}
body.body--dark {
__DARK__
}

html, body, .nicegui-content {
  background: var(--bg) !important;
  font-family: var(--font-ui);
  color: var(--ink);
  -webkit-font-smoothing: antialiased;
}
.nicegui-content { padding: 0 !important; gap: 0 !important; }
body.body--dark .nicegui-content { background: var(--bg) !important; }

/* 极淡的方格纸底纹：仪器感来自结构，不来自渐变 */
body::before {
  content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 0;
  background-image:
    repeating-linear-gradient(0deg, var(--line) 0 1px, transparent 1px 24px),
    repeating-linear-gradient(90deg, var(--line) 0 1px, transparent 1px 24px);
  opacity: .18;
}
body.body--dark::before { opacity: .22; }

::selection { background: var(--patina); color: var(--bg); }

*::-webkit-scrollbar { width: 10px; height: 10px; }
*::-webkit-scrollbar-track { background: transparent; }
*::-webkit-scrollbar-thumb { background: var(--line); border-radius: 0; }
*::-webkit-scrollbar-thumb:hover { background: var(--muted); }

/* ===================== 排版 ===================== */
.ss-brand {
  font-family: var(--font-ui); font-weight: 600; font-size: 17px;
  letter-spacing: .14em; color: var(--ink); line-height: 1;
}
.ss-brand span { color: var(--brass); }
.ss-sub { font-size: 10.5px; letter-spacing: .16em; color: var(--muted); font-family: var(--font-ui); }
.ss-h1 { font-size: 21px; font-weight: 600; letter-spacing: .01em; line-height: 1.25; }
.ss-h2 { font-size: 12px; font-weight: 600; letter-spacing: .10em; color: var(--muted); margin-bottom: 2px; }
.ss-body { font-size: 13px; line-height: 1.7; color: var(--ink2); }
.ss-note { font-size: 11.5px; line-height: 1.6; color: var(--muted); }
.ss-num { font-family: var(--font-num); font-variant-numeric: tabular-nums; letter-spacing: -.01em; }

/* ===================== 外壳 ===================== */
.ss-shell { display: flex; min-height: 100vh; width: 100%; position: relative; z-index: 1; }
.ss-rail {
  width: 216px; flex: 0 0 216px; border-right: 1px solid var(--line);
  background: var(--panel); display: flex; flex-direction: column;
  position: sticky; top: 0; height: 100vh; padding: 18px 0 12px 0;
}
.ss-rail-head { padding: 0 18px 18px 18px; border-bottom: 1px solid var(--line-soft); }
.ss-nav { padding: 10px 10px; display: flex; flex-direction: column; gap: 1px; }
.ss-nav-item {
  display: flex; align-items: center; gap: 10px; padding: 9px 10px;
  border-left: 2px solid transparent; cursor: pointer; color: var(--muted);
  font-size: 13px; transition: color .12s, background .12s, border-color .12s;
  user-select: none;
}
.ss-nav-item:hover { color: var(--ink); background: var(--panel2); }
.ss-nav-item.active { color: var(--ink); border-left-color: var(--brass); background: var(--panel2); }
.ss-nav-item .q-icon { font-size: 17px; opacity: .85; }
.ss-nav-idx { font-family: var(--font-num); font-size: 10px; color: var(--muted); width: 14px; opacity: .7; }
.ss-main { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; }
.ss-page { padding: 26px 30px 60px 30px; max-width: 1560px; width: 100%; }

/* ===================== 卡片 ===================== */
.ss-card {
  background: var(--panel); border: 1px solid var(--line); border-radius: var(--r);
  padding: 16px 18px; position: relative;
}
.ss-card.sunk { background: var(--sunk); }
.ss-card.flat { padding: 0; overflow: hidden; }
.ss-card-h { display: flex; align-items: baseline; gap: 10px; justify-content: space-between; margin-bottom: 12px; }
.ss-card-t { font-size: 13px; font-weight: 600; letter-spacing: .02em; }
.ss-rule { height: 1px; background: var(--line-soft); margin: 12px 0; }
.ss-accent { border-left: 2px solid var(--brass); }
.ss-accent.sig { border-left-color: var(--patina); }
.ss-accent.bad { border-left-color: var(--alert); }
.ss-accent.ok { border-left-color: var(--good); }

/* ===================== 数据块 ===================== */
.ss-tile {
  background: var(--panel2); border: 1px solid var(--line-soft);
  padding: 10px 12px; border-radius: var(--r);
  flex: 1 1 0; min-width: 104px;
}
.ss-tile-l { font-size: 10.5px; letter-spacing: .06em; color: var(--muted); margin-bottom: 3px; }
.ss-tile-v { font-family: var(--font-num); font-size: 19px; line-height: 1.1; color: var(--ink); font-variant-numeric: tabular-nums; }
.ss-tile-v small { font-size: 11px; color: var(--muted); margin-left: 3px; font-family: var(--font-ui); }
.ss-tile.good .ss-tile-v { color: var(--good); }
.ss-tile.warn .ss-tile-v { color: var(--warn); }
.ss-tile.bad .ss-tile-v { color: var(--alert); }

.ss-verdict {
  border: 1px solid var(--line); border-left: 3px solid var(--muted);
  background: var(--panel); padding: 10px 13px; border-radius: var(--r);
}
.ss-verdict.ok { border-left-color: var(--good); }
.ss-verdict.warn { border-left-color: var(--warn); }
.ss-verdict.bad { border-left-color: var(--alert); }
.ss-verdict.info { border-left-color: var(--patina); }
.ss-verdict-t { font-size: 12.5px; font-weight: 600; display: flex; gap: 8px; align-items: baseline; justify-content: space-between; }
.ss-verdict-x { font-size: 12px; line-height: 1.65; color: var(--ink2); margin-top: 4px; }
.ss-verdict-m { font-family: var(--font-num); font-size: 11px; color: var(--muted); white-space: nowrap; }

.ss-chip {
  display: inline-flex; align-items: center; gap: 4px; padding: 1px 7px;
  border: 1px solid var(--line); border-radius: 1px; font-size: 10.5px;
  color: var(--muted); font-family: var(--font-num); letter-spacing: .02em; white-space: nowrap;
}
.ss-chip.brass { color: var(--brass); border-color: var(--brass); }
.ss-chip.patina { color: var(--patina); border-color: var(--patina); }
.ss-chip.bad { color: var(--alert); border-color: var(--alert); }
.ss-chip.ok { color: var(--good); border-color: var(--good); }

/* ===================== Quasar 覆写 ===================== */
.q-field--outlined .q-field__control { border-radius: var(--r) !important; }
.q-field__native, .q-field__input { font-family: var(--font-ui) !important; font-size: 13px !important; }
.q-field--dense .q-field__control { min-height: 32px; }
.q-field__label { font-size: 12px !important; color: var(--muted) !important; }
.q-menu, .q-dialog__inner > .q-card {
  border-radius: var(--r) !important; background: var(--panel) !important;
  border: 1px solid var(--line) !important; box-shadow: 0 12px 40px rgba(0,0,0,.35) !important;
}
.q-item { font-size: 13px !important; min-height: 34px !important; }
.q-btn { border-radius: var(--r) !important; text-transform: none !important;
  font-family: var(--font-ui) !important; letter-spacing: .02em; }
.q-btn--flat { color: var(--ink2) !important; }
.q-btn--flat:hover { background: var(--panel2) !important; }
.q-tab { text-transform: none !important; font-family: var(--font-ui) !important;
  font-size: 12.5px !important; min-height: 36px !important; padding: 0 14px !important; }
.q-tab--active { color: var(--ink) !important; }
.q-separator { background: var(--line-soft) !important; }
.q-checkbox__inner--truthy, .q-toggle__inner--truthy { color: var(--patina) !important; }
.q-slider__track-container { border-radius: 0 !important; }
.q-table { background: transparent !important; }
.q-table thead th {
  font-size: 10.5px !important; letter-spacing: .06em; color: var(--muted) !important;
  font-weight: 500 !important; border-bottom: 1px solid var(--line) !important;
}
.q-table tbody td {
  font-size: 12.5px !important; font-family: var(--font-num);
  border-bottom: 1px solid var(--line-soft) !important; color: var(--ink2);
}
.q-table tbody tr:hover { background: var(--panel2) !important; }
.q-uploader {
  background: var(--sunk) !important; border: 1px dashed var(--line) !important;
  border-radius: var(--r) !important; box-shadow: none !important; color: var(--muted);
}
.q-uploader__header { background: transparent !important; }
.q-uploader__list { background: transparent !important; }
.q-linear-progress { border-radius: 0 !important; }
.q-expansion-item__container > .q-item { min-height: 38px !important; }
.q-notification { border-radius: var(--r) !important; font-family: var(--font-ui) !important; }

.ss-btn-primary {
  background: var(--patina) !important; color: #08110F !important;
  font-weight: 600 !important; letter-spacing: .04em; padding: 7px 18px !important;
}
body.body--dark .ss-btn-primary { color: #08110F !important; }
.ss-btn-primary:hover { filter: brightness(1.08); }
.ss-btn-ghost { border: 1px solid var(--line) !important; color: var(--ink2) !important; padding: 6px 14px !important; }
.ss-btn-ghost:hover { border-color: var(--muted) !important; color: var(--ink) !important; }

/* 图表区在浅色主题下也保持深色：频谱/频谱图的判读依赖暗背景，
   浅底会把 −100 dB 的弱线直接吃掉。相当于示波器的屏幕，不跟着纸张颜色走。 */
.ss-chart {
  background: #14191B; border: 1px solid #2C3438; border-radius: var(--r);
  padding: 8px; overflow: hidden;
}

.ss-param { padding: 7px 0; border-bottom: 1px dashed var(--line-soft); }
.ss-param:last-child { border-bottom: none; }
.ss-param-l { font-size: 12.5px; color: var(--ink); display: flex; align-items: center; gap: 6px; }
.ss-param-d { font-size: 11px; line-height: 1.55; color: var(--muted); margin-top: 2px; }
.ss-param-ctl { min-width: 150px; }

.ss-term { border-bottom: 1px solid var(--line-soft); padding: 12px 0; }
.ss-term-t { font-size: 13.5px; font-weight: 600; display: flex; gap: 8px; align-items: baseline; }
.ss-term-s { font-size: 11.5px; color: var(--brass); margin-left: auto; font-family: var(--font-num); }

.ss-status { display: flex; align-items: center; gap: 10px; font-size: 12px; color: var(--muted); font-family: var(--font-num); }
.ss-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--muted); flex: 0 0 6px; }
.ss-dot.run { background: var(--patina); animation: sspulse 1.2s ease-in-out infinite; }
.ss-dot.done { background: var(--good); }
.ss-dot.err { background: var(--alert); }
@keyframes sspulse { 0%,100% { opacity: 1; } 50% { opacity: .25; } }

.ss-empty {
  border: 1px dashed var(--line); border-radius: var(--r); padding: 34px 20px;
  text-align: center; color: var(--muted); font-size: 12.5px; line-height: 1.8;
}
.ss-mono-cell { font-family: var(--font-num); }
.ss-body strong { color: var(--ink); font-weight: 600; }
.ss-body code, .ss-note code {
  font-family: var(--font-num); font-size: .93em; padding: 0 3px;
  background: var(--sunk); border: 1px solid var(--line-soft); border-radius: 1px;
  color: var(--brass);
}

/* 整页拖放提示层：拖入时压暗背景并给一个明确的落点说明 */
.ss-dropzone {
  position: fixed; inset: 0; z-index: 9998; display: none;
  background: rgba(10, 14, 13, .82); backdrop-filter: blur(2px);
  align-items: center; justify-content: center; pointer-events: none;
}
.ss-dropzone.on { display: flex; }
.ss-dropzone-in {
  border: 2px dashed var(--patina); padding: 34px 46px; text-align: center;
  background: var(--panel); border-radius: 2px;
}
.ss-dropzone-t { font-size: 19px; letter-spacing: .06em; color: var(--ink); font-weight: 600; }
.ss-dropzone-s { margin-top: 6px; font-size: 12.5px; color: var(--muted); }

/* 上传器：压成一个按钮，不要 Quasar 默认的大方块 */
.ss-uploader .q-uploader__header {
  background: transparent !important; border: 1px dashed var(--line);
  min-height: 34px; padding: 0 10px;
}
.ss-uploader .q-uploader__header-content { padding: 0 !important; }
.ss-uploader .q-uploader__subtitle { display: none !important; }
.ss-uploader .q-uploader__header { min-height: 34px !important; height: 34px; }
.ss-uploader .q-uploader__list { display: none !important; }
.ss-uploader .q-btn { font-size: 11.5px !important; }
.ss-uploader .q-uploader__header .q-btn__content { font-size: 11.5px; }

/* 主题切换按钮：Quasar 默认给它 text-primary（亮蓝），与"黄铜/铜绿"双强调色体系冲突，
   统一降为 muted，hover 时才亮起来。 */
.ss-rail .q-btn.text-primary, .ss-theme-btn { color: var(--muted) !important; }
.ss-rail .q-btn.text-primary:hover, .ss-theme-btn:hover {
  color: var(--ink) !important; background: var(--panel2);
}
.ss-theme-btn { font-size: 11.5px; letter-spacing: .04em; padding: 2px 6px; }

/* Quasar 表格底栏是英文（"Records per page / of"）且与本工具的分页无关，
   表格数据量小，全部行直接展开，底栏一律隐藏，避免中英混排。 */
.ss-page .q-table__bottom { display: none !important; }
.ss-page .q-table thead th {
  font-size: 10.5px; letter-spacing: .06em; color: var(--muted);
  font-weight: 600; border-bottom: 1px solid var(--line) !important;
}
.ss-page .q-table tbody td { font-family: var(--font-num); font-size: 12.5px; }

/* 窄屏：侧栏收成图标条，页面留白收紧 */
@media (max-width: 980px) {
  .ss-rail { width: 58px; flex: 0 0 58px; padding-top: 14px; }
  .ss-rail-head { padding: 0 0 14px 0; display: flex; justify-content: center; }
  .ss-rail-head .ss-brand { font-size: 11px; letter-spacing: .02em; }
  .ss-rail-head .ss-sub { display: none; }
  .ss-nav { padding: 8px 4px; }
  .ss-nav-item { justify-content: center; padding: 10px 0; gap: 0; }
  .ss-nav-label, .ss-nav-idx { display: none; }
  .ss-rail-foot { display: none; }
  .ss-page { padding: 18px 14px 48px 14px; }
  .ss-card { padding: 13px 13px; }
  .ss-h1 { font-size: 18px; }
}
@media (max-width: 620px) {
  .ss-tile-v { font-size: 16px; }
  .ss-param-ctl { min-width: 120px; }
  .ss-card-h { flex-wrap: wrap; gap: 4px 10px; }
  .ss-card-h > * { min-width: 0; }
  .ss-card-h .ss-note { flex: 1 1 100%; }
  .ss-page { padding: 14px 10px 44px 10px; }
  .ss-row { flex-wrap: wrap !important; }
  .ss-page .q-field, .ss-page .q-select { max-width: 100%; }
}
""".replace("__LIGHT__", _vars(LIGHT)).replace("__DARK__", _vars(DARK)) \
    .replace("__FONT_UI__", FONT_UI).replace("__FONT_NUM__", FONT_NUM)


def head_html() -> str:
    """注入 <head>：字体、CSS、以及一点 Quasar 主题变量覆盖。"""
    return (
        "<style>" + CSS + "</style>"
        "<style>body.body--dark { --q-dark: " + DARK["panel"] + "; }"
        ".q-loading__box { border-radius: 2px !important; }</style>"
    )


# --------------------------------------------------------------------------
# 整页拖放上传
# --------------------------------------------------------------------------
# 为什么不用 Quasar 自带的拖放：q-uploader 只在自己那块 34px 高的标题栏上挂了
# dnd 监听，用户把文件拖到页面中间（甚至拖到那个输入框上）时浏览器毫无反应，
# 直接当"打开本地文件"处理。这段脚本在 window 上兜底：拦住浏览器默认行为、
# 把文件 POST 到 /api/upload、再用 emitEvent 把落地路径送回 Python 侧的 ui.on。
DROP_JS = """
<script>
(function () {
  function boot() {
    // nicegui.js 是普通脚本（非 module），它的 emitEvent / mounted_app 在全局脚本作用域里，
    // 因此这里必须用裸标识符判断，不能写成 window.emitEvent。
    if (typeof emitEvent !== 'function' || typeof mounted_app !== 'object' || !mounted_app) {
      setTimeout(boot, 120);   // NiceGUI 的 socket 还没就绪
      return;
    }
    if (window.__ssDropBound) return;
    window.__ssDropBound = true;
    var fire = function (name, arg) { emitEvent(name, arg); };

    var AUDIO = ['wav','flac','mp3','aif','aiff','aifc','caf','m4a','mp4','ogg','oga','opus',
                 'wv','tta','dsf','dff','ape','w64','au','snd','webm','mkv','mka','mp2','ac3','dts'];
    var zone = document.createElement('div');
    zone.className = 'ss-dropzone';
    zone.innerHTML = '<div class="ss-dropzone-in"><div class="ss-dropzone-t">松手即载入</div>' +
                     '<div class="ss-dropzone-s">音频文件会直接上传并开始分析</div></div>';
    document.body.appendChild(zone);

    var depth = 0, busy = false;

    function hasFiles(e) {
      var dt = e.dataTransfer;
      if (!dt) return false;
      if (dt.types && Array.prototype.indexOf.call(dt.types, 'Files') >= 0) return true;
      return !!(dt.items && dt.items.length && dt.items[0].kind === 'file');
    }
    function show() { zone.classList.add('on'); }
    function hide() { depth = 0; zone.classList.remove('on'); }

    window.addEventListener('dragenter', function (e) {
      if (!hasFiles(e)) return;
      e.preventDefault(); depth++; show();
    }, true);
    window.addEventListener('dragover', function (e) {
      if (!hasFiles(e)) return;
      e.preventDefault(); e.dataTransfer.dropEffect = 'copy';
    }, true);
    window.addEventListener('dragleave', function (e) {
      if (!hasFiles(e)) return;
      depth = Math.max(0, depth - 1);
      if (depth === 0) hide();
    }, true);
    window.addEventListener('drop', function (e) {
      if (!hasFiles(e)) return;
      e.preventDefault(); e.stopPropagation(); hide();
      var f = e.dataTransfer.files && e.dataTransfer.files[0];
      if (!f) return;
      var ext = (f.name.split('.').pop() || '').toLowerCase();
      if (AUDIO.indexOf(ext) < 0) {
        fire('ssdrop-error', '不认识的音频扩展名：.' + ext);
        return;
      }
      if (busy) { fire('ssdrop-error', '上一个文件还在上传'); return; }
      busy = true;
      var fd = new FormData();
      fd.append('file', f, f.name);
      var prefix = window.path_prefix || '';
      fetch(prefix + '/api/upload', { method: 'POST', body: fd })
        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
        .then(function (res) {
          busy = false;
          if (res.ok && res.j && res.j.path) fire('ssdrop', res.j.path);
          else fire('ssdrop-error', (res.j && res.j.detail) || '服务端拒绝了上传');
        })
        .catch(function (err) {
          busy = false;
          fire('ssdrop-error', String(err));
        });
    }, true);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
</script>
"""


def drop_html() -> str:
    """拖放脚本单独暴露，页面按需注入（只有带文件选择器的页面才需要）。"""
    return DROP_JS


def dark_enabled() -> bool:
    """默认深色：频谱图与波形在深底上判读更准。"""
    return True
