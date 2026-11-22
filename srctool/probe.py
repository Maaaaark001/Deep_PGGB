"""媒体探测：ffprobe 元数据 + 便捷的时长/编码判定。"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, asdict, field
from pathlib import Path

from . import config


@dataclass
class MediaInfo:
    path: str
    ok: bool = True
    error: str | None = None
    container: str = ""
    codec: str = ""
    profile: str = ""
    sample_rate: int = 0
    channels: int = 0
    channel_layout: str = ""
    bit_depth: int | None = None          # 容器/流声明的位深
    sample_fmt: str = ""                  # s16 / s32 / fltp ...
    duration: float = 0.0
    size: int = 0
    bitrate: int = 0
    tags: dict = field(default_factory=dict)
    lossless: bool = True
    dsd: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


_LOSSLESS_CODECS = {
    "flac", "alac", "wavpack", "tta", "ape", "mlp", "truehd", "shorten",
    "pcm_s8", "pcm_u8", "pcm_s16le", "pcm_s16be", "pcm_s24le", "pcm_s24be",
    "pcm_s32le", "pcm_s32be", "pcm_f32le", "pcm_f64le", "pcm_s64le",
    "dsd_lsbf", "dsd_msbf", "dsd_lsbf_planar", "dsd_msbf_planar",
    "wmalossless", "tak", "als",
}


def _run_json(args: list[str]) -> dict:
    r = subprocess.run(args, capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "").strip()[-800:] or "ffprobe failed")
    return json.loads(r.stdout)


def probe(path: str | Path) -> MediaInfo:
    p = Path(path)
    info = MediaInfo(path=str(p))
    if not p.is_file():
        info.ok = False
        info.error = "文件不存在"
        return info
    info.size = p.stat().st_size
    if config.FFPROBE is None:
        info.ok = False
        info.error = "未找到 ffprobe"
        return info
    try:
        d = _run_json([str(config.FFPROBE), "-v", "error", "-show_streams",
                       "-show_format", "-of", "json", str(p)])
    except Exception as exc:  # noqa: BLE001
        info.ok = False
        info.error = f"ffprobe 失败: {exc}"
        return info

    streams = d.get("streams") or []
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if audio is None:
        info.ok = False
        info.error = "没有音频流"
        return info

    fmt = d.get("format") or {}
    info.container = (fmt.get("format_name") or "").split(",")[0]
    info.codec = audio.get("codec_name") or ""
    info.profile = str(audio.get("profile") or "")
    try:
        info.sample_rate = int(audio.get("sample_rate") or 0)
    except ValueError:
        info.sample_rate = 0
    info.channels = int(audio.get("channels") or 0)
    info.channel_layout = audio.get("channel_layout") or ""
    bits = audio.get("bits_per_raw_sample") or audio.get("bits_per_sample")
    try:
        info.bit_depth = int(bits) if bits else None
    except ValueError:
        info.bit_depth = None
    if info.bit_depth == 0:
        info.bit_depth = None
    info.sample_fmt = audio.get("sample_fmt") or ""
    info.duration = float(fmt.get("duration") or audio.get("duration") or 0.0)
    try:
        info.bitrate = int(fmt.get("bit_rate") or audio.get("bit_rate") or 0)
    except ValueError:
        info.bitrate = 0
    info.tags = {k.lower(): v for k, v in (fmt.get("tags") or {}).items()}
    info.dsd = info.codec.startswith("dsd")
    info.lossless = info.codec in _LOSSLESS_CODECS or info.dsd
    if not info.duration and info.sample_rate and info.bitrate:
        info.duration = info.size * 8.0 / info.bitrate
    return info


def probe_json(path: str | Path) -> dict:
    return probe(path).to_dict()
