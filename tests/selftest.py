"""SonarSRC 自检脚本 —— 不依赖 pytest，直接 python tests/selftest.py 即可。

覆盖：二进制发现 → 解码 → 六台引擎 → 指标 → 质量测量 → 编码 → 流水线 → 绘图数据。
每一节都会打印 PASS/FAIL，最后给出汇总；任何一节失败返回码为 1。
"""
from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np

from srctool import codecs, config, engines, metrics, pipeline, plot, presets, probe, quality

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, fn) -> None:
    t0 = time.time()
    try:
        detail = fn() or ""
        RESULTS.append((name, True, str(detail)))
        print(f"  PASS  {name}  ({time.time() - t0:.2f}s) {detail}")
    except Exception as exc:  # noqa: BLE001
        RESULTS.append((name, False, f"{type(exc).__name__}: {exc}"))
        print(f"  FAIL  {name}  {type(exc).__name__}: {exc}")
        traceback.print_exc(limit=3)


def section(title: str) -> None:
    print("\n" + "=" * 68)
    print(title)
    print("=" * 68)


# --------------------------------------------------------------------------
def test_env() -> str:
    env = config.env_report()
    missing = [k for k in ("ffmpeg", "ffprobe", "sox_ng", "r8brain", "ssrc") if not env.get(k)]
    assert not missing, f"缺少外部二进制：{missing}"
    return f"python {env['python']}"


def _ensure_demo() -> Path:
    """演示素材：8 秒 44.1 kHz 立体声，带限和弦 + 微量噪声。

    素材不进仓库（见 .gitignore 的 *.wav），因此第一次自检时现生成，
    保证 clone 之后无需任何预处理就能直接跑通。
    """
    demo = config.WORK / "demo_44k.wav"
    if demo.exists():
        return demo
    demo.parent.mkdir(parents=True, exist_ok=True)
    rate, n = 44100, 44100 * 8
    t = np.arange(n, dtype=np.int64)

    def tone(hz: int, amp: float) -> np.ndarray:
        # 整数相位递推：避免 sin(2πft) 在 8 秒里的相位累积误差污染素材
        k = (t * int(hz)) % rate
        return amp * np.sin(2 * np.pi * k / rate)

    left = tone(220, 0.30) + tone(880, 0.12) + tone(3520, 0.06)
    right = tone(330, 0.30) + tone(1320, 0.12) + tone(7040, 0.06)
    rng = np.random.default_rng(7)
    y = np.stack([left, right], axis=1) + rng.normal(0.0, 3e-5, (n, 2))
    import soundfile as sf

    sf.write(str(demo), y, rate, subtype="FLOAT")
    return demo


def test_demo() -> str:
    demo = _ensure_demo()
    info = probe.probe(str(demo))
    assert info.ok, info.error
    assert info.sample_rate == 44100 and info.channels == 2, (info.sample_rate, info.channels)
    return f"{info.sample_rate} Hz / {info.channels}ch / {info.duration:.2f}s"


def test_decode(demo: Path) -> str:
    au = codecs.decode(str(demo))
    try:
        y = np.asarray(au.data)
        assert y.ndim == 2 and y.shape[1] == 2, y.shape
        assert au.rate == 44100
        assert np.isfinite(y).all(), "解码结果含 NaN/Inf"
        assert np.abs(y).max() <= 1.5, "解码幅度异常（可能被缩放）"
        return f"{y.shape[0]} 帧 × {y.shape[1]} 声道"
    finally:
        au.close()


def test_engines(demo: Path) -> str:
    au = codecs.decode(str(demo))
    try:
        y = np.asarray(au.data, dtype=np.float64)
    finally:
        au.close()
    seg = y[: 44100 * 2]  # 2 秒足够，避免自检太慢
    notes = []
    for key in engines.available_engines():
        spec = engines.ENGINES[key]
        # 只做整数倍上采样的对照引擎（PGGB）必须走整数倍率，且要能明确拒绝非整数倍
        src, dst = (44100, 88200) if spec.integer_only else (44100, 48000)
        out = engines.resample(seg, src, dst, key, engines.default_opts(key))
        assert out.shape[1] == 2, (key, out.shape)
        expect = int(round(seg.shape[0] * dst / src))
        assert abs(out.shape[0] - expect) <= 8, (key, out.shape[0], expect)
        assert np.isfinite(out).all(), f"{key} 输出含 NaN"
        peak = float(np.abs(out).max())
        assert 0.1 < peak < 1.5, f"{key} 输出电平异常 {peak:.3f}"
        if spec.integer_only:
            # 拒绝比"静默返回没重采样的数据"重要得多：PGGB 内核喂 1.5 会原样返回，
            # 那样测出来的每个指标都"完美"，实际什么都没测。
            try:
                engines.resample(seg, 44100, 48000, key, engines.default_opts(key))
            except RuntimeError:
                pass
            else:
                raise AssertionError(f"{key} 未拒绝非整数倍率 44.1→48")
        notes.append(f"{key}={out.shape[0]}")
    return " ".join(notes)


