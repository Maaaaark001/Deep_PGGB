"""转换流水线：解码 → 预处理 → 重采样 → 分析 → 编码。

一次 convert() 会同时产出：
  * 输入音频的质量报告
  * 输出音频的质量报告
  * SRC 本身的保真度（与参考实现做零差测试）
  * 客观结论卡片（人话）
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable

import numpy as np

from . import codecs, config, engines, metrics, quality
from .probe import MediaInfo, probe

Progress = Callable[[float, str], None]


@dataclass
class ConvertRequest:
    input_path: str
    output_path: str
    fmt: str = "wav"
    bits: int = 24
    dst_rate: int = 0                    # 0 = 保持源采样率
    channels: int | None = None          # None = 保持
    engine: str = "r8b"
    engine_opts: dict = field(default_factory=dict)
    gain_db: float | None = None
    normalize_dbfs: float | None = None
    dither: bool = True
    dither_filter: str = "shibata"
    dither_amount: float | None = None
    noise_shape: bool = True
    format_params: dict = field(default_factory=dict)
    trim_start: float | None = None
    trim_end: float | None = None
    analyze: bool = True
    null_test: bool = True
    reference_engine: str = "r8b"


@dataclass
class ConvertResult:
    ok: bool = False
    error: str | None = None
    output_path: str = ""
    src_rate: int = 0
    dst_rate: int = 0
    channels: int = 0
    frames_in: int = 0
    frames_out: int = 0
    duration: float = 0.0
    elapsed: float = 0.0
    speed_x: float = 0.0
    engine: str = ""
    engine_label: str = ""
    input_info: dict = field(default_factory=dict)
    output_info: dict = field(default_factory=dict)
    input_report: dict = field(default_factory=dict)
    output_report: dict = field(default_factory=dict)
    null: dict = field(default_factory=dict)
    src_measure: dict = field(default_factory=dict)
    input_verdicts: list = field(default_factory=list)
    output_verdicts: list = field(default_factory=list)
    src_verdicts: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _noop(_p: float, _m: str) -> None:
    return None


def convert(req: ConvertRequest, progress: Progress | None = None) -> ConvertResult:
    progress = progress or _noop
    res = ConvertResult()
    t_start = time.perf_counter()
    try:
        progress(0.02, "探测输入文件…")
        info = probe(req.input_path)
        if not info.ok:
            raise RuntimeError(info.error or "无法读取输入文件")
        res.input_info = info.to_dict()
        src_rate = info.sample_rate or 44100
        res.src_rate = src_rate
        dst_rate = int(req.dst_rate or src_rate)
        res.dst_rate = dst_rate

        # ---- 解码 ------------------------------------------------------
        progress(0.08, "解码为 float64…")
        trim = None
        if req.trim_start is not None or req.trim_end is not None:
            s = req.trim_start or 0.0
            e = req.trim_end
            trim = (s, (e - s) if e and e > s else None)
        with codecs.decode(req.input_path, rate=None, channels=req.channels,
                           start=trim[0] if trim else None,
                           duration=trim[1] if trim else None) as dec:
            y = np.array(dec.data, dtype=np.float64) if not isinstance(dec.data, np.memmap) \
                else np.array(dec.data, dtype=np.float64)
            res.channels = dec.channels
            res.frames_in = dec.frames
            res.duration = dec.duration
            if y.shape[0] == 0:
                raise RuntimeError("解码结果为空")
            if dst_rate and dst_rate != dec.rate:
                src_rate = dec.rate
                res.src_rate = src_rate

            # ---- 输入分析 ---------------------------------------------
            in_rep = None
            if req.analyze:
                progress(0.18, "分析输入音频质量…")
                in_rep = metrics.analyze(y, dec.rate)
                res.input_report = in_rep.to_dict()
                res.input_verdicts = quality.verdict_audio(in_rep, info)

            # ---- 预处理 -----------------------------------------------
            if req.normalize_dbfs is not None:
                peak = float(np.max(np.abs(y))) if y.size else 0.0
                if peak > 1e-12:
                    target = 10.0 ** (req.normalize_dbfs / 20.0)
                    y = y * (target / peak)
                    res.warnings.append(
                        f"已归一化：峰值 {20*math.log10(peak):.2f} dBFS → "
                        f"{req.normalize_dbfs:.2f} dBFS")
            if req.gain_db:
                y = y * (10.0 ** (req.gain_db / 20.0))
                res.warnings.append(f"已施加增益 {req.gain_db:+.2f} dB")

            # ---- 重采样 -----------------------------------------------
            progress(0.32, f"重采样 {src_rate} → {dst_rate} Hz（{req.engine}）…")
            t0 = time.perf_counter()
            if dst_rate != src_rate:
                out = engines.resample(y, src_rate, dst_rate, req.engine, req.engine_opts)
            else:
                out = y
            res.elapsed = time.perf_counter() - t0
            res.frames_out = int(out.shape[0])
            res.engine = req.engine
            spec = engines.ENGINES.get(req.engine)
            res.engine_label = spec.label if spec else req.engine
            if res.elapsed > 0 and res.duration > 0:
                res.speed_x = round(res.duration / res.elapsed, 1)

            # 峰值过冲保护
            peak_out = float(np.max(np.abs(out))) if out.size else 0.0
            if peak_out > 1.0:
                res.warnings.append(
                    f"重采样后峰值达到 {20*math.log10(peak_out):.2f} dBFS（超过满刻度 "
                    f"{20*math.log10(peak_out):.2f} dB），编码时会被削波。"
                    "建议先降 −1 dB 再转换。")

            # ---- 零差测试 ---------------------------------------------
            # 参考实现是"最严格的 r8brain"（1% 过渡带 / 250 dB）。
            # 如果当前引擎就是 r8brain 但参数更松（例如默认的 2% 过渡带），
            # 那么零差测试依然有意义：它量的是"你为了速度放弃了多少精度"。
            # 只有当参数已经等于参考本身时才跳过，改测绝对保真度（杂散/镜像/混叠）。
            strict = {"transband": 1.0, "atten": 250.0, "quality": "full", "phase": "linear"}

            def _same(v, ref) -> bool:
                try:
                    return abs(float(v) - float(ref)) < 1e-9
                except (TypeError, ValueError):
                    return str(v) == str(ref)

            same_as_ref = (req.engine == req.reference_engine
                           and all(_same(req.engine_opts.get(k, strict[k]), strict[k])
                                   for k in strict))
            if req.null_test and dst_rate != src_rate and not same_as_ref:
                progress(0.55, "零差测试（对比参考实现）…")
                try:
                    res.null = quality.null_test(y, src_rate, dst_rate, req.engine,
                                                 req.engine_opts, req.reference_engine)
                    if req.engine == req.reference_engine:
                        res.null["note"] = "参考 = 同一引擎的更严格参数（1% 过渡带 / 250 dB）"
                except Exception as exc:  # noqa: BLE001
                    res.warnings.append(f"零差测试失败：{exc}")
            elif req.null_test and dst_rate != src_rate:
                # 已经是参考本身：改测绝对保真度，比空着有用
                progress(0.55, "测量 SRC 绝对保真度…")
                try:
                    m = quality.measure_engine(req.engine, req.engine_opts, seconds=3.0)
                    res.src_measure = m.to_dict()
                except Exception as exc:  # noqa: BLE001
                    res.warnings.append(f"保真度测量失败：{exc}")

            # ---- 输出分析 ---------------------------------------------
            if req.analyze:
                progress(0.68, "分析输出音频质量…")
                out_rep = metrics.analyze(out, dst_rate)
                res.output_report = out_rep.to_dict()
                res.output_verdicts = quality.verdict_audio(out_rep, None)
                res.src_verdicts = _src_conclusions(res, in_rep, out_rep)

            # ---- 编码 -------------------------------------------------
            progress(0.85, "编码输出…")
            spec_fmt = codecs.FORMATS.get(req.fmt)
            if spec_fmt is None:
                raise RuntimeError(f"未知输出格式：{req.fmt}")
            opt = codecs.EncodeOptions(
                fmt=req.fmt, bits=req.bits, dither=req.dither,
                dither_filter=req.dither_filter, dither_amount=req.dither_amount,
                noise_shape=req.noise_shape, params=req.format_params or {})
            codecs.encode(out, dst_rate, req.output_path, opt)
            res.output_path = str(req.output_path)
            res.output_info = probe(req.output_path).to_dict()

        res.ok = True
        progress(1.0, "完成")
    except Exception as exc:  # noqa: BLE001
        res.ok = False
        res.error = str(exc)[:1200]
        progress(1.0, "失败")
    res.elapsed_total = round(time.perf_counter() - t_start, 3)
    return res


def _src_conclusions(res: ConvertResult, in_rep, out_rep) -> list[dict]:
    """把零差测试 + 输入/输出对比翻译成 SRC 层面的结论。"""
    out: list[dict] = []
    n = res.null or {}
    if n.get("ok") and not n.get("skipped"):
        # 判级与展示都用"可闻带深度"：全带深度会被 20 kHz 以上的滤波器差异主导，
        # 那个数字看着吓人，实际一个耳朵听不见的 Hz 都不在里面。
        depth = n.get("null_depth_audible_db", n.get("null_depth_db", -300))
        full = n.get("null_depth_db")
        v = n.get("verdict") or quality.verdict_null(depth, full_depth=full)
        extra = ""
        if n.get("truncated"):
            extra = f"，测试窗为文件中间 {n.get('seconds_tested', 0):.0f} 秒"
        out.append({
            "level": v["level"], "title": f"SRC 保真度：{v['label']}",
            "text": v["text"] + f"（参考实现：r8brain full / 过渡带 1% / 阻带 250 dB{extra}）",
            "metric": f"{depth:.1f} dB",
        })
        # 可闻性必须看可闻带的误差能量：全带 err_rms 里混着 20 kHz 以上的
        # 滤波器差异，拿它判"能被听出"是错的（demo 素材就会误报 -54 dBFS）。
        aud = n.get("audible_err_dbfs", -300)
        if aud > -60:
            out.append({
                "level": "bad", "title": "误差已进入可闻区间",
                "text": f"20 kHz 以下与参考实现的误差 RMS 为 {aud:.1f} dBFS，"
                        f"相关性 {n.get('correlation', 0):.5f}。这个量级的差异在 ABX 测试中可以被听出。",
                "metric": f"{aud:.1f} dBFS",
            })

    if in_rep is not None and out_rep is not None:
        # 峰值变化
        dpk = out_rep.peak_dbfs - in_rep.peak_dbfs
        if abs(dpk) > 0.5:
            out.append({
                "level": "info", "title": "峰值变化",
                "text": f"重采样后峰值变化 {dpk:+.2f} dB（{in_rep.peak_dbfs:.2f} → "
                        f"{out_rep.peak_dbfs:.2f} dBFS）。"
                        "这是滤波器过冲（overshoot）的正常表现，升采样时通常略微升高。",
                "metric": f"{dpk:+.2f} dB",
            })
        # 带宽变化
        bw_in = in_rep.bandwidth.get("hz", 0)
        bw_out = out_rep.bandwidth.get("hz", 0)
        if res.dst_rate > res.src_rate and bw_in > 0:
            out.append({
                "level": "ok" if bw_out >= bw_in * 0.95 else "warn",
                "title": "带宽保持",
                "text": f"输入带宽 {bw_in/1000:.2f} kHz，输出 {bw_out/1000:.2f} kHz。"
                        + ("升采样不会创造新的高频，带宽保持说明滤波器没有吃掉有效内容。"
                           if bw_out >= bw_in * 0.95 else
                           "输出带宽明显低于输入，说明重采样滤波器的过渡带过宽，"
                           "切掉了部分高频。可以减小过渡带宽度（如 r8b 的 transband）。"),
                "metric": f"{bw_out/1000:.2f} kHz",
            })
        elif res.dst_rate < res.src_rate:
            nyq = res.dst_rate / 2.0
            out.append({
                "level": "ok", "title": "下采样带宽",
                "text": f"目标采样率 {res.dst_rate} Hz 的 Nyquist 为 {nyq/1000:.1f} kHz，"
                        f"输出实际带宽 {bw_out/1000:.2f} kHz。"
                        + ("高于 Nyquist 的内容已被正确滤除。" if bw_out <= nyq * 1.02 else
                           "输出带宽超过了 Nyquist，说明滤波器没有充分衰减，可能存在混叠。"),
                "metric": f"{bw_out/1000:.2f} kHz",
            })
        # 有效位深
        if out_rep.effective_bits and in_rep.effective_bits:
            if out_rep.effective_bits < in_rep.effective_bits - 1:
                out.append({
                    "level": "warn", "title": "有效位深下降",
                    "text": f"输入有效位深约 {in_rep.effective_bits} bit，输出只有 "
                            f"{out_rep.effective_bits} bit。输出位深设置可能低于源文件，"
                            "或者 dither 噪声抬高了噪声底。",
                    "metric": f"{in_rep.effective_bits}→{out_rep.effective_bits} bit",
                })
    return out


def quick_probe(path: str) -> dict:
    """不解码，只给文件元数据（用于上传后立即回显）。"""
    info = probe(path)
    d = info.to_dict()
    if info.ok:
        d["estimated_frames"] = int(info.duration * info.sample_rate) if info.sample_rate else 0
    return d
