"""dp_ctx_bt.py - context x block-taper grid, alias and join together."""
import sys, os, subprocess, tempfile, numpy as np
sys.path.insert(0, r"C:\Users\Administrator\Documents\Python_Code\src")
from srctool import config

SRC, DST = 96000, 44100
SECS = 8.0
n = int(round(SRC*SECS)); t = np.arange(n)/float(SRC)
REF = 0.5/np.sqrt(2.0)

def conv(x, extra):
    td = tempfile.mkdtemp(); fi=os.path.join(td,"i.f64"); fo=os.path.join(td,"o.f64")
    x.astype("<f8").tofile(fi)
    subprocess.run([str(config.DPGGB),str(SRC),str(DST),fi,fo,"--ch","1"]+extra,
                   check=True, capture_output=True)
    return np.fromfile(fo,"<f8")

def alias(f, ctx, bt):
    y = conv(0.5*np.sin(2*np.pi*f*t), ["--block","1.0","--context",str(ctx),
             "--rolloff","200","--btaper",str(bt)])
    seg = y[len(y)//4:3*len(y)//4]
    return 20*np.log10(max(float(np.sqrt(np.mean(seg*seg))),1e-30)/REF)

rng = np.random.default_rng(11)
X = np.fft.rfft(rng.normal(0,1,n)); fr = np.fft.rfftfreq(n,1.0/SRC)
X[fr>18000.0]=0.0
xb = np.fft.irfft(X,n); xb = xb/np.max(np.abs(xb))*0.4
ref = conv(xb, ["--block","0","--rolloff","200"])

def null(b):
    m=min(len(ref),len(b)); a=ref[:m]; b=b[:m]; e=int(0.1*DST)
    a=a[e:m-e]; b=b[e:m-e]; d=a-b
    return 20*np.log10(max(float(np.sqrt(np.mean(d*d))),1e-30)/max(float(np.sqrt(np.mean(a*a))),1e-30))

print("%7s %8s %9s %9s %9s" % ("ctx_ms","btaper","al22050","al22100","join"))
for ctx in (100, 200, 400):
    for bt in (10, 20, 50):
        y = conv(xb, ["--block","1.0","--context",str(ctx),"--rolloff","200","--btaper",str(bt)])
        print("%7d %8d %9.1f %9.1f %9.1f"
              % (ctx, bt, alias(22050.37,ctx,bt), alias(22100.37,ctx,bt), null(y)))
