import sys, os, subprocess, tempfile, shutil, numpy as np
sys.path.insert(0, r"C:\Users\Administrator\Documents\Python_Code\src")
from srctool import engines, config
print("dll found:", config.DPGGB_DLL)
n = 44100*8
t = np.arange(n)/44100.0
y = np.stack([0.5*np.sin(2*np.pi*1000*t), 0.3*np.sin(2*np.pi*3000*t)], axis=1)
a = engines.resample(y, 44100, 96000, "dpggb")
td = tempfile.mkdtemp(); fi=os.path.join(td,"i.f64"); fo=os.path.join(td,"o.f64")
y.astype("<f8").tofile(fi)
subprocess.run([str(config.DPGGB),"44100","96000",fi,fo,"--ch","2"], check=True, capture_output=True)
b = np.fromfile(fo,"<f8").reshape(-1,2); shutil.rmtree(td, ignore_errors=True)
print("toolbox shape", a.shape, "exe shape", b.shape)
print("bit-identical to exe:", np.array_equal(a,b))
