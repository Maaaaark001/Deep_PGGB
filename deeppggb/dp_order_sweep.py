"""dp_order_sweep.py - shape exponent vs width, on the real binary."""
import sys, os, subprocess, tempfile, numpy as np
sys.path.insert(0, r"C:\Users\Administrator\Documents\Python_Code\src")
from srctool import config

SRC, DST, SECS = 96000, 44100, 8.0
n = int(round(SRC*SECS)); t = np.arange(n)/float(SRC)
REF = 0.5/np.sqrt(2.0)

def run(f, roll, order, block=1.0, ctx=100):
    x = (0.5*np.sin(2*np.pi*f*t)).astype("<f8")
    td = tempfile.mkdtemp(); fi=os.path.join(td,"i.f64"); fo=os.path.join(td,"o.f64")
    x.tofile(fi)
    subprocess.run([str(config.DPGGB),"96000","44100",fi,fo,"--ch","1","--block",str(block),
                    "--context",str(ctx),"--rolloff",str(roll),"--rollorder",str(order)],
                   check=True, capture_output=True)
    y = np.fromfile(fo,"<f8"); seg = y[len(y)//4:3*len(y)//4]
    return 20*np.log10(max(float(np.sqrt(np.mean(seg*seg))),1e-30)/REF)

print("%6s %5s %9s %9s %9s %9s" % ("roll","ord","al22050","al22100","pb21.5k","pb21.9k"))
for order in (1, 2, 3, 4):
    for roll in (100, 200, 400):
        print("%6d %5d %9.1f %9.1f %9.3f %9.3f"
              % (roll, order, run(22050.37,roll,order), run(22100.37,roll,order),
                 run(21500.0,roll,order), run(21900.0,roll,order)))
