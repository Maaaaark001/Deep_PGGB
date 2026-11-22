"""Reproduce the engine's block geometry exactly, to prove the diagnosis.

Engine (before the fix), 44.1 -> 56.448 kHz, 3 s, block=1 s:
  M=25, L=32, context T=4410 samples (100 ms)
  want=44100 -> lo_s=1764 -> smallest smooth s: P=45000, kept=P-2T=36180
  kept % M = 36180 % 25 = 5  -> not a multiple of M
  o0 = floor(bi*36180*32/25), lo = round(4410*32/25)=5645, hi-lo = floor(kept*32/25)
"""
import numpy as np

def taper(x, t):
    n = len(x); xs = x.copy()
    i = np.arange(t) / (t - 1); w = i**3 * (i*(i*6-15)+10)
    xs[:t] *= w; xs[n-1-np.arange(t)] *= w
    return xs

def resid(y, dst, f0, skip=0.5):
    lo = int(skip*dst); hi = len(y)-int(skip*dst)
    y = y[lo:hi]; t = np.arange(len(y))/dst
    Mx = np.column_stack([np.cos(2*np.pi*f0*t), np.sin(2*np.pi*f0*t)])
    c,*_ = np.linalg.lstsq(Mx, y, rcond=None)
    return 20*np.log10(max(np.sqrt(np.mean((y-Mx@c)**2)),1e-300)/0.3536)

def blockwise(xs, L, M, P, T, bt):
    n = len(xs)
    Q = (P//M)*L
    kept = P-2*T
    lo = round(T*L/M); hi = round((P-T)*L/M)
    out_total = round(n*L/M)
    out = np.zeros(out_total)
    nb = (n + kept - 1)//kept
    for bi in range(nb):
        start = bi*kept
        buf = np.zeros(P)
        idx = np.arange(start-T, start-T+P)
        ok = (idx>=0)&(idx<n)
        buf[ok] = xs[idx[ok]]
        # block taper
        i = np.arange(bt)/(bt-1); w = i**3*(i*(i*6-15)+10)
        buf[:bt] *= w; buf[P-1-np.arange(bt)] *= w
        S = np.fft.rfft(buf)
        keep = min(len(S), Q//2+1)
        o = np.zeros(Q//2+1, complex); o[:keep] = S[:keep]
        conv = np.fft.irfft(o, Q)*(Q/P)
        o0 = start*L//M
        cnt = min(hi-lo, out_total-o0)
        if cnt > 0:
            out[o0:o0+cnt] = conv[lo:lo+cnt]
    return out

n = int(44100*3); t = np.arange(n)/44100
x = 0.5*np.sin(2*np.pi*997.0*t); xs = taper(x, 882)

print("old geometry: T=4410 (not a multiple of M=25), kept=36180")
y = blockwise(xs, 32, 25, 45000, 4410, 882)
print("   resid = %6.1f dB   zeros in body = %d" % (resid(y,56448,997.0), int(np.sum(y[56448:2*56448]==0))))

# now snap T and kept to multiples of M
T = (4410//25)*25            # 4400
want_pts = 44100 + 2*T
lo_s = -(-want_pts//25)
P = 25*lo_s
while True:
    v = P
    for p in (2,3,5):
        while v % p == 0: v//=p
    if v == 1: break
    P += 25
kept = P-2*T
print(f"new geometry: T={T} (multiple of M), P={P}, kept={kept} (kept%M={kept%25})")
y = blockwise(xs, 32, 25, P, T, 882)
print("   resid = %6.1f dB   zeros in body = %d" % (resid(y,56448,997.0), int(np.sum(y[56448:2*56448]==0))))
