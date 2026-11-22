# -*- coding: utf-8 -*-
"""Replace @@FIG:name|WxH@@ placeholders in an exported docx with real inline images.

The Univer docx exporter does not carry base64 image data into word/media, so the
figures are placed after export. Each placeholder paragraph is replaced by a
single centred paragraph holding an inline DrawingML picture at the requested
pixel size (1 px = 9525 EMU at 96 dpi).
"""
import os
import re
import shutil
import sys
import zipfile

EMU_PER_PX = 9525
NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
      'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"')

# keepNext keeps the picture on the same page as the caption that follows it;
# without it Word happily leaves a figure stranded at the foot of a page.
DRAWING = '''<w:p><w:pPr><w:keepNext/><w:jc w:val="center"/><w:spacing w:before="160" w:after="40" w:line="240" w:lineRule="auto"/></w:pPr><w:r><w:drawing>
<wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/><wp:docPr id="{pid}" name="Figure {pid}"/>
<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
<pic:pic><pic:nvPicPr><pic:cNvPr id="{pid}" name="{name}.png"/><pic:cNvPicPr/></pic:nvPicPr>
<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>
<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>
</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>'''


A4_SECTPR = ('<w:sectPr><w:footerReference w:type="default" r:id="rIdFoot1"/>'
             '<w:pgSz w:w="11906" w:h="16838"/>'
             '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
             'w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>')

