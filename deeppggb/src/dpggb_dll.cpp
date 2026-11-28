// dpggb_dll.cpp - C API so Python can call the engine in process.
//
// Going through the exe costs a full copy of the audio on both sides: a 180 s
// stereo job is 127 MB in and 277 MB out, and the pipe transfer alone measured
// 0.84 s - more than the resampling itself. In process there is no transfer at
// all.
#include "dpggb.h"

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <new>
#include <string>
#include <thread>
#include <vector>

#ifdef _WIN32
#define DP_EXPORT extern "C" __declspec(dllexport)
#else
#define DP_EXPORT extern "C" __attribute__((visibility("default")))
#endif

namespace {

// Look a key up as a whole field, not as a substring. Plain find() matches
// "taper=" inside "btaper=20", so the taper shape was silently read as "20"
// and every call fell back to the default -- the option appeared to work and
// did nothing. A field starts at offset 0 or right after a comma.
size_t opt_pos(const std::string& o, const char* key) {
    const std::string k = std::string(key) + "=";
    size_t p = o.find(k);
    while (p != std::string::npos) {
        if (p == 0 || o[p - 1] == ',') return p;
        p = o.find(k, p + 1);
    }
    return std::string::npos;
}

double opt_num(const std::string& o, const char* key, double dflt) {
    size_t p = opt_pos(o, key);
    if (p == std::string::npos) return dflt;
    p += std::strlen(key) + 1;
    const size_t e = o.find(',', p);
    return atof(o.substr(p, e == std::string::npos ? std::string::npos : e - p).c_str());
}

std::string opt_str(const std::string& o, const char* key, const char* dflt) {
    size_t p = opt_pos(o, key);
    if (p == std::string::npos) return dflt;
    p += std::strlen(key) + 1;
    const size_t e = o.find(',', p);
    return o.substr(p, e == std::string::npos ? std::string::npos : e - p);
}

dpggb::Cfg make_cfg(const std::string& o, double in_rate, double out_rate, int ch) {
    dpggb::Cfg cfg;
    cfg.in_rate = in_rate;
    cfg.out_rate = out_rate;
    cfg.channels = ch;
    cfg.block_sec = opt_num(o, "block", 16.0);
    cfg.mem_mb = opt_num(o, "mem", 1024.0);
    cfg.taper_ms = opt_num(o, "fade", 20.0);
    cfg.context_ms = opt_num(o, "context", 800.0);
    cfg.mp_taps_ms = opt_num(o, "mptaps", 50.0);
    cfg.rolloff_hz = opt_num(o, "rolloff", 200.0);
    cfg.roll_order = (int) opt_num(o, "rollorder", 2.0);
    cfg.block_taper_ms = opt_num(o, "btaper", 20.0);
    cfg.threads = (int) opt_num(o, "threads", 0.0);
    cfg.workers = (int) opt_num(o, "workers", 0.0);
    cfg.edge_taper_ms = opt_num(o, "edgefade", 0.0);
    cfg.taper_shape = dpggb::taper_from_name(opt_str(o, "taper", "smooth12"));
    cfg.precision = opt_str(o, "prec", "double") == "long" ? 1 : 0;
    cfg.phase = opt_str(o, "phase", "linear") == "min" ? dpggb::PHASE_MIN
                                                       : dpggb::PHASE_LINEAR;
    return cfg;
}

}  // namespace

