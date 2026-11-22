"""路径、外部二进制与运行时常量。

二进制发现顺序（每个都可用环境变量覆盖）：
    SRCTOOL_BIN  -> 项目内 bin/ -> src-toolchain skill 的 bin/ -> PATH
    FFMPEG       -> PATH -> %TEMP%\\ffm\\...\\bin\\ffmpeg.exe -> imageio_ffmpeg
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

APP_NAME = "SonarSRC"
APP_TITLE = "SonarSRC · 多格式采样率工具箱"
APP_VERSION = "1.0.0"

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"
CACHE = ROOT / "cache"
UI_ASSETS = ROOT / "srctool" / "ui" / "assets"

DEFAULT_SKILL_BIN = Path.home() / ".dsh" / "skills" / "src-toolchain" / "bin"
# Deep_PGGB ships its own folder (exe + FFTW DLLs), not a loose binary in bin/.
SKILL_ROOT = DEFAULT_SKILL_BIN.parent
DPGGB_DIRS = [ROOT / "deeppggb", SKILL_ROOT / "deeppggb", SKILL_ROOT / "deeppggb" / "bin"]


def _bin_dirs() -> list[Path]:
    dirs: list[Path] = []
    env = os.environ.get("SRCTOOL_BIN")
    if env:
        dirs.append(Path(env))
    dirs.append(ROOT / "bin")
    dirs.append(DEFAULT_SKILL_BIN)
    return dirs


def _find_tool(*names: str) -> Path | None:
    for d in _bin_dirs():
        for n in names:
            p = d / n
            if p.is_file():
                return p
    for n in names:
        w = shutil.which(n)
        if w:
            return Path(w)
    return None


SOXNG = _find_tool("sox_ng.exe", "sox_ng")
R8B = _find_tool("r8b.exe", "r8b")
SSRC = _find_tool("ssrc.exe", "ssrc")


def _find_dpggb() -> Path | None:
    """dpggb.exe lives beside its FFTW DLLs, so it is found by folder, not by PATH."""
    for d in DPGGB_DIRS:
        for name in ("dpggb.exe", "dpggb"):
            p = d / name
            if p.is_file():
                return p
    return None


DPGGB = _find_dpggb()


def _find_dpggb_dll() -> Path | None:
    """dpggb.dll lets the toolbox call the engine in process.

    The exe path copies the whole buffer through a pipe (127 MB in, 277 MB out on
    a 180 s stereo job), which measured 0.84 s of pure transfer - more than the
    resampling. In process there is no transfer at all, so prefer the DLL and
    fall back to the exe when it is missing.
    """
    for d in DPGGB_DIRS:
        p = d / "dpggb.dll"
        if p.is_file():
            return p
    return None


DPGGB_DLL = _find_dpggb_dll()


def _find_pggb() -> Path | None:
    """PGGB-IT! 的内核 pggb_256_it.exe。

    它**只做整数倍率的上采样**（第二个位置参数 um 必须是 ≥1 的整数，非整数会被
    静默当成 1，即原样返回），所以它只作为基准对照出现，不能做转换引擎。
    官方 GUI 只是这个控制台程序的包装，DSP 全在它里面。
    """
    local = Path(os.environ.get("LOCALAPPDATA") or "")
    cands: list[Path] = []
    if local:
        cands.append(local / "Programs" / "PGGB-IT!" / "pggb_256_it.exe")
    cands.append(ROOT / "bin" / "pggb_256_it.exe")
    for c in cands:
        if c.is_file():
            return c
    return None


PGGB = _find_pggb()


def _find_ffmpeg() -> Path | None:
    cands: list[Path] = []
    env = os.environ.get("FFMPEG")
    if env:
        cands.append(Path(env))
    w = shutil.which("ffmpeg")
    if w:
        cands.append(Path(w))
    tmp = Path(os.environ.get("TEMP") or os.environ.get("TMP") or "C:/Windows/Temp")
    cands.append(tmp / "ffm" / "ffmpeg-master-latest-win64-gpl" / "bin" / "ffmpeg.exe")
    cands.append(ROOT / "bin" / "ffmpeg.exe")
    # PGGB-IT! ships a full GPL ffmpeg 8.1.1 (libmp3lame/libopus/libvorbis/alac/wavpack/tta,
    # soxr resampler, DSD decoders) — a complete build we can borrow instead of downloading one.
    local = Path(os.environ.get("LOCALAPPDATA") or "")
    if local:
        cands.append(local / "Programs" / "PGGB-IT!" / "ffmpeg.exe")
    for c in cands:
        if c.is_file():
            return c
    try:  # 最后的兜底：imageio-ffmpeg 自带的精简版（无 soxr、无 mp3）
        import imageio_ffmpeg  # type: ignore

        p = Path(imageio_ffmpeg.get_ffmpeg_exe())
        if p.is_file():
            return p
    except Exception:
        pass
    return None


FFMPEG = _find_ffmpeg()
FFPROBE: Path | None = None
if FFMPEG is not None:
    sibling = FFMPEG.with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
    if sibling.is_file():
        FFPROBE = sibling
    else:
        w = shutil.which("ffprobe")
        FFPROBE = Path(w) if w else None

# ---- 运行时限制 -----------------------------------------------------------
MAX_ANALYSIS_SECONDS = 600.0      # 单文件分析最多取多少秒
# 体检一次最多处理多少"样本"（帧 × 声道）。200M 个 float64 = 1.6 GB 峰值，
# 12.7 GB 的机器上留足余量。换算成秒数 = ANALYSIS_BUDGET_SAMPLES / (采样率 × 声道)：
#   44.1k 立体声 → 2268 s（一首歌永远落在全长档）
#   192k 8 声道  → 130 s（这种素材必须抽样，否则光解码就 7 GB）
ANALYSIS_BUDGET_SAMPLES = 200_000_000
MAX_ARRAY_BYTES = 768 * 1024**2   # 数组型引擎（soxr/scipy）允许的最大 float64 体积
PREVIEW_SECONDS = 30.0            # 试听/预览截取长度
TARGET_RATES = [8000, 11025, 12000, 16000, 22050, 24000, 32000, 44100, 48000,
                88200, 96000, 176400, 192000, 352800, 384000, 705600, 768000]
STANDARD_BITS = [8, 16, 24, 32]


def ensure_dirs() -> None:
    for d in (WORK, CACHE):
        d.mkdir(parents=True, exist_ok=True)


def env_report() -> dict:
    """给 UI 的"关于/环境"面板用。"""
    def _v(p: Path | None) -> str | None:
        return str(p) if p else None

    return {
        "app": f"{APP_NAME} {APP_VERSION}",
        "python": os.sys.version.split()[0],
        "ffmpeg": _v(FFMPEG),
        "ffprobe": _v(FFPROBE),
        "sox_ng": _v(SOXNG),
        "r8brain": _v(R8B),
        "ssrc": _v(SSRC),
        "deeppggb": _v(DPGGB),
        "pggb": _v(PGGB),
        "work": str(WORK),
    }
