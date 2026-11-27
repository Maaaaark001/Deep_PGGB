import os, time
import win32com.client as win32

src = os.path.abspath(r"work/paper_cert/certified_null_paper.docx")
pdf = os.path.abspath(r"work/paper_cert/certified_null_paper.pdf")
word = win32.DispatchEx("Word.Application")
word.Visible = False
word.DisplayAlerts = 0
try:
    doc = word.Documents.Open(src, ReadOnly=False)
    time.sleep(1.0)
    pages = doc.ComputeStatistics(2)
    words = doc.ComputeStatistics(0)
    doc.SaveAs(pdf, FileFormat=17)
    print("PAGES", pages, "WORDS", words)
    doc.Close(False)
finally:
    word.Quit()
print("pdf_bytes", os.path.getsize(pdf))
