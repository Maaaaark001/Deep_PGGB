import os, sys, ctypes, numpy as np, subprocess, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
os.add_dll_directory(HERE)
lib = ctypes.CDLL(os.path.join(HERE, "dpggb.dll"))
lib.dpggb_resample.restype = ctypes.c_int
lib.dpggb_resample.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.c_longlong, ctypes.c_int,
                               ctypes.c_double, ctypes.c_double, ctypes.c_char_p,
                               ctypes.POINTER(ctypes.POINTER(ctypes.c_double)),
                               ctypes.POINTER(ctypes.c_longlong)]
lib.dpggb_free.argtypes = [ctypes.POINTER(ctypes.c_double)]

def dll(y, src, dst, opts=b"block=4.0,context=400.0,btaper=20.0,taper=smooth5"):
    y = np.ascontiguousarray(y, dtype=np.float64)
    n, ch = y.shape
    p = ctypes.POINTER(ctypes.c_double)(); nf = ctypes.c_longlong()
    rc = lib.dpggb_resample(y.ctypes.data_as(ctypes.POINTER(ctypes.c_double)), n, ch, src, dst, opts,
                            ctypes.byref(p), ctypes.byref(nf))
    if rc: raise RuntimeError(rc)
    out = np.ctypeslib.as_array(p, shape=(nf.value * ch,)).copy().reshape(-1, ch)
    lib.dpggb_free(p)
    return out

def exe(y, src, dst, opts):
    td = tempfile.mkdtemp(); fi = os.path.join(td, "i.f64"); fo = os.path.join(td, "o.f64")
    y.astype("<f8").tofile(fi)
    cmd = [os.path.join(HERE, "dpggb.exe"), str(src), str(dst), fi, fo, "--ch", str(y.shape[1])]
    for k, v in opts.items(): cmd += ["--" + k, str(v)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode: raise RuntimeError(r.stderr)
    return np.fromfile(fo, "<f8").reshape(-1, y.shape[1])

t = np.arange(44100 * 2) / 44100
y = np.column_stack([0.5 * np.sin(2 * np.pi * 997 * t), 0.4 * np.sin(2 * np.pi * 3001 * t)])
for src, dst in [(44100, 48000), (44100, 56448), (44100, 50001), (96000, 44100)]:
    # Both sides must run the SAME options, otherwise this compares two
    # configurations and reports a difference that is not a DLL/EXE mismatch.
    common = {"block": 4.0, "context": 400.0, "btaper": 20.0, "taper": "smooth5"}
    a = dll(y, src, dst, ",".join("%s=%s" % kv for kv in common.items()).encode())
    b = exe(y, src, dst, common)
    print(f"{src}->{dst}: dll {a.shape} exe {b.shape} equal={np.array_equal(a, b)} "
          f"maxdiff={np.max(np.abs(a-b)) if a.shape==b.shape else 'shape mismatch'}")
