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

}  // namespace

// Resample an interleaved float64 buffer. On success returns 0 and hands back a
// malloc'd buffer the caller must release with dpggb_free.
DP_EXPORT int dpggb_resample(const double* in, long long frames, int ch,
                             double in_rate, double out_rate, const char* opts,
                             double** out, long long* out_frames) {
    if (!in || !out || !out_frames || frames <= 0 || ch < 1) return 1;
    const std::string o = opts ? opts : "";

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
    const std::string taper = opt_str(o, "taper", "smooth");
    cfg.taper_shape = taper == "none" ? dpggb::TAPER_NONE
                    : taper == "cos"  ? dpggb::TAPER_COS
                    : taper == "blackman" ? dpggb::TAPER_BLACKMAN
                    : taper == "smooth2" ? dpggb::TAPER_SMOOTH
                    : taper == "smooth4" ? dpggb::TAPER_SMOOTH4
                    : taper == "smooth6" ? dpggb::TAPER_SMOOTH6
                                          : dpggb::TAPER_SMOOTH5;
    cfg.precision = opt_str(o, "prec", "double") == "long" ? 1 : 0;
    cfg.phase = opt_str(o, "phase", "linear") == "min" ? dpggb::PHASE_MIN
                                                       : dpggb::PHASE_LINEAR;

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
