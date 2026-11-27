# -*- coding: utf-8 -*-
"""Render the certified-null manuscript to docx.

The directive layer is a small superset of the one used by work/paper/build_docx.py
so the two manuscripts share a look, but the renderer is new: figures go in through
python-docx's own add_picture, which writes a correctly namespaced DrawingML.  The
previous pipeline injected a hand-written <w:drawing> whose <a:graphic> relied on
namespace declarations that the exporter had dropped, and Word refused the file
("Namespace prefix a on graphic is not defined").

Directives
    @title @author @affil @corr @date
    @entitle @enauthor @enaffil @ensub @enbody @enkw @kw @abs
    @eq N | body
    @fig file.png | 图 N | caption
    @table N | caption          followed by a pipe table
    @ref text
    @code ... @code
    ## heading / ### subheading
Everything else is body text.  Inline markup: **bold**, _{sub}, ^{sup}.
"""
import os
import re
import sys

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

HERE = os.path.dirname(os.path.abspath(__file__))
FIGDIR = os.path.join(HERE, "figures")
OUT = os.path.join(HERE, "certified_null_paper.docx")

LATIN = "Times New Roman"
SONG = "宋体"
HEI = "黑体"
MONO = "Consolas"

PAGE_W = 595.3          # A4 in points
PAGE_H = 841.9
MARGIN = 72.0           # 1 inch all round
TEXT_W = PAGE_W - 2 * MARGIN     # 451.3 pt
TEXT_W_TWIPS = int(TEXT_W * 20)  # 9026

TOKEN_RE = re.compile(r"(\*\*.+?\*\*|_\{[^{}]*\}|\^\{[^{}]*\})")


def cjk(run, east, size, bold=False, color="000000", latin=LATIN, italic=False):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
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


def add_rich(p, text, east, size, bold=False, italic=False, latin=LATIN,
             color="000000"):
    for seg in TOKEN_RE.split(text or ""):
        if not seg:
            continue
        sub = sup = False
        bold_seg = False
        if seg.startswith("**") and seg.endswith("**") and len(seg) > 4:
            seg = seg[2:-2]
            bold_seg = True
        elif seg.startswith("_{") and seg.endswith("}"):
            seg = seg[2:-1]
            sub = True
        elif seg.startswith("^{") and seg.endswith("}"):
            seg = seg[2:-1]
            sup = True
        run = p.add_run(seg)
        cjk(run, east, size, bold or bold_seg, italic=italic, latin=latin,
            color=color)
        if sub:
            run.font.subscript = True
        if sup:
            run.font.superscript = True


def para(doc, text, *, east=SONG, size=10.5, bold=False, align=None,
         before=0.0, after=0.0, line=1.5, indent_chars=0, keep_next=False,
         page_break=False, style=None, latin=LATIN, italic=False, color="000000"):
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
        ppr = p._p.get_or_add_pPr()
        ind = ppr.find(qn("w:ind"))
        if ind is None:
            ind = OxmlElement("w:ind")
            ppr.append(ind)
        ind.set(qn("w:firstLineChars"), str(indent_chars * 100))
        ind.set(qn("w:firstLine"), str(int(indent_chars * size * 20)))
    add_rich(p, text, east, size, bold, italic, latin, color)
    return p


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


def cell_margins(table, top=22, bottom=22, left=110, right=110):
    tblpr = table._tbl.tblPr
    mar = OxmlElement("w:tblCellMar")
    for tag, val in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        el = OxmlElement("w:" + tag)
        el.set(qn("w:w"), str(val))
        el.set(qn("w:type"), "dxa")
        mar.append(el)
    tblpr.append(mar)


def set_grid(table, colw):
    """Write tblGrid/gridCol; without it Word ignores every tcW and equalises."""
    tbl = table._tbl
    grid = tbl.find(qn("w:tblGrid"))
    if grid is not None:
        tbl.remove(grid)
    grid = OxmlElement("w:tblGrid")
    for w in colw:
        gc = OxmlElement("w:gridCol")
        gc.set(qn("w:w"), str(w))
        grid.append(gc)
    tblPr = tbl.tblPr
    tblPr.addnext(grid)