// Resample an interleaved float64 buffer. On success returns 0 and hands back a
// malloc'd buffer the caller must release with dpggb_free.
DP_EXPORT int dpggb_resample(const double* in, long long frames, int ch,
                             double in_rate, double out_rate, const char* opts,
                             double** out, long long* out_frames) {
    if (!in || !out || !out_frames || frames <= 0 || ch < 1) return 1;
    const std::string o = opts ? opts : "";

    dpggb::Cfg cfg = make_cfg(o, in_rate, out_rate, ch);
    const dpggb::Ratio r = dpggb::reduce_ratio(in_rate, out_rate);
    const long long n_out =
        (long long) llround((double) frames * (double) r.L / (double) r.M);
    if (n_out <= 0) return 2;

    double* dst = (double*) std::malloc((size_t) n_out * (size_t) ch * sizeof(double));
    if (!dst) return 3;
    std::memset(dst, 0, (size_t) n_out * (size_t) ch * sizeof(double));

    // Same split as the CLI: the worker budget is divided between channels, not
    // multiplied, so 4 cores with 2 channels gives 2 block workers per channel.
    unsigned hw = (unsigned) (cfg.workers > 0 ? cfg.workers
                                              : std::thread::hardware_concurrency());
    if (hw == 0) hw = 1;
    const int ch_par = std::min<int>(ch, (int) hw);
    const int per_ch = std::max<int>(1, (int) hw / ch_par);

    auto do_channel = [&](int c) {
        dpggb::Cfg cc = cfg;
        cc.workers = per_ch;
        std::vector<double> col((size_t) frames);
        for (long long i = 0; i < frames; ++i)
            col[(size_t) i] = in[(size_t) i * (size_t) ch + (size_t) c];
        const std::vector<double> y = dpggb::resample_channel(col.data(), (size_t) frames, cc, r);
        const size_t m = std::min<size_t>(y.size(), (size_t) n_out);
        for (size_t i = 0; i < m; ++i)
            dst[i * (size_t) ch + (size_t) c] = y[i];
    };

    if (ch_par <= 1) {
        for (int c = 0; c < ch; ++c) do_channel(c);
    } else {
        std::vector<std::thread> pool;
        pool.reserve((size_t) ch_par);
        std::atomic<int> next(0);
        for (int w = 0; w < ch_par; ++w) {
            pool.emplace_back([&]() {
                for (;;) {
                    const int c = next.fetch_add(1);
                    if (c >= ch) break;
                    do_channel(c);
                }
            });
        }
        for (auto& t : pool) t.join();
    }

    *out = dst;
    *out_frames = n_out;
    return 0;
}

DP_EXPORT void dpggb_free(double* p) { std::free(p); }