def test_metrics() -> str:
    rate = 48000
    t = np.arange(rate, dtype=np.float64) / rate
    tone = (0.5 * np.sin(2 * np.pi * 1000.0 * t))[:, None]
    rep = metrics.analyze(tone, rate)
    assert abs(rep.peak_dbfs - (-6.02)) < 0.1, rep.peak_dbfs
    assert abs(rep.rms_dbfs - (-9.03)) < 0.1, rep.rms_dbfs
    assert abs(rep.lufs.get("integrated", 0) - (-9.0)) < 1.5, rep.lufs
    assert abs(rep.crest_db - 3.01) < 0.2, rep.crest_db
    # 纯音的能量只落在基频一根线上，所以"能量降到 −60 dB 的边界"就是 1 kHz 附近
    assert 900 < rep.bandwidth["hz"] < 1200, rep.bandwidth
    return f"peak={rep.peak_dbfs} lufs={rep.lufs.get('integrated')} bw={rep.bandwidth['hz']}"


def test_measure() -> str:
    notes = []
    for key in engines.available_engines():
        m = quality.measure_engine(key, engines.default_opts(key), seconds=2.0)
        assert m.ok, (key, m.error)
        assert m.spur_dbc < -60, (key, m.spur_dbc)
        notes.append(f"{key}:spur={m.spur_dbc:.0f}")
    return " ".join(notes)


def test_imd() -> str:
    """互调失真：单音杂散之外的第二类判据（线性度）。

    这里只做"指标能跑通且量级合理"的断言，不钉死具体数字——具体数字属于测量报告，
    钉进测试会在换编译器/换 FFTW 版本时无谓地失败。
    """
    notes = []
    for key in engines.available_engines():
        m = quality.measure_engine(key, engines.default_opts(key), seconds=2.0,
                                   do_passband=False, do_speed=False)
        assert m.ok, (key, m.error)
        assert m.imd_dbc < -60, (key, m.imd_dbc)
        assert m.imd_smpte_dbc < -60, (key, m.imd_smpte_dbc)
        assert m.mt_dbc < -50, (key, m.mt_dbc)
        notes.append(f"{key}:imd={m.imd_dbc:.0f}/mt={m.mt_dbc:.0f}")
    # Deep_PGGB 必须显著优于最差的引擎，否则说明指标没有区分力
    d = quality.measure_engine("dpggb", engines.default_opts("dpggb"), seconds=2.0,
                               do_passband=False, do_speed=False)
    s = quality.measure_engine("scipy", None, seconds=2.0,
                               do_passband=False, do_speed=False)
    assert d.mt_dbc < s.mt_dbc - 100, (d.mt_dbc, s.mt_dbc)
    return " ".join(notes)


def test_null(demo: Path) -> str:
    au = codecs.decode(str(demo))
    try:
        y = np.asarray(au.data, dtype=np.float64)[: 44100 * 3]
    finally:
        au.close()
    # 参考与被测必须是同一组参数，才是"自己跟自己比"的数值链路自检
    strict = {"transband": 1.0, "atten": 250.0, "quality": "full", "phase": "linear"}
    same = quality.null_test(y, 44100, 48000, "r8b", strict, "r8b", strict)
    assert same["null_depth_db"] > 200, same["null_depth_db"]
    cross = quality.null_test(y, 44100, 48000, "soxng", None, "r8b", None)
    assert cross["null_depth_audible_db"] > 40, cross["null_depth_audible_db"]
    return (f"自比 {same['null_depth_db']:.0f} dB / soxng 可闻 "
            f"{cross['null_depth_audible_db']:.0f} dB")


def test_encode(demo: Path) -> str:
    au = codecs.decode(str(demo))
    try:
        y = np.asarray(au.data, dtype=np.float64)[: 48000 * 2]
    finally:
        au.close()
    out_dir = config.WORK / "selftest"
    out_dir.mkdir(parents=True, exist_ok=True)
    notes = []
    for fmt, bits in (("wav", 24), ("flac", 16), ("mp3", 16)):
        spec = codecs.FORMATS[fmt]
        path = out_dir / f"enc.{spec.ext}"
        opt = codecs.EncodeOptions(fmt=fmt, bits=bits, dither=True, noise_shape=True)
        codecs.encode(y, 48000, path, opt)
        assert path.exists() and path.stat().st_size > 1000, f"{fmt} 输出为空"
        info = probe.probe(str(path))
        assert info.ok, (fmt, info.error)
        assert abs(info.duration - 2.0) < 0.15, (fmt, info.duration)
        notes.append(f"{fmt}={path.stat().st_size // 1024}KB")
    return " ".join(notes)


