"""deeppggb_stream - streaming (incremental) front-end for Deep_PGGB.

The offline path (deeppggb.resample) needs the whole signal in memory. A live
source (DAC feed, broadcast chain, plugin bus) only offers a bounded FIFO of
recently-arrived samples and needs output to fall out the far end at the same
cadence. StreamResampler is the streaming analogue.

Window geometry
---------------
Each window is handed to the kernel with block=0 (one transform, no seams
inside), so per-window quality equals a one-shot conversion of that window. The
streaming discipline adds only the context-overlap bookkeeping the offline block
mode already does internally:

    buf_i = [ left_ctx (ctx_in) | core_i (core_in) | right_ctx (ctx_in) ]

Only the *core* of each window's output is emitted. The right context is carried
so the kernel's spectral surgery and near-Nyquist response have room to settle
inside the window; the left context of window i+1 is exactly the right context
of window i (bit-identical FIFO bytes), so the seam is a no-op for stationary
input and a click guard for transients.

Latency is bounded by core_sec + context_sec. For a given core/context the
fraction of each FFT spent on context (the throughput tax vs offline) is fixed
and does not grow with stream length.

Head convention
---------------
The first window's left context is zero-padded (a live stream has no samples
before the first push). The offline path fades the *true file head* over the
edge-taper (20 ms); the streaming path cannot know a file head exists, so its
first 20 ms differs from an offline conversion of the same samples by the taper
profile. After one taper duration the two agree to the float64 floor. This is a
boundary *convention*, not a defect: a streaming resampler that treated the
first push as a file head would be wrong for a continuous stream.
"""
from __future__ import annotations

import numpy as np

import importlib.util as _ilu
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
def _load_module(name, path):
    spec = _ilu.spec_from_file_location(name, path)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
_deepmod = _load_module("deepmod", _os.path.join(_HERE, "deeppggb.py"))
DEFAULTS = _deepmod.DEFAULTS
resample = _deepmod.resample


class StreamResampler:
    """Incremental Deep_PGGB resampler for live / bounded-buffer sources."""

    def __init__(self, src: int, dst: int, channels: int = 1,
                 core_sec: float = 1.0, context_ms: float | None = None, **opts):
        if src == dst:
            raise ValueError("StreamResampler requires src != dst; pass-through needs no resampler")
        self.src = int(src)
        self.dst = int(dst)
        self.channels = int(channels)
        self.core_sec = float(core_sec)
        self.opts = dict(opts)
        ctx_ms = float(context_ms) if context_ms is not None else float(DEFAULTS["context"])
        # Geometry: core in OUTPUT frames, everything else derived from the ratio.
        self._core_out = max(1, int(round(self.dst * self.core_sec)))
        self._core_in = max(1, int(round(self._core_out * self.src / self.dst)))
        self._ctx_in = max(1, int(round(self.src * ctx_ms / 1000.0)))
        self._ctx_out = max(1, int(round(self._ctx_in * self.dst / self.src)))
        self._fifo = np.zeros((0, self.channels), dtype=np.float64)
        self._cursor = 0
        self._out_pos = 0
        self._prev_tail = None
        self._finished = False

    # -- public API ---------------------------------------------------------

    def push(self, x) -> np.ndarray:
        """Feed x (frames, channels) at src rate; return ready output frames."""
        if self._finished:
            raise RuntimeError("stream already flushed; create a new StreamResampler")
        x = np.asarray(x, dtype=np.float64)
        if x.ndim == 1:
            x = x[:, None]
        if x.shape[1] != self.channels:
            raise ValueError(f"channel mismatch: got {x.shape[1]}, expected {self.channels}")
        if x.shape[0] == 0:
            return np.zeros((0, self.channels), dtype=np.float64)
        self._fifo = np.vstack([self._fifo, x])
        return self._drain(final=False)

    def flush(self) -> np.ndarray:
        """Signal end-of-stream; return the final window (kernel fades the tail)."""
        if self._finished:
            return np.zeros((0, self.channels), dtype=np.float64)
        self._finished = True
        return self._drain(final=True)

    def latency_sec(self) -> float:
        """End-to-end latency bound: core + right context, seconds."""
        return self.core_sec + (self._ctx_in / float(self.src))

    def reset(self) -> None:
        self._fifo = np.zeros((0, self.channels), dtype=np.float64)
        self._cursor = 0
        self._out_pos = 0
        self._prev_tail = None
        self._finished = False

    # -- internals ----------------------------------------------------------

    def _core_ready(self) -> bool:
        """A full window (core + right ctx) is available after the cursor."""
        return (self._fifo.shape[0] - self._cursor) >= (self._core_in + self._ctx_in)

    def _drain(self, final: bool) -> np.ndarray:
        pieces = []
        while True:
            if final:
                remaining = self._fifo.shape[0] - self._cursor
                if remaining <= 0:
                    break
                buf, cursor_after = self._window(self._cursor, take=remaining, final=True)
                self._cursor = cursor_after
                pieces.append(self._process_window(buf, final=True))
                break
            if not self._core_ready():
                break
            buf, cursor_after = self._window(self._cursor, take=None, final=False)
            self._cursor = cursor_after
            pieces.append(self._process_window(buf, final=False))
        # Keep the left-context tail for the next window, bound memory on long streams.
        keep_from = max(0, self._cursor - self._ctx_in)
        if keep_from > 0:
            self._fifo = self._fifo[keep_from:]
            self._cursor -= keep_from
        if not pieces:
            return np.zeros((0, self.channels), dtype=np.float64)
        return np.vstack(pieces)

    def _window(self, start: int, take: int | None, final: bool):
        """Build [left_ctx | core | right_ctx] and return (buf, cursor_after)."""
        if take is None:
            core_n = self._core_in
            right_n = self._ctx_in
        else:
            core_n = take
            right_n = 0
        left_n = self._ctx_in
        # Left context (zero-padded at stream head).
        lo = max(0, start - left_n)
        left = self._fifo[lo:start]
        if left.shape[0] < left_n:
            pad = np.zeros((left_n - left.shape[0], self.channels), dtype=np.float64)
            left = np.vstack([pad, left])
        core = self._fifo[start:start + core_n]
        right = self._fifo[start + core_n:start + core_n + right_n]
        if right.shape[0] < right_n:
            pad = np.zeros((right_n - right.shape[0], self.channels), dtype=np.float64)
            right = np.vstack([right, pad])
        buf = np.vstack([left, core, right])
        cursor_after = start + core_n
        return buf, cursor_after

    def _process_window(self, buf: np.ndarray, final: bool) -> np.ndarray:
        if buf.shape[0] < 2:
            return np.zeros((0, self.channels), dtype=np.float64)
        o = dict(self.opts)
        o.setdefault("block", 0.0)
        out = resample(buf, self.src, self.dst, **o)
        n_out = out.shape[0]
        # Emit the core region: skip ctx_out (left ctx) frames, take core_out.
        core_lo = min(self._ctx_out, n_out)
        if final:
            core = out[core_lo:]
        else:
            core = out[core_lo:core_lo + self._core_out]
        if core.shape[0] <= 0:
            return np.zeros((0, self.channels), dtype=np.float64)
        # Cores are contiguous by construction: the cursor advances by core_in and
        # each window's left-context warm-up happens *inside* the kernel. There is
        # no output overlap between consecutive windows, so no cross-fade is needed
        # (and one would be wrong — it would blend non-overlapping time regions).
        self._out_pos += core.shape[0]
        return core