FOOTER_XML = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<w:p><w:pPr><w:jc w:val="center"/></w:pPr>
<w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/><w:sz w:val="18"/><w:color w:val="595959"/></w:rPr>
<w:fldChar w:fldCharType="begin"/></w:r>
<w:r><w:rPr><w:sz w:val="18"/></w:rPr><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>
<w:r><w:rPr><w:sz w:val="18"/></w:rPr><w:fldChar w:fldCharType="separate"/></w:r>
<w:r><w:rPr><w:sz w:val="18"/></w:rPr><w:t>1</w:t></w:r>
<w:r><w:rPr><w:sz w:val="18"/></w:rPr><w:fldChar w:fldCharType="end"/></w:r>
</w:p></w:ftr>'''


HEADING_STYLES = '''<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:sz w:val="26"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:outlineLvl w:val="1"/></w:pPr><w:rPr><w:b/><w:sz w:val="23"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:outlineLvl w:val="2"/></w:pPr><w:rPr><w:b/><w:sz w:val="21"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:jc w:val="center"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style>'''

# The Univer exporter writes every paragraph as Normal and drops named styles,
# so headings arrive in Word as a flat wall of body text: no navigation pane, no
# outline, no TOC. Re-derive the level from the run size/bold that the renderer
# already applied, and attach a real heading style.
SZ_TO_STYLE = {("32", True): "Title", ("26", True): "Heading1",
               ("23", True): "Heading2", ("21", True): "Heading3"}


def tag_headings(doc):
    def para(m):
        body = m.group(0)
        if "<w:drawing>" in body or "<w:tbl" in body:
            return body
        pr = re.search(r"<w:pPr>(.*?)</w:pPr>", body, re.S)
        if not pr:
            return body
        ppr = pr.group(1)
        rpr = re.search(r"<w:rPr>(.*?)</w:rPr>", ppr, re.S)
        if not rpr:
            return body
        sz = re.search(r'<w:sz w:val="(\d+)"', rpr.group(1))
        bold = "<w:b/>" in rpr.group(1)
        name = SZ_TO_STYLE.get((sz.group(1) if sz else None, bold))
        if not name or "w:pStyle" in ppr:
            return body
        new_ppr = '<w:pStyle w:val="%s"/>' % name + ppr
        return body.replace(pr.group(0), "<w:pPr>" + new_ppr + "</w:pPr>", 1)

    return re.sub(r"<w:p\b[^>]*>.*?</w:p>", para, doc, flags=re.S)


def keep_tables_whole(doc):
    """Stop a table from breaking across a page boundary.

    Word has no per-table "keep together" flag, so the equivalent is: mark every
    row cantSplit, and give every paragraph in every row except the last a
    keepNext. A six-row table split 1/5 across pages reads as a typesetting
    accident, which is exactly what happened to Table 6 before this was added.
    """
    # Cell paragraphs inherit docDefaults (after=180 twips, line=360), which turns a
    # nine-row table into a full page of air. Pin them to single spacing first.
    CELL_SPACING = '<w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/>'

    def fix_table(m):
        table = m.group(0)
        # pPr children are a schema sequence: keepNext must precede spacing.
        table = re.sub(r"(<w:tc\b.*?</w:tc>)", lambda c: re.sub(
            r"</w:pPr>", CELL_SPACING + "</w:pPr>", c.group(1)), table, flags=re.S)
        table = re.sub(r"<w:p>(<w:r>)",
                       "<w:p><w:pPr>" + CELL_SPACING + r"</w:pPr>\1", table)
        rows = re.findall(r"<w:tr\b.*?</w:tr>", table, re.S)
        if len(rows) < 2:
            return table
        out = table
        for idx, row in enumerate(rows):
            new = row
            if "<w:trPr>" in new:
                new = new.replace("<w:trPr>", "<w:trPr><w:cantSplit/>", 1)
            else:
                new = re.sub(r"(<w:tr\b[^>]*>)", r"\1<w:trPr><w:cantSplit/></w:trPr>", new, count=1)
            if idx < len(rows) - 1:
                # Cells normally arrive with a <w:pPr> already (justification, spacing),
                # so keepNext has to be inserted *inside* it; only bare <w:p> gets a new one.
                new = re.sub(r"<w:pPr>", "<w:pPr><w:keepNext/>", new)
                # Bare paragraphs (no pPr at all) get one; the lookahead keeps the
                # already-patched ones from being double-wrapped.
                new = re.sub(r"<w:p(\s[^>]*)?>(?!<w:pPr>)",
                             lambda mm: mm.group(0) + "<w:pPr><w:keepNext/></w:pPr>", new)
            out = out.replace(row, new, 1)
        return out

    return re.sub(r"<w:tbl>.*?</w:tbl>", fix_table, doc, flags=re.S)


TITLE = ("精确有理倍率下的分块频域重采样：数值保真度、流式扩展与八引擎对照")
CORE_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"'
    ' xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/"'
    ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
    '<dc:title>' + TITLE + '</dc:title>'
    '<dc:subject>采样率转换 / 分块频域 / 数值保真度 / 流式处理</dc:subject>'
    '<dc:creator>SonarSRC 项目组</dc:creator>'
    '<cp:keywords>sample-rate conversion; spectral zero-padding; null test; numerical fidelity; '
    'partitioned processing; window function; streaming</cp:keywords>'
    '<dc:description>Technical Report, SonarSRC Project, 2026-11-23</dc:description>'
    '<cp:lastModifiedBy>SonarSRC 项目组</cp:lastModifiedBy>'
    '<dcterms:created xsi:type="dcterms:W3CDTF">2026-11-23T00:00:00Z</dcterms:created>'
    '<dcterms:modified xsi:type="dcterms:W3CDTF">2026-11-23T00:00:00Z</dcterms:modified>'
    '</cp:coreProperties>'
)


def main(docx_in, docx_out, figdir):
    zin = zipfile.ZipFile(docx_in)
    items = {n: zin.read(n) for n in zin.namelist()}
    zin.close()

    doc = items["word/document.xml"].decode("utf-8")
    rels = items["word/_rels/document.xml.rels"].decode("utf-8")
    types = items["[Content_Types].xml"].decode("utf-8")

    existing = [int(m) for m in re.findall(r'Id="rId(\d+)"', rels)]
    next_id = max(existing) + 1 if existing else 1
    media = []

    for pid, m in enumerate(re.finditer(r"@@FIG:([A-Za-z0-9_]+)\|(\d+)x(\d+)@@", doc), start=1):
        pass

    def repl(m):
        nonlocal next_id
        name, w, h = m.group(1), int(m.group(2)), int(m.group(3))
        png = os.path.join(figdir, name + ".png")
        rid = "rId%d" % next_id
        next_id += 1
        media.append((name + ".png", png, rid))
        return DRAWING.format(cx=w * EMU_PER_PX, cy=h * EMU_PER_PX, pid=next_id,
                              name=name, rid=rid)

    # The placeholder sits inside its own <w:p>…</w:p>; replace the whole paragraph.
    def para_repl(m):
        body = m.group(0)
        if "@@FIG:" not in body:
            return body
        inner = re.search(r"@@FIG:([A-Za-z0-9_]+)\|(\d+)x(\d+)@@", body)
        return repl(inner)

    doc2 = re.sub(r"<w:p\b[^>]*>.*?</w:p>", para_repl, doc, flags=re.S)

    if not media:
        raise SystemExit("no figure placeholders found")

    rel_xml = "".join(
        '<Relationship Id="%s" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
        'relationships/image" Target="media/%s"/>' % (rid, fn)
        for fn, _, rid in media)
    rels = rels.replace("</Relationships>", rel_xml + "</Relationships>")
    if 'Extension="png"' not in types:
        types = types.replace("<Types ", "<Types ", 1)
        types = re.sub(r"(<Types[^>]*>)", r'\1<Default Extension="png" ContentType="image/png"/>', types, count=1)

    # The exporter emits a 14400x16840 twip page (US Letter-ish, 15x17.5 in) with
    # 750 twip margins. Replace it with A4 and a centred page number.
    doc2 = tag_headings(doc2)
    doc2 = keep_tables_whole(doc2)
    doc2 = re.sub(r"<w:sectPr.*?</w:sectPr>", A4_SECTPR, doc2, count=1, flags=re.S)
    if 'w:footerReference' in doc2:
        rels = rels.replace("</Relationships>",
            '<Relationship Id="rIdFoot1" Type="http://schemas.openxmlformats.org/'
            'officeDocument/2006/relationships/footer" Target="footer1.xml"/></Relationships>')
        items["word/footer1.xml"] = FOOTER_XML.encode("utf-8")
        types = re.sub(r"(<Types[^>]*>)",
                       r'\1<Override PartName="/word/footer1.xml" '
                       r'ContentType="application/vnd.openxmlformats-officedocument.'
                       r'wordprocessingml.footer+xml"/>', types, count=1)

    styles = items["word/styles.xml"].decode("utf-8")
    if "w:styleId=\"Heading1\"" not in styles:
        styles = styles.replace("</w:styles>", HEADING_STYLES + "</w:styles>")
        items["word/styles.xml"] = styles.encode("utf-8")

    # The exporter stamps the unit name ("final8") into dc:title and leaves the
    # author blank. A manuscript handed to a reviewer should carry its real title.
    items["docProps/core.xml"] = CORE_XML.encode("utf-8")

    items["word/document.xml"] = doc2.encode("utf-8")
    items["word/_rels/document.xml.rels"] = rels.encode("utf-8")
    items["[Content_Types].xml"] = types.encode("utf-8")
    for fn, path, _ in media:
        items["word/media/" + fn] = open(path, "rb").read()

    with zipfile.ZipFile(docx_out, "w", zipfile.ZIP_DEFLATED) as zout:
        for n, data in items.items():
            zout.writestr(n, data)
    print("embedded %d figure(s) -> %s (%d bytes)"
          % (len(media), docx_out, os.path.getsize(docx_out)))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else ".")
