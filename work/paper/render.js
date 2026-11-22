
const fs = await import("node:fs");
const E = api.Enum;
const SRC = "C:/Users/Administrator/Documents/Python_Code/src/";
const spec = JSON.parse(fs.readFileSync(SRC + "work/paper/blocks.json", "utf8"));
// embed=true puts the real PNG in the unit (used for visual preview only);
// embed=false writes a placeholder that embed_figures.py turns into DrawingML,
// because the docx exporter drops base64 images.
const EMBED = JSON.parse(fs.readFileSync(SRC + "work/paper/render_cfg.json", "utf8")).embed;
const out = { blocks: spec.length, figs: 0, tables: 0, errs: [] };

const FONTS = { body: "宋体", head: "黑体", latin: "Times New Roman" };
const STYLE = {
  title: { ff: FONTS.head, fs: 16, bl: 1, cl: { rgb: "#000000" } },
  h1: { ff: FONTS.head, fs: 13, bl: 1, cl: { rgb: "#000000" } },
  h2: { ff: FONTS.head, fs: 11.5, bl: 1, cl: { rgb: "#000000" } },
  h3: { ff: FONTS.head, fs: 10.5, bl: 1, cl: { rgb: "#000000" } },
  body: { ff: FONTS.body, fs: 10.5, cl: { rgb: "#000000" } },
  caption: { ff: FONTS.body, fs: 9, cl: { rgb: "#1a1a1a" } },
  table: { ff: FONTS.body, fs: 9, cl: { rgb: "#000000" } },
  ref: { ff: FONTS.body, fs: 9, cl: { rgb: "#000000" } },
};

let PENDING_BREAK = false;   // set by a "pb" block, consumed by the next paragraph

function mk(text, kind) {
  const p = doc.appendParagraph(text || "");
  // namedStyleType gives the docx real Heading 1/2/3 outline levels, which is what
  // makes Word's navigation pane and any generated TOC work. Without it the
  // manuscript exports as a wall of Normal paragraphs.
  const NAMED = { title: E.NamedStyleType.TITLE, h1: E.NamedStyleType.HEADING_1,
                  h2: E.NamedStyleType.HEADING_2, h3: E.NamedStyleType.HEADING_3 };
  const st = { textStyle: STYLE[kind] || STYLE.body };
  if (PENDING_BREAK) { st.pageBreakBefore = E.BooleanNumber.TRUE; PENDING_BREAK = false; }
  if (NAMED[kind] !== undefined) st.namedStyleType = NAMED[kind];
  // NumberUnitType: POINT = 0, LINE = 1, CHARACTER = 2. Spacing must be POINT
  // (u:1 is a multiple of the line height and produces enormous gaps), and a
  // two-character first-line indent must be CHARACTER, not LINE.
  const PT = 0, CH = 2;
  if (kind === "title") { st.horizontalAlign = E.HorizontalAlign.CENTER; st.spaceBelow = { v: 14, u: PT }; st.lineSpacing = 1.25; }
  else if (kind === "h1") { st.spaceAbove = { v: 16, u: PT }; st.spaceBelow = { v: 7, u: PT }; st.keepNext = E.BooleanNumber.TRUE; }
  else if (kind === "h2") { st.spaceAbove = { v: 11, u: PT }; st.spaceBelow = { v: 5, u: PT }; st.keepNext = E.BooleanNumber.TRUE; }
  else if (kind === "h3") { st.spaceAbove = { v: 8, u: PT }; st.spaceBelow = { v: 3, u: PT }; st.keepNext = E.BooleanNumber.TRUE; }
  else if (kind === "caption") { st.horizontalAlign = E.HorizontalAlign.CENTER; st.spaceAbove = { v: 4, u: PT }; st.spaceBelow = { v: 10, u: PT }; st.lineSpacing = 1.15; }
  else if (kind === "ref") { st.lineSpacing = 1.2; st.spaceBelow = { v: 2, u: PT }; }
  else if (kind === "table") { st.lineSpacing = 1.0; st.spaceAbove = { v: 2, u: PT }; st.spaceBelow = { v: 2, u: PT }; }
  else { st.lineSpacing = 1.5; st.indentFirstLine = { v: 2, u: CH }; st.spaceBelow = { v: 0, u: PT }; st.horizontalAlign = E.HorizontalAlign.JUSTIFY; }
  p.setStyle(st);
  return p;
}

