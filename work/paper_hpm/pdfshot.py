import fitz, os
d = fitz.open("work/paper_hpm/final.pdf")
os.makedirs("work/paper_hpm/pages", exist_ok=True)
for i, p in enumerate(d, 1):
    pix = p.get_pixmap(dpi=110)
    pix.save(f"work/paper_hpm/pages/p{i:02d}.png")
print(d.page_count)