// ---------------------------------------------------------------------------
// Streaming C API.
//
// The Python StreamResampler proved the window geometry, but it calls back into
// the whole-file entry point once per window. When that entry point is the exe,
// every window pays a process spawn plus a temp-file round trip; when it is the
// DLL it still pays a ctypes call and a fresh output allocation. This API keeps
// the FIFO and the cursor in C++ so a live source can push arbitrary chunks and
// only the core of each window crosses the ABI.
//
// Geometry (same as deeppggb_stream.py):
//   window = [left context | core | right context]
//   emit   = window output [ctx_out, ctx_out + core_out)
// The cursor advances by core_in; the left context of the next window is the
// right context of the previous one, so no cross-fade is needed.
// ---------------------------------------------------------------------------
namespace {

long long round_even(double v) {
    // Python's round() is half-to-even. The old code used llround (half away
    // from zero), which can differ by one frame on ratios where the product
    // lands exactly on .5.
    return (long long) std::nearbyint(v);
}

struct Stream {
    dpggb::Cfg cfg;
    dpggb::Ratio ratio;
    int ch = 1;
    double core_sec = 1.0;
    long long core_in = 1;
    long long core_out = 1;
    long long ctx_in = 1;
    long long ctx_out = 1;
    std::vector<double> fifo;  // interleaved, starts at absolute sample 0
    long long cursor = 0;
    bool finished = false;
};

// Build one window and append its core to acc. Returns false only on a kernel
// failure; an empty window is not an error.
bool process_window(Stream& s, bool final, std::vector<double>& acc) {
    const long long total_in = (long long) (s.fifo.size() / (size_t) s.ch);
    const long long avail = total_in - s.cursor;
    if (avail <= 0) return true;

    const long long core_n = final ? avail : s.core_in;
    const long long right_n = final ? 0 : s.ctx_in;
    const long long left_n = s.ctx_in;
    const long long W = left_n + core_n + right_n;
    if (W <= 0) return true;

    std::vector<double> win((size_t) W * (size_t) s.ch, 0.0);
    const long long start = s.cursor - left_n;
    for (long long i = 0; i < W; ++i) {
        const long long idx = start + i;
        if (idx < 0 || idx >= total_in) continue;  // zero-padded context
        for (int c = 0; c < s.ch; ++c)
            win[(size_t) i * (size_t) s.ch + (size_t) c] =
                s.fifo[(size_t) idx * (size_t) s.ch + (size_t) c];
    }

    const long long want = round_even((double) W * s.cfg.out_rate / s.cfg.in_rate);
    std::vector<std::vector<double>> outs((size_t) s.ch);
    std::vector<double> col((size_t) W);
    for (int c = 0; c < s.ch; ++c) {
        for (long long i = 0; i < W; ++i)
            col[(size_t) i] = win[(size_t) i * (size_t) s.ch + (size_t) c];
        dpggb::Cfg cc = s.cfg;
        cc.block_sec = 0.0;  // one transform per window, like the Python patch
        try {
            outs[(size_t) c] = dpggb::resample_channel(col.data(), (size_t) W, cc, s.ratio);
        } catch (...) {
            return false;
        }
        std::vector<double>& y = outs[(size_t) c];
        if ((long long) y.size() < want) y.resize((size_t) want, 0.0);
        else if ((long long) y.size() > want) y.resize((size_t) want);
    }

    const long long nout = (long long) outs[0].size();
    const long long lo = std::min<long long>(s.ctx_out, nout);
    const long long take = final ? (nout - lo)
                                 : std::min<long long>(s.core_out, nout - lo);
    if (take > 0) {
        acc.reserve(acc.size() + (size_t) take * (size_t) s.ch);
        for (long long i = 0; i < take; ++i)
            for (int c = 0; c < s.ch; ++c)
                acc.push_back(outs[(size_t) c][(size_t) (lo + i)]);
    }
    s.cursor += core_n;
    return true;
}

bool drain(Stream& s, bool final, std::vector<double>& acc) {
    for (;;) {
        if (final) {
            const long long avail =
                (long long) (s.fifo.size() / (size_t) s.ch) - s.cursor;
            if (avail <= 0) break;
            if (!process_window(s, true, acc)) return false;
            break;
        }
        const long long avail =
            (long long) (s.fifo.size() / (size_t) s.ch) - s.cursor;
        if (avail < s.core_in + s.ctx_in) break;
        if (!process_window(s, false, acc)) return false;
    }

    // Keep only the left context that the next window may still need. This
    // bounds memory on an endless stream and keeps the FIFO contiguous.
    const long long keep_from = std::max<long long>(0, s.cursor - s.ctx_in);
    if (keep_from > 0) {
        const size_t n = (size_t) keep_from * (size_t) s.ch;
        if (n <= s.fifo.size()) {
            s.fifo.erase(s.fifo.begin(), s.fifo.begin() + (std::ptrdiff_t) n);
            s.cursor -= keep_from;
        }
    }
    return true;
}

int emit(Stream& s, const std::vector<double>& acc, double** out, long long* out_frames) {
    *out = nullptr;
    *out_frames = 0;
    if (acc.empty()) return 0;
    double* p = (double*) std::malloc(acc.size() * sizeof(double));
    if (!p) return 3;
    std::memcpy(p, acc.data(), acc.size() * sizeof(double));
    *out = p;
    *out_frames = (long long) (acc.size() / (size_t) s.ch);
    return 0;
}

}  // namespace

