"""格式注册表 + 解码 / 编码。

解码统一走 ffmpeg -> float64（绝不中途降到 16bit）。
编码优先 sox_ng（自带 dither 噪声整形），sox_ng 不支持的容器交给 ffmpeg。
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import config


# --------------------------------------------------------------------------
# 解码
# --------------------------------------------------------------------------
class DecodedAudio:
    """float64 样本 + 临时文件句柄。用完必须 release()。"""

    def __init__(self, data: np.ndarray, rate: int, channels: int, tmp: Path | None):
        self.data = data
        self.rate = int(rate)
        self.channels = int(channels)
        self._tmp = tmp

    @property
    def frames(self) -> int:
        return int(self.data.shape[0])

    @property
    def duration(self) -> float:
        return self.frames / float(self.rate) if self.rate else 0.0

    def close(self) -> None:
        if isinstance(self.data, np.memmap):
            try:
                self.data._mmap.close()  # type: ignore[attr-defined]
            except Exception:
                pass
        if self._tmp is not None:
            try:
                os.unlink(self._tmp)
            except OSError:
                pass
            self._tmp = None

    def __enter__(self) -> "DecodedAudio":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def _tmpdir() -> Path:
    config.ensure_dirs()
    d = Path(tempfile.mkdtemp(prefix="dec_", dir=str(config.WORK)))
    return d


def decode(path: str | Path, *, rate: int | None = None, channels: int | None = None,
           start: float | None = None, duration: float | None = None,
           memmap_threshold_bytes: int = 256 * 1024**2) -> DecodedAudio:
    """把任意文件解码成 float64 交错数组 (frames, channels)。

    rate      : 目标采样率；None 表示保持源采样率（SRC 前必须保持！）
    channels  : 目标声道数；None 表示保持
    start/duration : 秒；用于试听与"只分析前 N 秒"
    """
    if config.FFMPEG is None:
        raise RuntimeError("未找到 ffmpeg，无法解码")
    src = Path(path)
    if not src.is_file():
        raise FileNotFoundError(str(src))

    tmpd = _tmpdir()
    out = tmpd / "audio.f64"
    cmd = [str(config.FFMPEG), "-v", "error", "-nostdin", "-y", "-i", str(src)]
    if start is not None or duration is not None:
        parts = []
        if start:
            parts.append(f"start={start}")
        if duration:
            parts.append(f"end={start + duration if start else duration}")
        cmd += ["-af", "atrim=" + ":".join(parts)]
    if channels:
        cmd += ["-ac", str(channels)]
    if rate:
        cmd += ["-ar", str(rate)]
    cmd += ["-map", "0:a:0", "-f", "f64le", "-acodec", "pcm_f64le", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if r.returncode != 0 or not out.is_file():
        raise RuntimeError("解码失败: " + (r.stderr or "").strip()[-600:])

    # 从流信息里拿真实声道/采样率（ffmpeg 可能做了隐式变换）
    nch = channels or _channels_of(src)
    fs = rate or _rate_of(src)
    size = out.stat().st_size
    nframes = size // (8 * nch)
    if nframes == 0:
        raise RuntimeError("解码结果为空（文件可能不含音频）")
    if size >= memmap_threshold_bytes:
        data = np.memmap(out, dtype="<f8", mode="r", shape=(nframes, nch))
    else:
        data = np.fromfile(out, dtype="<f8", count=nframes * nch).reshape(nframes, nch)
        try:
            os.unlink(out)
        except OSError:
            pass
        out = None
    return DecodedAudio(data, fs, nch, out)


def _channels_of(path: Path) -> int:
    from .probe import probe

    info = probe(path)
    return info.channels or 2


def _rate_of(path: Path) -> int:
    from .probe import probe

    info = probe(path)
    return info.sample_rate or 44100


# --------------------------------------------------------------------------
# 格式注册表
# --------------------------------------------------------------------------
@dataclass
class FormatSpec:
    key: str
    label: str
    ext: str
    engine: str                     # "soxng" | "ffmpeg"
    codec: str                      # ffmpeg 编码器名（engine=ffmpeg 时用）
    lossless: bool = True
    bits: tuple[int, ...] = (16, 24, 32)
    default_bits: int = 24
    note: str = ""
    params: list[dict] = field(default_factory=list)   # 见 PARAM 说明


def _p(key, label, kind, default, desc, **kw) -> dict:
    d = {"key": key, "label": label, "kind": kind, "default": default, "desc": desc}
    d.update(kw)
    return d


FORMATS: dict[str, FormatSpec] = {}


def _reg(spec: FormatSpec) -> None:
    FORMATS[spec.key] = spec


_reg(FormatSpec(
    "wav", "WAV / PCM", "wav", "soxng", "pcm_s24le", True, (16, 24, 32), 24,
    "最通用的无损容器。16/24bit 为整数 PCM，32bit 可选整数或浮点。",
    [_p("float", "32bit 用浮点", "bool", False, "开启后 32bit 输出为 IEEE float（无量化、无 dither，动态范围最大，但部分老播放器不识别）。"),
     _p("compression", "压缩方式", "select", "plain", "WAV 的压缩方式。plain 兼容性最好。",
        options=[("plain", "无压缩 PCM"), ("wavpack", "WavPack 无损（体积小 30-50%）")])],
))
_reg(FormatSpec(
    "flac", "FLAC 无损", "flac", "soxng", "flac", True, (16, 24), 24,
    "无损压缩，体积约为 WAV 的 50-70%，元数据友好。",
    [_p("compression", "压缩等级", "int", 8, "0-8。越大体积越小、编码越慢，解码速度不变。8 为默认最佳。", min=0, max=8, step=1),
     _p("blocksize", "块大小", "int", 4096, "编码块样本数，影响压缩率与寻址粒度。常用 4096。", min=1024, max=16384, step=1024)],
))
_reg(FormatSpec(
    "aiff", "AIFF", "aiff", "soxng", "pcm_s24be", True, (16, 24, 32), 24,
    "苹果无损容器，大端 PCM。老式 Pro Tools / Logic 工作流常用。",
))
_reg(FormatSpec(
    "caf", "CAF (Core Audio)", "caf", "soxng", "pcm_s24be", True, (16, 24, 32), 24,
    "苹果 Core Audio 容器，可存超过 4GB 的音频，支持更多声道。",
))
_reg(FormatSpec(
    "w64", "Wave64", "w64", "soxng", "pcm_s24le", True, (16, 24, 32), 24,
    "Sony 的 64 位 WAV 变体，绕开 4GB 限制。",
))
_reg(FormatSpec(
    "au", "AU / Sun", "au", "soxng", "pcm_s24be", True, (16, 24, 32), 24,
    "Unix 传统音频格式，大端。",
))
_reg(FormatSpec(
    "mp3", "MP3", "mp3", "ffmpeg", "libmp3lame", False, (16,), 16,
    "兼容性之王。有损，会切掉 16 kHz 以上。",
    [_p("bitrate", "码率 (kbps)", "int", 320, "CBR 码率。128 一般、192 良好、320 接近透明。", min=32, max=320, step=32),
     _p("mode", "立体声模式", "select", "joint", "joint 联合立体声最省码率；stereo 独立；mono 单声道。",
        options=[("joint", "Joint Stereo"), ("stereo", "Stereo"), ("mono", "Mono")])],
))
_reg(FormatSpec(
    "ogg", "Ogg Vorbis", "ogg", "ffmpeg", "libvorbis", False, (16,), 16,
    "开源有损格式，同码率下通常优于 MP3，尤其 16 kHz 以上。",
    [_p("quality", "质量 q", "float", 8.0, "0-10。q6≈160kbps、q8≈256kbps、q10≈500kbps。", min=0, max=10, step=0.5)],
))
_reg(FormatSpec(
    "opus", "Opus", "opus", "ffmpeg", "libopus", False, (16,), 16,
    "现代低延迟有损格式，语音与音乐都强，低码率优势明显。",
    [_p("bitrate", "码率 (kbps)", "int", 192, "6-512。64 可听、128 良好、192 接近透明。", min=6, max=512, step=6),
     _p("vbr", "VBR 模式", "select", "on", "on 音质优先；off 恒定码率（流媒体友好）。",
        options=[("on", "VBR 开"), ("off", "CBR")])],
))
_reg(FormatSpec(
    "m4a_aac", "M4A / AAC", "m4a", "ffmpeg", "aac", False, (16,), 16,
    "苹果生态标准，AAC-LC。",
    [_p("bitrate", "码率 (kbps)", "int", 256, "64-512。AAC 在 128 以上开始接近透明。", min=64, max=512, step=32)],
))
_reg(FormatSpec(
    "m4a_alac", "M4A / ALAC", "m4a", "ffmpeg", "alac", True, (16, 24), 24,
    "苹果无损压缩，体积约为 WAV 的 60%。",
))
_reg(FormatSpec(
    "wv", "WavPack", "wv", "ffmpeg", "wavpack", True, (16, 24, 32), 24,
    "无损（也可混合有损），压缩率优于 FLAC，支持 32bit 浮点。",
))
_reg(FormatSpec(
    "tta", "TTA", "tta", "ffmpeg", "tta", True, (16, 24), 24,
    "True Audio，实时无损解码，适合嵌入式播放器。",
))
_reg(FormatSpec(
    "dsf", "DSF / DSD", "dsf", "soxng", "dsd", True, (1,), 1,
    "1bit DSD。体积巨大（DSD64 立体声 ≈ 5.6 Mbps）。只建议在 DSD 工作流中使用。",
    [_p("dsd_rate", "DSD 倍率", "select", "2822400", "DSD64=2.8224MHz、DSD128=5.6448MHz、DSD256=11.2896MHz。",
        options=[("2822400", "DSD64"), ("5644800", "DSD128"), ("11289600", "DSD256")])],
))

SOXNG_EXTS = {f.ext for f in FORMATS.values() if f.engine == "soxng"}


def format_choices() -> list[tuple[str, str]]:
    return [(k, f"{v.label}  (.{v.ext})") for k, v in FORMATS.items()]


def guess_format(path: str | Path) -> FormatSpec | None:
    ext = Path(path).suffix.lower().lstrip(".")
    for f in FORMATS.values():
        if f.ext == ext:
            return f
    if ext in ("aif",):
        return FORMATS["aiff"]
    if ext in ("oga",):
        return FORMATS["ogg"]
    return None


# --------------------------------------------------------------------------
# 编码
# --------------------------------------------------------------------------
def _write_stage_f32(y: np.ndarray, rate: int, path: Path) -> None:
    """把 float64 写成 float32 WAV，供 sox_ng 读取（float32 足够承载 24bit 内容）。"""
    import scipy.io.wavfile as wf

    arr = np.asarray(y, dtype="<f4")
    wf.write(str(path), int(rate), arr)


def _write_stage_f64(y: np.ndarray, rate: int, path: Path) -> None:
    """无损中间文件：raw float64。用于 32bit float 与 DSD 路径。"""
    np.asarray(y, dtype="<f8").tofile(str(path))


@dataclass
class EncodeOptions:
    fmt: str = "wav"
    bits: int = 24
    dither: bool = True
    dither_filter: str = "shibata"
    dither_amount: float | None = None
    noise_shape: bool = True
    params: dict = field(default_factory=dict)


def _soxng_encode(y: np.ndarray, rate: int, out: Path, opt: EncodeOptions) -> None:
    spec = FORMATS[opt.fmt]
    tmpd = _tmpdir()
    try:
        if spec.ext == "dsf":
            raw = tmpd / "stage.f64"
            _write_stage_f64(y, rate, raw)
            dsd = int(opt.params.get("dsd_rate", 2822400))
            cmd = [str(config.SOXNG), "-q", "-t", "raw", "-r", str(rate), "-e", "floating-point",
                   "-b", "64", "-c", str(y.shape[1]), str(raw), str(out),
                   "rate", "-v", str(dsd), "sdm"]
            _run(cmd)
            return
        stage = tmpd / "stage.wav"
        _write_stage_f32(y, rate, stage)
        cmd = [str(config.SOXNG), "-q", str(stage)]
        if spec.ext == "wav" and opt.bits == 32 and opt.params.get("float"):
            cmd += ["-e", "floating-point", "-b", "32"]
        else:
            cmd += ["-b", str(opt.bits)]
        if spec.ext == "flac":
            cmd += ["-C", str(int(opt.params.get("compression", 8)))]
        if spec.ext == "wav" and opt.params.get("compression") == "wavpack":
            cmd += ["-t", "wv"]
        cmd.append(str(out))
        if opt.dither and opt.bits in (8, 16, 24) and not (spec.ext == "wav" and opt.bits == 32):
            dith = ["dither"]
            if opt.noise_shape:
                dith += ["-s", "-f", opt.dither_filter]
            else:
                dith += ["-S"]
            if opt.dither_amount is not None:
                dith += ["-a", str(opt.dither_amount)]
            dith += ["-p", str(opt.bits)]
            cmd += dith
        _run(cmd)
    finally:
        _cleanup(tmpd)


def _ffmpeg_encode(y: np.ndarray, rate: int, out: Path, opt: EncodeOptions) -> None:
    spec = FORMATS[opt.fmt]
    tmpd = _tmpdir()
    try:
        stage = tmpd / "stage.wav"
        _write_stage_f32(y, rate, stage)
        cmd = [str(config.FFMPEG), "-v", "error", "-nostdin", "-y", "-i", str(stage),
               "-c:a", spec.codec]
        p = opt.params
        if spec.key == "mp3":
            cmd += ["-b:a", f"{int(p.get('bitrate', 320))}k"]
            mode = p.get("mode", "joint")
            if mode == "joint":
                cmd += ["-joint_stereo", "1"]
            elif mode == "mono":
                cmd += ["-ac", "1"]
            else:
                cmd += ["-joint_stereo", "0"]
        elif spec.key == "ogg":
            cmd += ["-q:a", str(float(p.get("quality", 8.0)))]
        elif spec.key == "opus":
            cmd += ["-b:a", f"{int(p.get('bitrate', 192))}k"]
            cmd += ["-vbr", "on" if p.get("vbr", "on") == "on" else "off"]
        elif spec.key == "m4a_aac":
            cmd += ["-b:a", f"{int(p.get('bitrate', 256))}k", "-profile:a", "aac_low"]
        elif spec.key == "m4a_alac":
            cmd += ["-sample_fmt", "s32p" if opt.bits > 16 else "s16p"]
        elif spec.key in ("wv", "tta"):
            pass
        if spec.lossless and spec.key != "m4a_alac":
            cmd += ["-bits_per_raw_sample", str(opt.bits)]
        cmd.append(str(out))
        _run(cmd)
    finally:
        _cleanup(tmpd)


def encode(y: np.ndarray, rate: int, out: str | Path, opt: EncodeOptions) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    spec = FORMATS[opt.fmt]
    if spec.engine == "soxng" and config.SOXNG is not None:
        _soxng_encode(y, rate, out, opt)
    else:
        if config.FFMPEG is None:
            raise RuntimeError("未找到 ffmpeg，无法编码该格式")
        _ffmpeg_encode(y, rate, out, opt)
    if not out.is_file():
        raise RuntimeError("编码未产生输出文件")
    return out


def _run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        raise RuntimeError("命令失败: " + " ".join(cmd[:4]) + "\n" + (r.stderr or "")[-700:])


def _cleanup(d: Path) -> None:
    import shutil

    shutil.rmtree(d, ignore_errors=True)


def output_name(src: str | Path, spec: FormatSpec, rate: int, tag: str = "") -> str:
    stem = Path(src).stem
    suffix = f"_{rate//1000}k" if rate else ""
    if tag:
        suffix += "_" + tag
    return f"{stem}{suffix}.{spec.ext}"