for (const b of spec) {
  try {
    if (b.t === "fig") {
      // The docx exporter drops base64 images, so the figure is left as a
      // placeholder paragraph here and swapped for real DrawingML by
      // embed_figures.py after export. The placeholder carries the size so the
      // post-processor does not have to guess the aspect ratio.
      const name = b.src.split("/").pop().replace(/\.png$/, "");
      const ph = doc.appendParagraph(EMBED ? "" : "@@FIG:" + name + "|" + b.w + "x" + b.h + "@@");
      const info = ph.getInfo();
      ph.setStyle({ horizontalAlign: E.HorizontalAlign.CENTER, spaceAbove: { v: 10, u: 0 }, spaceBelow: { v: 0, u: 0 }, lineSpacing: 1.0, keepNext: E.BooleanNumber.TRUE });
      if (EMBED) {
        const b64 = fs.readFileSync(SRC + b.src).toString("base64");
        await doc.insertImage({ source: b64, imageSourceType: E.ImageSourceType.BASE64,
          width: b.w, height: b.h, wrappingStyle: E.TextWrappingStyle.INLINE,
          textRange: { startOffset: info.startOffset, endOffset: info.startOffset, collapsed: true, segmentId: "" } });
      }
      out.figs++;
      if (b.cap) mk(b.cap, "caption");
    } else if (b.t === "pb") {
      // Force the next block onto a fresh page. Applied to the following paragraph
      // rather than an empty one, so no stray blank line lands at the page top.
      PENDING_BREAK = true;
    } else if (b.t === "table") {
      if (b.cap) { const c = mk(b.cap, "caption"); c.setStyle({ keepNext: E.BooleanNumber.TRUE }); }
      const hdr = b.header === undefined ? 1 : b.header;
      const t = doc.insertTableFromData(b.rows, { headerRowCount: hdr });
      if (t) {
        const rows = b.rows.length, cols = b.rows[0].length;
        // Thin grey grid: a table with Word's default 0.5 pt black border reads
        // as a spreadsheet pasted into a paper.
        t.setTableBorder({ preset: E.DocsTableBorderPreset.All, width: 0.5, color: "#a6a6a6" });
        // Cell margins are in PIXELS, not twips (30 px exports as 450 twips = 22.5 pt,
        // which turns every row into a 50 pt band). 3 px vertical / 9 px horizontal
        // gives the 2 pt breathing room a table actually needs.
        t.setDefaultCellMargin({ top: 3, bottom: 3, left: 9, right: 9 });
        for (let r = 0; r < rows; r++) {
          t.setRowHeight(r, 0, 0);  // TableRowHeightRule.AUTO

          for (let c = 0; c < cols; c++) {
            const cr = t.getCellContentRange(r, c);
            if (!cr) continue;
            const rg = doc.getTextRange(cr.startOffset, cr.endOffset, cr.segmentId || "");
            rg.setTextStyle({ ff: FONTS.body, fs: 8.5, cl: { rgb: "#000000" }, bl: r < hdr ? E.BooleanNumber.TRUE : E.BooleanNumber.FALSE });
          }
        }
        if (b.widths) {
          // Column widths are relative weights; scale them so the table spans the
          // 602 px text column instead of leaving a ragged right edge.
          const sum = b.widths.reduce((a, v) => a + v, 0);
          const k = 602 / sum;
          for (let c = 0; c < cols && c < b.widths.length; c++) t.setColumnWidth(c, Math.round(b.widths[c] * k));
        }
        if (hdr > 0) { try { t.pinHeaderRows(hdr); } catch (e) {} }
        out.tables++;
      }
      mk("", "caption");
    } else {
      mk(b.x, b.t);
    }
  } catch (e) { out.errs.push(b.t + ": " + String(e && e.message || e).slice(0, 160)); }
}
out.paras = doc.getParagraphs().length;
return out;