def add_table(doc, rows, fs=8.6, aligns=None, widths=None):
    ncol = max(len(r) for r in rows)
    t = doc.add_table(rows=len(rows), cols=ncol)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    borders(t)
    cell_margins(t)
    if widths is None:
        colw = [TEXT_W_TWIPS // ncol] * ncol
    else:
        tot = float(sum(widths))
        colw = [int(TEXT_W_TWIPS * w / tot) for w in widths]
    tblpr = t._tbl.tblPr
    tw = OxmlElement("w:tblW")
    tw.set(qn("w:w"), str(sum(colw)))
    tw.set(qn("w:type"), "dxa")
    tblpr.append(tw)
    lay = OxmlElement("w:tblLayout")
    lay.set(qn("w:type"), "fixed")
    tblpr.append(lay)
    set_grid(t, colw)
    for c, w in enumerate(colw):
        t.columns[c].width = Pt(w / 20.0)
    for r, row in enumerate(rows):
        tr = t.rows[r]._tr
        trpr = tr.get_or_add_trPr()
        trpr.append(OxmlElement("w:cantSplit"))
        if r == 0:
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
            a = (aligns[c] if aligns and c < len(aligns) else ("l" if c == 0 else "c"))
            if r == 0:
                a = "c"
            p.alignment = {"l": WD_ALIGN_PARAGRAPH.LEFT,
                           "c": WD_ALIGN_PARAGRAPH.CENTER,
                           "r": WD_ALIGN_PARAGRAPH.RIGHT}[a]
            add_rich(p, str(txt), SONG, fs, bold=(r == 0))
            if r == 0:
                tcpr = cell._tc.get_or_add_tcPr()
                shd = OxmlElement("w:shd")
                shd.set(qn("w:val"), "clear")
                shd.set(qn("w:color"), "auto")
                shd.set(qn("w:fill"), "F2F2F2")
                tcpr.append(shd)
    for r in range(len(rows) - 1):
        for c in range(ncol):
            for cp in t.cell(r, c).paragraphs:
                cp.paragraph_format.keep_with_next = True
    return t


def split_row(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def add_figure(doc, name, label, caption, width_pt=TEXT_W):
    """Inline picture through python-docx, so the DrawingML is namespaced properly."""
    path = os.path.join(FIGDIR, name)
    if not os.path.exists(path):
        raise SystemExit("missing figure: " + path)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pf = p.paragraph_format
    pf.space_before = Pt(9)
    pf.space_after = Pt(3)
    pf.line_spacing = 1.0
    pf.keep_with_next = True
    run = p.add_run()
    run.add_picture(path, width=Pt(width_pt))
    return p


def add_page_number_footer(section):
    footer = section.footer
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    cjk(run, SONG, 9, color="595959")
    for kind, payload in (("begin", None), ("instr", " PAGE "), ("separate", None),
                          ("text", "1"), ("end", None)):
        if kind == "instr":
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = payload
        elif kind == "text":
            el = OxmlElement("w:t")
            el.text = payload
        else:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), kind)
        run._r.append(el)