# ---------------------------------------------------------------------------
# Native backend
# ---------------------------------------------------------------------------
import ctypes as _ct

_DLL = None
_DLL_PATH = None


def _find_dll():
    """dpggb.dll sits next to this file in the dev tree and under bin/ in the
    installed skill. DPGGB_DLL overrides both for experiments."""
    env = _os.environ.get("DPGGB_DLL")
    if env and _os.path.isfile(env):
        return env
    for cand in (_os.path.join(_HERE, "dpggb.dll"),
                 _os.path.join(_HERE, "dpggb_v2.dll"),
                 _os.path.join(_HERE, "bin", "dpggb.dll"),
                 _os.path.join(_os.path.dirname(_HERE), "bin", "dpggb.dll")):
        if _os.path.isfile(cand):
            return cand
    return None


def _load_dll(path=None):
    global _DLL, _DLL_PATH
    if _DLL is not None and (path is None or path == _DLL_PATH):
        return _DLL
    p = path or _find_dll()
    if not p:
        return None
    d = _os.path.dirname(_os.path.abspath(p))
    if hasattr(_os, "add_dll_directory"):
        _os.add_dll_directory(d)
    lib = _ct.CDLL(p)
    if not hasattr(lib, "dpggb_stream_create"):
        raise RuntimeError("dpggb.dll has no streaming API: " + p)
    lib.dpggb_stream_create.restype = _ct.c_void_p
    lib.dpggb_stream_create.argtypes = [_ct.c_double, _ct.c_double, _ct.c_int, _ct.c_char_p]
    lib.dpggb_stream_push.restype = _ct.c_int
    lib.dpggb_stream_push.argtypes = [
        _ct.c_void_p, _ct.POINTER(_ct.c_double), _ct.c_longlong,
        _ct.POINTER(_ct.POINTER(_ct.c_double)), _ct.POINTER(_ct.c_longlong)]
    lib.dpggb_stream_flush.restype = _ct.c_int
    lib.dpggb_stream_flush.argtypes = [
        _ct.c_void_p, _ct.POINTER(_ct.POINTER(_ct.c_double)), _ct.POINTER(_ct.c_longlong)]
    lib.dpggb_stream_latency.restype = _ct.c_double
    lib.dpggb_stream_latency.argtypes = [_ct.c_void_p]
    lib.dpggb_stream_reset.argtypes = [_ct.c_void_p]
    lib.dpggb_stream_destroy.argtypes = [_ct.c_void_p]
    lib.dpggb_free.argtypes = [_ct.POINTER(_ct.c_double)]
    lib.dpggb_free.restype = None
    _DLL = lib
    _DLL_PATH = p
    return lib


