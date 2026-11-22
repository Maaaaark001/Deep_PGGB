"""deeppggb - Python driver for the Deep_PGGB resampler.

Two entry points:
  resample(y, src, dst, **opts)          numpy in, numpy out
  convert(src_path, dst_path, rate, ...) file in, file out (ffmpeg handles formats)

The DSP lives in dpggb.exe; this module only moves data in and out."""
from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def _find_exe() -> str:
    """The binary sits next to this file in the dev tree and under bin/ in the
    installed skill, so search both layouts."""
    for cand in (os.path.join(HERE, "dpggb.exe"),
                 os.path.join(HERE, "bin", "dpggb.exe"),
                 os.path.join(os.path.dirname(HERE), "bin", "dpggb.exe")):
        if os.path.isfile(cand):
            return cand
    return os.path.join(HERE, "dpggb.exe")


EXE = _find_exe()

DEFAULTS = dict(
    block=16.0,       # seconds per block (0 = whole file)
    workers=0,       # 0 = one worker per hardware thread
    mem=1024.0,      # memory budget, MB
    fade=20.0,       # head/tail fade, ms (20 saturates the boundary error)
    context=800.0,   # block context, ms (seams + upsampling image band; must match C++)
    mptaps=50.0,     # min-phase FIR length = 4 x this, ms
    taper="smooth5",  # smooth5 | smooth4 | smooth6 | smooth2 | cos | blackman | none
    prec="double",   # double | long
    phase="linear",  # linear | min
    threads=0,       # 0 = FFTW default
)


def available() -> bool:
    return os.path.isfile(EXE)


def _ffmpeg() -> str:
    """ffmpeg handles containers only; the resampling is never delegated to it."""
    env = os.environ.get("FFMPEG")
    if env and os.path.isfile(env):
        return env
    for pat in (os.path.join(tempfile.gettempdir(), "ffm", "ffmpeg*", "bin", "ffmpeg.exe"),
                os.path.join(tempfile.gettempdir(), "ffm", "*", "bin", "ffmpeg.exe")):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    raise RuntimeError("ffmpeg not found; set FFMPEG or install it")


def _probe(path: str) -> dict:
    """Sample rate and channel count, via soundfile when it can, else ffmpeg."""
    try:
        import soundfile as sf
        info = sf.info(path)
        return {"rate": int(info.samplerate), "channels": int(info.channels)}
    except Exception:
        pass
    p = subprocess.run([_ffmpeg(), "-hide_banner", "-i", path],
                       capture_output=True, text=True)
    m = re.search(r"(\d+) Hz", p.stderr)
    if not m:
        raise RuntimeError("cannot probe " + path)
    ch = 1 if "mono" in p.stderr else 2
    return {"rate": int(m.group(1)), "channels": ch}


def decode(path: str) -> tuple[np.ndarray, int]:
    """Decode to float64 (frames, channels). Never drops to 16-bit midway."""
    meta = _probe(path)
    raw = subprocess.run(
        [_ffmpeg(), "-v", "error", "-i", path, "-f", "f64le", "-acodec", "pcm_f64le", "-"],
        capture_output=True, check=True).stdout
    y = np.frombuffer(raw, "<f8").reshape(-1, meta["channels"])
    return y, meta["rate"]


def encode(y: np.ndarray, rate: int, path: str, bits: int = 24) -> None:
    """Encode float64 back to a container. Quantisation happens exactly once."""
    fmt = os.path.splitext(path)[1].lower()
    codec = {".flac": "flac", ".wav": "pcm_s24le", ".aiff": "pcm_s24be",
             ".mp3": "libmp3lame", ".ogg": "libvorbis"}.get(fmt, "flac")
    if fmt == ".wav":
        codec = {16: "pcm_s16le", 24: "pcm_s24le", 32: "pcm_s32le"}.get(bits, "pcm_s24le")
    args = [_ffmpeg(), "-v", "error", "-y", "-f", "f64le", "-ar", str(rate),
            "-ac", str(y.shape[1]), "-i", "-", "-acodec", codec]
    if codec == "flac":
        args += ["-compression_level", "8"]
    args += [path]
    subprocess.run(args, input=np.ascontiguousarray(y, dtype="<f8").tobytes(), check=True)


def resample(y, src: int, dst: int, **opts) -> np.ndarray:
    """numpy (frames, channels) float64 in, the same shape out at the new rate."""
    y = np.ascontiguousarray(y, dtype=np.float64)
    if y.ndim == 1:
        y = y[:, None]
    if src == dst:
        return y.copy()
    o = dict(DEFAULTS)
    o.update({k: v for k, v in opts.items() if v is not None})

    td = tempfile.mkdtemp(prefix="dpggb_")
    try:
        fi = os.path.join(td, "in.f64")
        fo = os.path.join(td, "out.f64")
        y.astype("<f8").tofile(fi)
        cmd = [EXE, str(src), str(dst), fi, fo,
               "--ch", str(y.shape[1]), "--block", str(o["block"]),
               "--mem", str(o["mem"]), "--fade", str(o["fade"]),
               "--context", str(o["context"]), "--mptaps", str(o["mptaps"]),
               "--taper", str(o["taper"]), "--prec", str(o["prec"]),
               "--phase", str(o["phase"]), "--threads", str(o["threads"]),
               "--workers", str(o.get("workers", 0))]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError("dpggb failed: " + r.stderr.strip()[-500:])
        out = np.fromfile(fo, "<f8").reshape(-1, y.shape[1])
        want = int(round(y.shape[0] * dst / src))
        if out.shape[0] > want:
            out = out[:want]
        elif out.shape[0] < want:
            out = np.vstack([out, np.zeros((want - out.shape[0], y.shape[1]))])
        return out
    finally:
        shutil.rmtree(td, ignore_errors=True)


def convert(src_path: str, dst_path: str, dst_rate: int, bits: int = 24, **opts) -> dict:
    """Decode, resample, encode. Returns a small report dict."""
    y, rate = decode(src_path)
    out = resample(y, rate, dst_rate, **opts)
    encode(out, dst_rate, dst_path, bits)
    return {"in_rate": rate, "out_rate": dst_rate, "in_frames": int(y.shape[0]),
            "out_frames": int(out.shape[0]), "channels": int(y.shape[1])}


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Deep_PGGB resampler")
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("-r", "--rate", type=int, required=True)
    ap.add_argument("--bits", type=int, default=24)
    ap.add_argument("--block", type=float, default=16.0)
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--mem", type=float, default=1024.0)
    ap.add_argument("--fade", type=float, default=20.0)
    ap.add_argument("--context", type=float, default=800.0)
    ap.add_argument("--mptaps", type=float, default=50.0)
    ap.add_argument("--taper", default="smooth5")
    ap.add_argument("--prec", default="double")
    ap.add_argument("--phase", default="linear")
    ap.add_argument("--threads", type=int, default=0)
    a = ap.parse_args()
    print(convert(a.src, a.dst, a.rate, bits=a.bits, block=a.block, mem=a.mem,
                  workers=a.workers,
                  fade=a.fade, context=a.context, mptaps=a.mptaps,
                  taper=a.taper, prec=a.prec, phase=a.phase,
                  threads=a.threads))