def main():
    src = []
    for fn in ("paper_a.md", "paper_b.md"):
        path = os.path.join(HERE, fn)
        if os.path.exists(path):
            src.append(open(path, encoding="utf-8").read())
    lines = "\n".join(src).split("\n")

    doc = Document()
    sec = doc.sections[0]
    sec.page_width = Pt(PAGE_W)
    sec.page_height = Pt(PAGE_H)
    for attr in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, attr, Pt(MARGIN))
    add_page_number_footer(sec)

    tstyle = doc.styles["Title"].element
    tpr = tstyle.find(qn("w:pPr"))
    if tpr is not None:
        for bd in tpr.findall(qn("w:pBdr")):
            tpr.remove(bd)

    normal = doc.styles["Normal"]
    normal.font.name = LATIN
    normal.font.size = Pt(10.5)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), SONG)

    stats = {"figs": 0, "tables": 0, "eqs": 0, "refs": 0, "heads": 0,
             "paras": 0, "chars": 0}
    fig_no = []
    tbl_no = []
    i = 0
    while i < len(lines):
        s = lines[i].rstrip()
        st = s.strip()

        if not st:
            i += 1
            continue

        if st.startswith("@code"):
            i += 1
            buf = []
            while i < len(lines) and not lines[i].strip().startswith("@code"):
                buf.append(lines[i])
                i += 1
            i += 1
            p = doc.add_paragraph()
            pf = p.paragraph_format
            pf.left_indent = Cm(0.5)
            pf.space_before = Pt(4)
            pf.space_after = Pt(8)
            pf.line_spacing = 1.0
            run = p.add_run("\n".join(buf))
            run.font.name = MONO
            run._element.get_or_add_rPr().get_or_add_rFonts().set(
                qn("w:eastAsia"), MONO)
            run.font.size = Pt(8.2)
            continue

        if st.startswith("@fig "):
            parts = [x.strip() for x in st[5:].split("|")]
            name, label, cap = parts[0], parts[1], "|".join(parts[2:])
            pb = label.endswith(" pb")
            if pb:
                label = label[:-3].strip()
            m = re.search(r"(\d+)", label)
            if m:
                fig_no.append(int(m.group(1)))
            fig_p = add_figure(doc, name, label, cap)
            if pb:
                fig_p.paragraph_format.page_break_before = True
            cap_p = para(doc, "%s  %s" % (label, cap), size=9,
                         align=WD_ALIGN_PARAGRAPH.JUSTIFY, before=0, after=10,
                         line=1.18)
            cap_p.paragraph_format.keep_together = True
            stats["figs"] += 1
            i += 1
            continue

        if st.startswith("@table "):
            parts = [x.strip() for x in st[7:].split("|", 1)]
            label, cap = parts[0], (parts[1] if len(parts) > 1 else "")
            tbl_no.append(int(label))
            i += 1
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i])
                i += 1
            aligns = None
            if len(rows) > 1 and re.match(r"^\|[\s:|-]+\|$", rows[1].strip()):
                sep = split_row(rows[1])
                aligns = ["r" if c.endswith(":") else
                          "c" if (c.startswith(":") and c.endswith(":")) else "l"
                          for c in sep]
                del rows[1]
            para(doc, "表 %s  %s" % (label, cap), size=9,
                 align=WD_ALIGN_PARAGRAPH.CENTER, before=8, after=4, line=1.15,
                 keep_next=True)
            add_table(doc, [split_row(r) for r in rows], 8.6, aligns)
            para(doc, "", size=6, line=1.0, after=6)
            stats["tables"] += 1
            continue

        if st.startswith("@eq "):
            m = re.match(r"^@eq\s+(\S+)\s*\|\s*(.*)$", st)
            num, body = m.group(1), m.group(2)
            p = doc.add_paragraph()
            pf = p.paragraph_format
            pf.space_before = Pt(6)
            pf.space_after = Pt(6)
            pf.line_spacing = 1.2
            pf.tab_stops.add_tab_stop(Pt(TEXT_W / 2), WD_TAB_ALIGNMENT.CENTER)
            pf.tab_stops.add_tab_stop(Pt(TEXT_W), WD_TAB_ALIGNMENT.RIGHT)
            run = p.add_run("\t")
            cjk(run, SONG, 10.5)
            add_rich(p, body, SONG, 10.5, italic=False)
            run = p.add_run("\t(" + num + ")")
            cjk(run, SONG, 10.5)
            stats["eqs"] += 1
            i += 1
            continue

        if st.startswith("@ref "):
            para(doc, st[5:], size=8.8, before=0, after=0, line=1.12,
                 align=WD_ALIGN_PARAGRAPH.JUSTIFY)
            stats["refs"] += 1
            i += 1
            continue

        if st.startswith("@title "):
            para(doc, st[7:], east=HEI, size=16, bold=True,
                 align=WD_ALIGN_PARAGRAPH.CENTER, before=150, after=4,
                 line=1.25, style="Title")
            stats["heads"] += 1
            i += 1
            continue

        for tag, east, size, before, after, line, align in (
                ("@subtitle ", HEI, 12, 0, 12, 1.2, WD_ALIGN_PARAGRAPH.CENTER),
                ("@author ", SONG, 11.5, 2, 1, 1.2, WD_ALIGN_PARAGRAPH.CENTER),
                ("@affil ", SONG, 9.5, 0, 1, 1.2, WD_ALIGN_PARAGRAPH.CENTER),
                ("@corr ", SONG, 9, 0, 1, 1.2, WD_ALIGN_PARAGRAPH.CENTER),
                ("@date ", SONG, 9, 0, 10, 1.2, WD_ALIGN_PARAGRAPH.CENTER)):
            if st.startswith(tag):
                para(doc, st[len(tag):], east=east, size=size, before=before,
                     after=after, line=line, align=align,
                     bold=(tag == "@subtitle "))
                break
        else:
            if st.startswith("@entitle "):
                para(doc, st[9:], east=HEI, size=12, bold=True,
                     align=WD_ALIGN_PARAGRAPH.CENTER, before=20, after=2,
                     line=1.2)
                i += 1
                continue
            if st.startswith("@enauthor "):
                para(doc, st[10:], size=11, bold=True,
                     align=WD_ALIGN_PARAGRAPH.CENTER, before=2, after=1, line=1.2)
                i += 1
                continue
            if st.startswith("@enaffil "):
                para(doc, st[9:], size=9.5, align=WD_ALIGN_PARAGRAPH.CENTER,
                     before=0, after=10, line=1.2)
                i += 1
                continue
            if st.startswith("@ensub "):
                para(doc, st[7:], size=10.5, bold=True,
                     align=WD_ALIGN_PARAGRAPH.LEFT, before=4, after=3, line=1.2)
                i += 1
                continue
            if st.startswith("@enbody "):
                para(doc, st[8:], size=9.5, align=WD_ALIGN_PARAGRAPH.JUSTIFY,
                     before=0, after=3, line=1.28)
                i += 1
                continue
            if st.startswith("@enkw "):
                para(doc, st[6:], size=9.5, align=WD_ALIGN_PARAGRAPH.JUSTIFY,
                     before=2, after=12, line=1.28)
                i += 1
                continue
            if st.startswith("@abs "):
                para(doc, st[5:], size=9.5, align=WD_ALIGN_PARAGRAPH.JUSTIFY,
                     before=2, after=3, line=1.3)
                i += 1
                continue
            if st.startswith("@kw "):
                para(doc, st[4:], size=9.5, align=WD_ALIGN_PARAGRAPH.JUSTIFY,
                     before=4, after=12, line=1.3)
                i += 1
                continue
            if st.startswith("## "):
                para(doc, st[3:], east=HEI, size=13, bold=True, before=16,
                     after=7, line=1.25, keep_next=True, style="Heading 1")
                stats["heads"] += 1
                i += 1
                continue
            if st.startswith("### "):
                para(doc, st[4:], east=HEI, size=11.5, bold=True, before=11,
                     after=5, line=1.25, keep_next=True, style="Heading 2")
                stats["heads"] += 1
                i += 1
                continue
            if st == "---":
                i += 1
                continue

            para(doc, st, size=10.5, align=WD_ALIGN_PARAGRAPH.JUSTIFY,
                 after=0, line=1.5, indent_chars=2)
            stats["paras"] += 1
            stats["chars"] += len(st)
            i += 1
            continue
        i += 1

    if fig_no != list(range(1, len(fig_no) + 1)):
        raise SystemExit("figure numbers are not sequential: %s" % fig_no)
    if tbl_no != list(range(1, len(tbl_no) + 1)):
        raise SystemExit("table numbers are not sequential: %s" % tbl_no)

    doc.core_properties.title = "可证零差：任意精度音频测量的地板归属与精度预算"
    doc.core_properties.author = "Maaaaark"
    doc.core_properties.subject = "任意精度测量；球算术；零差；泄漏；精度预算"
    doc.core_properties.keywords = ("certified null depth; arbitrary precision; "
                                    "interval arithmetic; spectral leakage")
    doc.save(OUT)
    print("wrote", OUT)
    print("stats", stats)
    print("figures", fig_no)
    print("tables", tbl_no)


if __name__ == "__main__":
    main()