def test_pipeline(demo: Path) -> str:
    out = config.WORK / "selftest" / "pipe.flac"
    out.parent.mkdir(parents=True, exist_ok=True)
    req = pipeline.ConvertRequest(
        input_path=str(demo), output_path=str(out), fmt="flac", bits=24,
        dst_rate=48000, engine="r8b", dither=True, noise_shape=True,
        analyze=True, null_test=True,
    )
    res = pipeline.convert(req)
    assert res.ok, res.error
    assert res.dst_rate == 48000
    assert res.frames_out > 0
    assert res.input_verdicts and res.output_verdicts and res.src_verdicts
    assert out.exists()
    return (f"{res.frames_in}→{res.frames_out} 帧, {res.elapsed:.2f}s, "
            f"{res.speed_x:.0f}× 实时")


def test_plot(demo: Path) -> str:
    au = codecs.decode(str(demo))
    try:
        y = np.asarray(au.data, dtype=np.float64)[: 44100 * 2]
    finally:
        au.close()
    rep = metrics.analyze(y, 44100)
    sg = metrics.spectrogram(y, 44100)
    ms = [quality.measure_engine("r8b", None, seconds=2.0),
          quality.measure_engine("soxng", None, seconds=2.0)]
    null = quality.null_test(y, 44100, 48000, "soxng", None, "r8b", None)
    opts = [
        plot.spectrum_option([rep.spectrum], ["测试"]),
        plot.spectrogram_option(sg, duration=2.0),
        plot.waveform_option(y, 44100),
        plot.fidelity_option(ms),
        plot.imd_option(ms),
        plot.speed_fidelity_option(ms),
        plot.engine_compare_option(ms, "spur_dbc"),
        plot.band_option(null),
    ]
    for o in opts:
        assert isinstance(o, dict) and o, o
        json.dumps(o)  # 必须可 JSON 序列化，否则前端渲染会炸
    return f"{len(opts)} 个图表 option 可序列化"


def test_presets() -> str:
    for p in presets.PRESETS:
        assert p.engine in engines.ENGINES, (p.key, p.engine)
        assert p.fmt in codecs.FORMATS, (p.key, p.fmt)
        spec = engines.ENGINES[p.engine]
        valid = {x.key for x in spec.params}
        bad = set(p.engine_opts) - valid
        assert not bad, f"预设 {p.key} 含未知参数 {bad}"
    return f"{len(presets.PRESETS)} 个预设 / {len(presets.GLOSSARY)} 个词条"


# --------------------------------------------------------------------------
def main() -> int:
    section("0. 环境")
    check("外部二进制发现", test_env)

    section("1. 解码与元数据")
    demo = config.WORK / "demo_44k.wav"
    check("演示素材存在且可探测", test_demo)
    check("解码为 float64", lambda: test_decode(demo))

    section("2. 八台引擎")
    check("全部引擎输出合法（整数倍引擎走 ×2）", lambda: test_engines(demo))

    section("3. 指标")
    check("正弦的峰值/RMS/LUFS/带宽", test_metrics)

    section("4. 质量测量")
    check("合成音杂散测量", test_measure)
    check("互调失真（双音 + 多音）", test_imd)
    check("零差测试（自比 + 跨引擎）", lambda: test_null(demo))

    section("5. 编码")
    check("wav/flac/mp3 编码", lambda: test_encode(demo))

    section("6. 流水线")
    check("端到端转换 + 三重结论", lambda: test_pipeline(demo))

    section("7. 绘图数据")
    check("ECharts option 可序列化", lambda: test_plot(demo))

    section("8. 预设与百科")
    check("预设引用的引擎/格式/参数都存在", test_presets)

    ok = sum(1 for _, good, _ in RESULTS if good)
    total = len(RESULTS)
    print("\n" + "=" * 68)
    print(f"汇总：{ok}/{total} 通过")
    if ok != total:
        for name, good, detail in RESULTS:
            if not good:
                print(f"  未通过：{name} —— {detail}")
    print("=" * 68)
    return 0 if ok == total else 1


if __name__ == "__main__":
    sys.exit(main())