// Create a streaming handle. opts accepts the same keys as dpggb_resample plus
// "core=<seconds>" (default 1.0). The context is taken from "context" (ms).
DP_EXPORT void* dpggb_stream_create(double in_rate, double out_rate, int ch,
                                    const char* opts) {
    if (ch < 1 || !(in_rate > 0.0) || !(out_rate > 0.0) || in_rate == out_rate)
        return nullptr;
    const std::string o = opts ? opts : "";
    try {
        Stream* s = new (std::nothrow) Stream();
        if (!s) return nullptr;
        s->cfg = make_cfg(o, in_rate, out_rate, ch);
        s->cfg.block_sec = 0.0;
        // One block worker keeps the thread-local FFT plan cache alive across
        // windows. Spawning a pool per window throws that cache away and, before
        // the PlanCache destructor existed, leaked every worker's scratch set.
        // A caller that wants block parallelism can still pass workers=N.
        if (opt_pos(o, "workers") == std::string::npos) s->cfg.workers = 1;
        s->ratio = dpggb::reduce_ratio(in_rate, out_rate);
        s->ch = ch;
        s->core_sec = opt_num(o, "core", 1.0);
        if (!(s->core_sec > 0.0)) s->core_sec = 1.0;
        s->core_out = std::max<long long>(1, round_even(out_rate * s->core_sec));
        s->core_in = std::max<long long>(
            1, round_even((double) s->core_out * in_rate / out_rate));
        s->ctx_in = std::max<long long>(
            1, round_even(in_rate * s->cfg.context_ms / 1000.0));
        s->ctx_out = std::max<long long>(
            1, round_even((double) s->ctx_in * out_rate / in_rate));
        return s;
    } catch (...) {
        return nullptr;
    }
}

// Feed interleaved float64 frames at the input rate. On success *out is a
// malloc'd interleaved buffer (release with dpggb_free) and *out_frames is its
// frame count; either can be zero. Returns 0 on success, 1 bad arguments,
// 4 stream already flushed, 5 kernel failure.
DP_EXPORT int dpggb_stream_push(void* handle, const double* in, long long frames,
                                double** out, long long* out_frames) {
    if (!handle || !out || !out_frames) return 1;
    *out = nullptr;
    *out_frames = 0;
    Stream* s = (Stream*) handle;
    if (s->finished) return 4;
    if (frames < 0 || (frames > 0 && !in)) return 1;
    if (frames == 0) return 0;
    try {
        const size_t old = s->fifo.size();
        s->fifo.resize(old + (size_t) frames * (size_t) s->ch);
        std::memcpy(s->fifo.data() + old, in,
                    (size_t) frames * (size_t) s->ch * sizeof(double));
        std::vector<double> acc;
        if (!drain(*s, false, acc)) return 5;
        return emit(*s, acc, out, out_frames);
    } catch (...) {
        return 5;
    }
}

// Signal end-of-stream and return the final partial window.
DP_EXPORT int dpggb_stream_flush(void* handle, double** out, long long* out_frames) {
    if (!handle || !out || !out_frames) return 1;
    *out = nullptr;
    *out_frames = 0;
    Stream* s = (Stream*) handle;
    if (s->finished) return 0;
    s->finished = true;
    try {
        std::vector<double> acc;
        if (!drain(*s, true, acc)) return 5;
        return emit(*s, acc, out, out_frames);
    } catch (...) {
        return 5;
    }
}

// End-to-end latency bound: core + right context, in seconds.
DP_EXPORT double dpggb_stream_latency(void* handle) {
    if (!handle) return 0.0;
    Stream* s = (Stream*) handle;
    return s->core_sec + (double) s->ctx_in / s->cfg.in_rate;
}

// Reset the FIFO and the cursor; configuration is kept.
DP_EXPORT void dpggb_stream_reset(void* handle) {
    if (!handle) return;
    Stream* s = (Stream*) handle;
    s->fifo.clear();
    s->cursor = 0;
    s->finished = false;
}

DP_EXPORT void dpggb_stream_destroy(void* handle) {
    delete (Stream*) handle;
}
