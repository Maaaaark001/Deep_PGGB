import re, sys
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

BT = chr(96)
SRC = sys.argv[1]
DST = sys.argv[2]
text = open(SRC, encoding="utf-8").read().split("\n")

doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
sec.left_margin = sec.right_margin = Cm(2.1)
sec.top_margin = Cm(2.0)
sec.bottom_margin = Cm(1.9)

style = doc.styles["Normal"]
style.font.name = "Times New Roman"
style.font.size = Pt(10.5)
style.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
style.paragraph_format.space_after = Pt(4)
style.paragraph_format.line_spacing = 1.28

def set_east_asia(run, name="宋体"):
    run.font.name = "Times New Roman"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)

def shade(cell, hexcolor):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hexcolor)
    tcPr.append(shd)

PAT = "(" + r"\*\*[^*]+\*\*" + "|" + BT + "[^" + BT + "]+" + BT + ")"

def add_runs(p, s, base_size=10.5, bold=False, italic=False):
    for part in re.split(PAT, s):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            add_runs(p, part[2:-2], base_size, True, italic)
            continue
        if part.startswith(BT) and part.endswith(BT) and len(part) > 2:
            r = p.add_run(part[1:-1])
            r.font.name = "Consolas"
            r._element.rPr.rFonts.set(qn("w:eastAsia"), "Consolas")
            r.font.size = Pt(base_size - 0.7)
            r.bold = bold
            r.italic = italic
            continue
        r = p.add_run(part)
        r.bold = bold
        r.italic = italic
        set_east_asia(r)
        r.font.size = Pt(base_size)

def table_flags(t):
    trPr = t.rows[0]._tr.get_or_add_trPr()
    th = OxmlElement("w:tblHeader")
    th.set(qn("w:val"), "true")
    trPr.append(th)
    for row in t.rows:
        trPr = row._tr.get_or_add_trPr()
        trPr.append(OxmlElement("w:cantSplit"))

def add_table(rows, aligns):
    ncol = max(len(r) for r in rows)
    t = doc.add_table(rows=len(rows), cols=ncol)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, row in enumerate(rows):
        for j in range(ncol):
            cell = t.cell(i, j)
            txt = row[j].strip() if j < len(row) else ""
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(1)
            p.paragraph_format.line_spacing = 1.05
            if i == 0:
                add_runs(p, txt, 9.5)
                for r in p.runs:
                    r.bold = True
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                shade(cell, "E8EDF2")
            else:
                add_runs(p, txt, 9.5)
                a = aligns[j] if j < len(aligns) else "l"
                p.alignment = (WD_ALIGN_PARAGRAPH.RIGHT if a == "r"
                               else WD_ALIGN_PARAGRAPH.CENTER if a == "c"
                               else WD_ALIGN_PARAGRAPH.LEFT)
    table_flags(t)

i = 0
in_code = False
code_buf = []
FENCE = BT * 3
while i < len(text):
    line = text[i]
    s = line.rstrip()
    if s.startswith(FENCE):
        if not in_code:
            in_code = True; code_buf = []
        else:
            in_code = False
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.35)
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(6)
            p.paragraph_format.line_spacing = 1.0
            r = p.add_run("\n".join(code_buf))
            r.font.name = "Consolas"
            r._element.rPr.rFonts.set(qn("w:eastAsia"), "Consolas")
            r.font.size = Pt(8.2)
        i += 1
        continue
    if in_code:
        code_buf.append(line)
        i += 1
        continue
    if s.startswith("|") and i + 1 < len(text) and re.match(r"^\|[\s:|-]+\|$", text[i+1].strip()):
        sep = [c.strip() for c in text[i+1].strip().strip("|").split("|")]
        lines = []
        while i < len(text) and text[i].strip().startswith("|"):
            lines.append(text[i].strip())
            i += 1
        if len(lines) > 1 and re.match(r"^\|[\s:|-]+\|$", lines[1]):
            del lines[1]
        rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in lines]
        aligns = []
        for c in sep:
            aligns.append("r" if c.endswith(":") else "c" if (c.startswith(":") and c.endswith(":")) else "l")
        add_table(rows, aligns)
        doc.add_paragraph().paragraph_format.space_after = Pt(2)
        continue
    if s.startswith("#"):
        m = re.match(r"^(#{1,4})\s+(.*)$", s)
        lvl = len(m.group(1))
        txt = m.group(2)
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(14 if lvl <= 2 else 9)
        p.paragraph_format.space_after = Pt(5)
        p.paragraph_format.keep_with_next = True
        add_runs(p, txt, {1: 16.0, 2: 13.0, 3: 11.5, 4: 10.5}[lvl])
        for r in p.runs:
            r.bold = True
        if lvl == 1:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        i += 1
        continue
    if s.startswith("> "):
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Cm(0.5)
        add_runs(p, s[2:], 9.5)
        for r in p.runs:
            r.italic = True
        i += 1
        continue
    if s.strip() == "" or s.strip() == "---":
        i += 1
        continue
    if s.startswith("- "):
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Cm(0.55)
        p.paragraph_format.first_line_indent = Cm(-0.55)
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        add_runs(p, "\u2022  " + s[2:])
        i += 1
        continue
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    add_runs(p, s)
    i += 1

doc.save(DST)
print("saved", DST)