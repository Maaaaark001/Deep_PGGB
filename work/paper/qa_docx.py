import re, sys, zipfile
import docx

P = "work/paper/Deep_PGGB_paper.docx"
z = zipfile.ZipFile(P)
bad = []
for n in z.namelist():
    if n.endswith(".xml") or n.endswith(".rels"):
        try:
            import lxml.etree as ET
            ET.fromstring(z.read(n))
        except Exception as e:
            bad.append((n, str(e)[:80]))
doc = z.read("word/document.xml").decode("utf-8")
styles = z.read("word/styles.xml").decode("utf-8")
print("parts", len(z.namelist()), "bad", bad)
print("drawing", doc.count("<w:drawing>"), "tbl", doc.count("<w:tbl>"),
      "cantSplit", doc.count("cantSplit"), "keepNext", len(re.findall(r"<w:keepNext/>", doc)))
print("pStyle", len(re.findall(r"<w:pStyle ", doc)),
      "FIG left", doc.count("@@FIG"), "stars", doc.count("**"))
for sid in ("Title", "Heading1", "Heading2", "Heading3"):
    m = re.search(r'<w:style [^>]*w:styleId="%s".*?</w:style>' % sid, styles, re.S)
    print(sid, "defined" if m else "MISSING",
          "outlineLvl" if m and "outlineLvl" in m.group(0) else "")
d = docx.Document(P)
print("chars", sum(len(p.text) for p in d.paragraphs))
print("tblW", re.findall(r'<w:tblW w:w="(\d+)"', doc)[:8])
fonts = {}
for p in d.paragraphs:
    for r in p.runs:
        rf = r._element.rPr.rFonts if r._element.rPr is not None else None
        ea = rf.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia") if rf is not None else None
        key = (ea, round(r.font.size.pt, 1) if r.font.size else None, bool(r.font.bold))
        fonts[key] = fonts.get(key, 0) + 1
print(sorted(fonts.items(), key=lambda kv: -kv[1])[:8])
