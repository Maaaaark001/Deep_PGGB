# -*- coding: utf-8 -*-
"""把 blocks.json 渲染成 docx（不依赖 Univer）。

原先的渲染路径是 univer_unit -> render.js -> univer_export -> embed_figures.py。
本轮起 Univer 的 doc 工具不在工具集里，于是用 python-docx 直接重建同一套版式：
标题层级、表格样式、图占位符（由 embed_figures.py 换成真实 DrawingML）。
"""
import json
import os
import re
import shutil
import sys
import zipfile

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

HERE = os.path.dirname(os.path.abspath(__file__))
BLOCKS = os.path.join(HERE, "blocks.json")
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "py_raw.docx")

LATIN = "Times New Roman"
SONG = "宋体"
HEI = "黑体"
TEXT_W_TWIPS = 9026          # A4 宽 11906 - 左右边距各 1440

DRAWING_NS = {
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
}


def cjk(run, east, size, bold=False, color="000000", latin=LATIN):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = RGBColor.from_string(color)
    rpr = run._element.get_or_add_rPr()
    rf = rpr.find(qn("w:rFonts"))
    if rf is None:
        rf = OxmlElement("w:rFonts")
        rpr.insert(0, rf)
    rf.set(qn("w:ascii"), latin)
    rf.set(qn("w:hAnsi"), latin)
    rf.set(qn("w:cs"), latin)
    rf.set(qn("w:eastAsia"), east)


def para(doc, text, *, east=SONG, size=10.5, bold=False, align=None,
         before=0.0, after=0.0, line=1.5, indent_chars=0, keep_next=False,
         page_break=False, style=None):
    p = doc.add_paragraph()
    if style:
        p.style = doc.styles[style]
    pf = p.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing = line
    pf.keep_with_next = keep_next
    if page_break:
        pf.page_break_before = True
    if align is not None:
        p.alignment = align
    if indent_chars:
        # 首行缩进按“字符”给，Word 才会随字号缩放；twips 只是兜底。
        ppr = p._p.get_or_add_pPr()
        ind = ppr.find(qn("w:ind"))
        if ind is None:
            ind = OxmlElement("w:ind")
            ppr.append(ind)
        ind.set(qn("w:firstLineChars"), str(indent_chars * 100))
        ind.set(qn("w:firstLine"), str(int(indent_chars * size * 20)))
    add_rich(p, text or "", east, size, bold)
    return p


def add_rich(p, text, east, size, bold=False):
    """写入文字，并把 **…** 变成粗体 run。

    源文（blocks.json）用 markdown 的星号标重点；Univer 的渲染器不解析它，
    所以早期版本靠“正文里不许出现 **”这条规矩回避。这里直接解析，
    既保留强调，又不会在 Word 里显示出星号。
    """
    for i, seg in enumerate(re.split(r"\*\*(.+?)\*\*", text)):
        if not seg:
            continue
        cjk(p.add_run(seg), east, size, bold or (i % 2 == 1))


def borders(table, sz=4, color="A6A6A6"):
    tblpr = table._tbl.tblPr
    bd = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement("w:" + edge)
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(sz))
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), color)
        bd.append(el)
    tblpr.append(bd)


def cell_margins(table, top=45, bottom=45, left=135, right=135):
    tblpr = table._tbl.tblPr
    mar = OxmlElement("w:tblCellMar")
    for tag, val in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        el = OxmlElement("w:" + tag)
        el.set(qn("w:w"), str(val))
        el.set(qn("w:type"), "dxa")
        mar.append(el)
    tblpr.append(mar)


