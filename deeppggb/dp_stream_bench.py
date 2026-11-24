#!/usr/bin/env python
"""Streaming throughput / latency benchmark for the SRC engines.

Protocol: 60 s stereo 44.1 -> 88.2 kHz, fed in fixed chunks.  Throughput is
input seconds / wall seconds; latency is the number of input frames that must
be consumed before the first output frame appears.  Reps are best-of-N.

Engines with an incremental API: Deep_PGGB NativeStreamResampler (the FIFO
lives in dpggb.dll), libsoxr (python-soxr ResampleStream), ffmpeg
(aresample=soxr over a pipe), sox_ng (rate -v over a pipe).  r8brain / SSRC /
SciPy / PGGB only accept whole files or a CLI call and are recorded as
non-streaming in the meta block.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time

import numpy as np
import soxr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
from deeppggb_stream import NativeStreamResampler  # noqa: E402

SR, DST, CH = 44100, 88200, 2
def _resolve_tool(env_var, attr, *names):
    """Env var -> srctool.config (the project's own chain) -> PATH."""
    v = os.environ.get(env_var)
    if v and os.path.exists(v):
        return v
    try:
        from srctool import config as _cfg
        p = getattr(_cfg, attr, None)
        if p and os.path.exists(str(p)):
            return str(p)
    except Exception:
        pass
    for n in names:
        w = shutil.which(n)
        if w:
            return w
    return None


FFMPEG = _resolve_tool("FFMPEG", "FFMPEG", "ffmpeg.exe", "ffmpeg")
SOXNG = _resolve_tool("SOXNG", "SOXNG", "sox_ng.exe", "sox_ng")


def signal(seconds):
    n = int(round(SR * seconds))
    t = np.arange(n) / SR
    x = 0.5 * np.sin(2 * np.pi * 997.0 * t) + 0.3 * np.sin(2 * np.pi * 12345.0 * t)
    return np.repeat(x[:, None], CH, axis=1)


def best_of(fn, reps):
    vals = [fn() for _ in range(reps)]
    return max(vals), vals


def dp_run(x, core, chunk):
    r = NativeStreamResampler(SR, DST, CH, core_sec=core)
    t0 = time.perf_counter()
    frames = 0
    for i in range(0, len(x), chunk):
        frames += r.push(x[i:i + chunk]).shape[0]
    frames += r.flush().shape[0]
    wall = time.perf_counter() - t0
    r.close()
    return wall, frames


def dp_latency(core, chunk, seconds=5.0):
    x = signal(seconds)
    r = NativeStreamResampler(SR, DST, CH, core_sec=core)
    fed = 0
    for i in range(0, len(x), chunk):
        o = r.push(x[i:i + chunk])
        fed += min(chunk, len(x) - i)
        if o.shape[0]:
            r.close()
            return fed / SR
    r.close()
    return None


def soxr_run(x, chunk):
    st = soxr.ResampleStream(SR, DST, CH, dtype="float64", quality="HQ")
    t0 = time.perf_counter()
    frames = 0
    n = len(x)
    for i in range(0, n, chunk):
        last = (i + chunk) >= n
        frames += st.resample_chunk(x[i:i + chunk], last=last).shape[0]
    return time.perf_counter() - t0, frames


def soxr_latency(chunk, seconds=5.0):
    x = signal(seconds)
    st = soxr.ResampleStream(SR, DST, CH, dtype="float64", quality="HQ")
    fed = 0
    for i in range(0, len(x), chunk):
        o = st.resample_chunk(x[i:i + chunk], last=False)
        fed += min(chunk, len(x) - i)
        if o.shape[0]:
            return fed / SR
    return None


_SOXR = None


def _ffmpeg_has_soxr():
    global _SOXR
    if _SOXR is None:
        _SOXR = False
        try:
            from srctool import engines as _E
            _SOXR = bool(_E.ffmpeg_caps().get("soxr"))
        except Exception:
            pass
    return _SOXR


def pipe_cmd(engine):
    if engine == "ffmpeg":
        if not FFMPEG:
            raise RuntimeError("ffmpeg not found: set FFMPEG or put it on PATH")
        # essentials builds ship no libsoxr; asking for resampler=soxr then fails with
        # EINVAL ("Task finished with error code: -22"), so pick whatever is present.
        af = "aresample=%d" % DST
        if _ffmpeg_has_soxr():
            af += ":resampler=soxr"
        return [FFMPEG, "-v", "error", "-nostdin", "-f", "f64le", "-ar", str(SR),
                "-ac", str(CH), "-i", "pipe:0",
                "-af", af, "-f", "f64le", "pipe:1"]
    if engine == "sox_ng":
        if not SOXNG:
            raise RuntimeError("sox_ng not found: set SOXNG or put it on PATH")
        return [SOXNG, "-q", "-t", "f64", "-r", str(SR), "-c", str(CH), "-",
                "-t", "f64", "-r", str(DST), "-", "rate", "-v"]
    raise ValueError(engine)


def pipe_run(cmd, x):
    raw = np.ascontiguousarray(x, dtype="<f8").tobytes()
    t0 = time.perf_counter()
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    out, err = p.communicate(raw)
    wall = time.perf_counter() - t0
    if p.returncode != 0:
        raise RuntimeError("pipe failed: %s" % err.decode("utf-8", "replace")[-300:])
    return wall, len(out) // (8 * CH)


def pipe_latency(cmd, chunk, seconds=5.0):
    raw = np.ascontiguousarray(signal(seconds), dtype="<f8").tobytes()
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, bufsize=0)
    first = threading.Event()
    fed = [0]

    def reader():
        fd = p.stdout.fileno()
        while True:
            b = os.read(fd, 1 << 16)
            if not b:
                break
            if not first.is_set():
                first.set()

    def eread():
        try:
            p.stderr.read()
        except Exception:
            pass

    th = threading.Thread(target=reader, daemon=True)
    te = threading.Thread(target=eread, daemon=True)
    th.start()
    te.start()
    step = chunk * 8 * CH
    for i in range(0, len(raw), step):
        try:
            p.stdin.write(raw[i:i + step])
        except BrokenPipeError:
            break
        fed[0] = min(i + step, len(raw)) // (8 * CH)
        if first.wait(0.02):
            break
    try:
        p.stdin.close()
    except Exception:
        pass
    try:
        p.wait(timeout=10)
    except subprocess.TimeoutExpired:
        p.kill()
    return fed[0] / SR if first.is_set() else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--out", default=os.path.join(ROOT, "work", "stream_engines.json"))
    args = ap.parse_args()

    x = signal(args.seconds)
    chunks = (256, 1024, 4096)
    rows = []

    for core in (0.5, 1.0, 2.0):
        for chunk in chunks:
            (wall, frames), vals = best_of(lambda: dp_run(x, core, chunk), args.reps)
            rows.append({"engine": "dpggb", "core_s": core, "chunk": chunk,
                         "throughput_x": args.seconds / wall,
                         "latency_s": dp_latency(core, chunk),
                         "frames": frames, "reps_wall_s": vals})
            print("dpggb core=%.1f chunk=%4d  %7.1fx  latency %.3f s  frames %d"
                  % (core, chunk, rows[-1]["throughput_x"],
                     rows[-1]["latency_s"] or -1, frames), flush=True)

    for eng in ("soxr", "ffmpeg", "sox_ng"):
        if (eng == "ffmpeg" and not FFMPEG) or (eng == "sox_ng" and not SOXNG):
            print("%-6s skipped: binary not found" % eng, flush=True)
            continue
        for chunk in chunks:
            if eng == "soxr":
                (wall, frames), vals = best_of(lambda: soxr_run(x, chunk), args.reps)
                lat = soxr_latency(chunk)
            else:
                cmd = pipe_cmd(eng)
                (wall, frames), vals = best_of(lambda: pipe_run(cmd, x), args.reps)
                lat = pipe_latency(cmd, chunk)
            rows.append({"engine": eng, "core_s": None, "chunk": chunk,
                         "throughput_x": args.seconds / wall,
                         "latency_s": lat, "frames": frames, "reps_wall_s": vals})
            print("%-6s chunk=%4d  %7.1fx  latency %.3f s  frames %d"
                  % (eng, chunk, rows[-1]["throughput_x"], lat or -1, frames), flush=True)

    offline = {}
    try:
        with open(os.path.join(ROOT, "work", "paper_data.json"), encoding="utf-8") as f:
            pd = json.load(f)
        offline = {e["engine"]: e["speed_x"] for e in pd["engines"]}
    except Exception:
        pass

    doc = {
        "meta": {"src": SR, "dst": DST, "channels": CH, "seconds": args.seconds,
                 "reps": args.reps, "chunks": list(chunks),
                 "protocol": "input seconds / wall seconds; latency = input frames consumed before first output; best of N",
                 "dp_backend": "native C++ FIFO in dpggb.dll (NativeStreamResampler), workers=1",
                 "python_patch_1024": {"0.5": 9.6, "1.0": 13.5, "2.0": 18.4},
                 "nonstreaming": ["r8b", "ssrc", "scipy", "pggb"],
                 "offline_speed_x": offline},
        "rows": rows,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    print("wrote", args.out)


if __name__ == "__main__":
    main()
