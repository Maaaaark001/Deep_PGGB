import fitz, sys
d = fitz.open(sys.argv[1])
print("pages", d.page_count)
for i in (5, 6):
    p = d[i]
    pix = p.get_pixmap(dpi=115)
    out = f"work/float128/pdfpage_{i+1}.png"
    pix.save(out)
    print(out, pix.width, pix.height)