def add_table(doc, rows, widths=None, header=1):
    ncol = len(rows[0])
    t = doc.add_table(rows=len(rows), cols=ncol)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    borders(t)
    cell_margins(t)
    if widths:
        k = TEXT_W_TWIPS / float(sum(widths))
        colw = [int(w * k) for w in widths]
    else:
        colw = [TEXT_W_TWIPS // ncol] * ncol
    tblpr = t._tbl.tblPr
    tw = OxmlElement("w:tblW")
    tw.set(qn("w:w"), str(sum(colw)))
    tw.set(qn("w:type"), "dxa")
    tblpr.append(tw)
    lay = OxmlElement("w:tblLayout")
    lay.set(qn("w:type"), "fixed")
    tblpr.append(lay)
    # tcW 在固定布局下未必被采用；把 tblGrid 的 gridCol 一并写成同一组宽度，
    # 否则渲染器按等宽网格排，第一列会把 "Deep_PGGB" 折成两行。
    for c, w in enumerate(colw):
        t.columns[c].width = Pt(w / 20.0)
    for r, row in enumerate(rows):
        tr = t.rows[r]._tr
        trpr = tr.get_or_add_trPr()
        trpr.append(OxmlElement("w:cantSplit"))
        if r < header:
            # 表头行在跨页时重复：cantSplit 只能防"一行被劈开"，
            # 整表超过一页时 Word 仍会从中间断开，没有 tblHeader 就会断成
            # "第一页只剩表头、第二页没有表头"。
            trpr.append(OxmlElement("w:tblHeader"))
        for c in range(ncol):
            cell = t.cell(r, c)
            cell.width = Pt(colw[c] / 20.0)
            txt = row[c] if c < len(row) else ""
            p = cell.paragraphs[0]
            pf = p.paragraph_format
            pf.space_before = Pt(0)
            pf.space_after = Pt(0)
            pf.line_spacing = 1.0
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if (r < header or c > 0) else WD_ALIGN_PARAGRAPH.LEFT
            cjk(p.add_run(str(txt)), SONG, 8.5, bold=(r < header))
    return t


def _declare_drawing_ns(path):
    """把 DrawingML 的三个命名空间声明到 <w:document> 根上。

    embed_figures.py 注入的 <w:drawing> 片段直接使用 wp:/a:/pic: 前缀；python-docx
    的根只声明 w、r 与 wp14，于是片段成了未绑定前缀，Word 与 lxml 都拒绝解析。
    """
    tmp = path + ".tmp"
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                txt = data.decode("utf-8")
                start = txt.find("<w:document")
                end = txt.find(">", start) + 1
                root = txt[start:end]
                add = "".join(' xmlns:%s="%s"' % (k, v) for k, v in DRAWING_NS.items()
                              if ("xmlns:%s=" % k) not in root)
                if add:
                    txt = txt[:start] + root[:-1].rstrip() + add + ">" + txt[end:]
                data = txt.encode("utf-8")
            zout.writestr(item, data)
    shutil.move(tmp, path)


def main():
    spec = json.load(open(BLOCKS, encoding="utf-8"))
    doc = Document()
    sec = doc.sections[0]
    sec.page_width = Pt(595.3)
    sec.page_height = Pt(841.9)
    for attr in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, attr, Pt(72))

    normal = doc.styles["Normal"]
    normal.font.name = LATIN
    normal.font.size = Pt(10.5)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), SONG)

    stats = {"blocks": len(spec), "tables": 0, "figs": 0, "heads": 0}
    pending_break = False
    for b in spec:
        kind = b.get("t")
        if kind == "pb":
            pending_break = True
            continue
        if kind == "fig":
            name = os.path.basename(b["src"]).replace(".png", "")
            para(doc, "@@FIG:%s|%dx%d@@" % (name, b["w"], b["h"]),
                 align=WD_ALIGN_PARAGRAPH.CENTER, before=10, after=2,
                 line=1.0, keep_next=True)
            stats["figs"] += 1
            if b.get("cap"):
                para(doc, b["cap"], size=9, align=WD_ALIGN_PARAGRAPH.CENTER,
                     before=4, after=10, line=1.15)
        elif kind == "table":
            if b.get("cap"):
                para(doc, b["cap"], size=9, align=WD_ALIGN_PARAGRAPH.CENTER,
                     before=6, after=4, line=1.15, keep_next=True)
            add_table(doc, b["rows"], b.get("widths"), b.get("header", 1))
            stats["tables"] += 1
            para(doc, "", size=9, line=1.0, after=6)
        elif kind == "title":
            para(doc, b["x"], east=HEI, size=16, bold=True,
                 align=WD_ALIGN_PARAGRAPH.CENTER, after=14, line=1.25,
                 page_break=pending_break, style="Title")
            stats["heads"] += 1
        elif kind in ("h1", "h2", "h3"):
            size, before, after = {"h1": (13, 16, 7), "h2": (11.5, 11, 5),
                                   "h3": (10.5, 8, 3)}[kind]
            para(doc, b["x"], east=HEI, size=size, bold=True, before=before,
                 after=after, line=1.25, keep_next=True, page_break=pending_break,
                 style={"h1": "Heading 1", "h2": "Heading 2", "h3": "Heading 3"}[kind])
            stats["heads"] += 1
        elif kind == "caption":
            para(doc, b["x"], size=9, align=WD_ALIGN_PARAGRAPH.CENTER,
                 before=4, after=10, line=1.15, page_break=pending_break)
        elif kind == "ref":
            para(doc, b["x"], size=9, before=0, after=2, line=1.2,
                 page_break=pending_break)
        else:
            para(doc, b["x"], size=10.5, align=WD_ALIGN_PARAGRAPH.JUSTIFY,
                 after=0, line=1.5, indent_chars=2, page_break=pending_break)
        pending_break = False

    doc.core_properties.title = "Deep_PGGB：以精确有理倍率实现 300 dB 数值保真的分块砖墙式采样率转换"
    doc.core_properties.author = "SonarSRC Project"
    doc.save(OUT)
    _declare_drawing_ns(OUT)
    print("wrote", OUT, stats)


if __name__ == "__main__":
    main()
