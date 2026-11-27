import fitz, os
doc = fitz.open(r"work/paper_cert/certified_null_paper.pdf")
out = r"work/paper_cert/_pg"
os.makedirs(out, exist_ok=True)
for i, page in enumerate(doc):
    pix = page.get_pixmap(dpi=100)
    pix.save(os.path.join(out, "p%02d.png" % (i + 1)))
print("pages", len(doc))