class NativeStreamResampler:
    """Streaming Deep_PGGB with the FIFO and cursor inside the C++ DLL.

    Same push/flush/latency_sec contract as StreamResampler, but each push is
    one ABI call instead of one whole-file resample call per window.
    """

    def __init__(self, src: int, dst: int, channels: int = 1,
                 core_sec: float = 1.0, context_ms: float | None = None,
                 dll_path: str | None = None, **opts):
        if src == dst:
            raise ValueError("NativeStreamResampler requires src != dst")
        self.src = int(src)
        self.dst = int(dst)
        self.channels = int(channels)
        self.core_sec = float(core_sec)
        self.opts = dict(opts)
        ctx = float(context_ms) if context_ms is not None else float(DEFAULTS["context"])
        self.context_ms = ctx
        self._lib = _load_dll(dll_path)
        if self._lib is None:
            raise RuntimeError("dpggb.dll not found; set DPGGB_DLL or build the DLL")
        fields = dict(self.opts)
        fields["core"] = self.core_sec
        fields["context"] = ctx
        o = ",".join("%s=%s" % (k, v) for k, v in fields.items() if v is not None)
        self._opts = o.encode()
        self._h = self._lib.dpggb_stream_create(
            _ct.c_double(self.src), _ct.c_double(self.dst),
            _ct.c_int(self.channels), self._opts)
        if not self._h:
            raise RuntimeError("dpggb_stream_create failed (check rates/opts)")
        self.backend = "native"

    def push(self, x) -> np.ndarray:
        x = np.asarray(x, dtype=np.float64)
        if x.ndim == 1:
            x = x[:, None]
        if x.shape[1] != self.channels:
            raise ValueError("channel mismatch: got %d, expected %d"
                             % (x.shape[1], self.channels))
        if x.shape[0] == 0:
            return np.zeros((0, self.channels), dtype=np.float64)
        x = np.ascontiguousarray(x, dtype=np.float64)
        p = _ct.POINTER(_ct.c_double)()
        n = _ct.c_longlong()
        rc = self._lib.dpggb_stream_push(
            self._h, x.ctypes.data_as(_ct.POINTER(_ct.c_double)),
            _ct.c_longlong(x.shape[0]), _ct.byref(p), _ct.byref(n))
        if rc != 0:
            raise RuntimeError("dpggb_stream_push failed: %d" % rc)
        try:
            if n.value == 0:
                return np.zeros((0, self.channels), dtype=np.float64)
            return np.ctypeslib.as_array(p, shape=(n.value * self.channels,)).copy().reshape(-1, self.channels)
        finally:
            if p:
                self._lib.dpggb_free(p)

    def flush(self) -> np.ndarray:
        p = _ct.POINTER(_ct.c_double)()
        n = _ct.c_longlong()
        rc = self._lib.dpggb_stream_flush(self._h, _ct.byref(p), _ct.byref(n))
        if rc != 0:
            raise RuntimeError("dpggb_stream_flush failed: %d" % rc)
        try:
            if n.value == 0:
                return np.zeros((0, self.channels), dtype=np.float64)
            return np.ctypeslib.as_array(p, shape=(n.value * self.channels,)).copy().reshape(-1, self.channels)
        finally:
            if p:
                self._lib.dpggb_free(p)

    def latency_sec(self) -> float:
        return float(self._lib.dpggb_stream_latency(self._h))

    def reset(self) -> None:
        self._lib.dpggb_stream_reset(self._h)

    def close(self) -> None:
        if getattr(self, "_h", None):
            self._lib.dpggb_stream_destroy(self._h)
            self._h = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def make_stream(src, dst, channels=1, core_sec=1.0, context_ms=None,
                backend="auto", **opts):
    """Pick the native backend when the DLL exposes the streaming ABI."""
    if backend == "python":
        return StreamResampler(src, dst, channels, core_sec=core_sec,
                               context_ms=context_ms, **opts)
    if backend in ("native", "auto"):
        try:
            return NativeStreamResampler(src, dst, channels, core_sec=core_sec,
                                         context_ms=context_ms, **opts)
        except Exception:
            if backend == "native":
                raise
    return StreamResampler(src, dst, channels, core_sec=core_sec,
                           context_ms=context_ms, **opts)

