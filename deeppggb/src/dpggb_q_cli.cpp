// dpggb_q_cli.cpp - file front end for the IEEE binary128 path.
//
//   dpggb128 in_rate out_rate in.f128 out.f128 [options]
//
// Input and output default to raw __float128 (16 bytes per sample, native
// little-endian, interleaved). --in f64 / --out f64 bridge to the ordinary
// float64 format; that is convenient, but widening a float64 input cannot
// recover the samples' own quantisation and narrowing the output puts the
// float64 floor straight back, so a precision comparison needs f128 on both
// sides.
#include "dpggb.h"

#include <quadmath.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

static bool read_raw(const char* path, bool as_f64, std::vector<__float128>& v) {
    FILE* f = std::fopen(path, "rb");
    if (!f) return false;
    std::fseek(f, 0, SEEK_END);
    const long long bytes = std::ftell(f);
    std::fseek(f, 0, SEEK_SET);
    const size_t width = as_f64 ? 8 : 16;
    const size_t n = (size_t) (bytes / (long long) width);
    v.resize(n);
    if (as_f64) {
        std::vector<double> d(n);
        if (std::fread(d.data(), 8, n, f) != n) { std::fclose(f); return false; }
        for (size_t i = 0; i < n; ++i) v[i] = (__float128) d[i];
    } else {
        if (std::fread(v.data(), 16, n, f) != n) { std::fclose(f); return false; }
    }
    std::fclose(f);
    return true;
}

static bool write_raw(const char* path, bool as_f64, const std::vector<__float128>& v) {
    FILE* f = std::fopen(path, "wb");
    if (!f) return false;
    bool ok;
    if (as_f64) {
        std::vector<double> d(v.size());
        for (size_t i = 0; i < v.size(); ++i) d[i] = (double) v[i];
        ok = std::fwrite(d.data(), 8, d.size(), f) == d.size();
    } else {
        ok = std::fwrite(v.data(), 16, v.size(), f) == v.size();
    }
    std::fclose(f);
    return ok;
}

int main(int argc, char** argv) {
    if (argc < 5) {
        std::fprintf(stderr,
            "usage: %s in_rate out_rate in out [options]\n"
            "  --ch N          channels (default 1)\n"
            "  --block SEC     block length in seconds (default 16, 0 = whole file)\n"
            "  --context MS    block context (default 800)\n"
            "  --btaper MS     block-edge taper (default 20)\n"
            "  --taper SHAPE   smooth4 | smooth5 | smooth6 | smooth2 | cos | blackman | none\n"
            "  --rolloff HZ    transition band (default 200)\n"
            "  --workers N     block workers (0 = auto)\n"
            "  --in FMT        f128 | f64 (default f128)\n"
            "  --out FMT       f128 | f64 (default f128)\n"
            "  --bench N       repeat the conversion N times, report the best\n", argv[0]);
        return 1;
    }
    dpggb::Cfg cfg;
    cfg.in_rate = std::atof(argv[1]);
    cfg.out_rate = std::atof(argv[2]);
    bool in_f64 = false, out_f64 = false;
    int bench = 1;
    for (int i = 5; i + 1 < argc; i += 2) {
        const std::string k = argv[i];
        const char* v = argv[i + 1];
        if (k == "--ch") cfg.channels = std::atoi(v);
        else if (k == "--block") cfg.block_sec = std::atof(v);
        else if (k == "--context") cfg.context_ms = std::atof(v);
        else if (k == "--btaper") cfg.block_taper_ms = std::atof(v);
        else if (k == "--rolloff") cfg.rolloff_hz = std::atof(v);
        else if (k == "--workers") cfg.workers = std::atoi(v);
        else if (k == "--in") in_f64 = std::string(v) == "f64";
        else if (k == "--out") out_f64 = std::string(v) == "f64";
        else if (k == "--bench") bench = std::max(1, std::atoi(v));
        else if (k == "--taper") {
            const std::string s = v;
            cfg.taper_shape = s == "none" ? dpggb::TAPER_NONE
                            : s == "cos" ? dpggb::TAPER_COS
                            : s == "blackman" ? dpggb::TAPER_BLACKMAN
                            : s == "smooth2" ? dpggb::TAPER_SMOOTH
                            : s == "smooth4" ? dpggb::TAPER_SMOOTH4
                            : s == "smooth6" ? dpggb::TAPER_SMOOTH6
                            : dpggb::TAPER_SMOOTH5;
        } else { std::fprintf(stderr, "unknown option %s\n", k.c_str()); return 1; }
    }
    if (cfg.channels < 1) cfg.channels = 1;
    cfg.precision = 2;

    std::vector<__float128> all;
    if (!read_raw(argv[3], in_f64, all)) {
        std::fprintf(stderr, "cannot read %s\n", argv[3]);
        return 1;
    }
    const size_t frames = all.size() / (size_t) cfg.channels;
    const dpggb::Ratio r = dpggb::reduce_ratio(cfg.in_rate, cfg.out_rate);
    const size_t out_frames = (size_t) std::llround((double) frames * (double) r.L / (double) r.M);
    std::vector<__float128> out(out_frames * (size_t) cfg.channels, 0);

    unsigned hw = (unsigned) (cfg.workers > 0 ? cfg.workers : std::thread::hardware_concurrency());
    if (hw == 0) hw = 1;
    const int nch = cfg.channels;
    const int ch_par = std::min<int>(nch, (int) hw);
    const int per_ch = std::max<int>(1, (int) hw / ch_par);
    (void) ch_par;

    // Channels run one after another; the core already parallelises blocks
    // inside a channel, and that is the axis that scales here.
    double best = 1e30;
    for (int rep = 0; rep < bench; ++rep) {
        const auto t0 = std::chrono::steady_clock::now();
        for (int c = 0; c < nch; ++c) {
            dpggb::Cfg cc = cfg;
            cc.workers = per_ch;
            std::vector<__float128> ch((size_t) frames);
            for (size_t i = 0; i < frames; ++i) ch[i] = all[i * (size_t) cfg.channels + (size_t) c];
            std::vector<__float128> y = dpggb::resample_channel_q(ch.data(), frames, cc, r);
            for (size_t i = 0; i < y.size() && i < out_frames; ++i)
                out[i * (size_t) cfg.channels + (size_t) c] = y[i];
        }
        const double s = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
        best = std::min(best, s);
    }

    if (!write_raw(argv[4], out_f64, out)) {
        std::fprintf(stderr, "cannot write %s\n", argv[4]);
        return 1;
    }
    const double audio_s = (double) frames / cfg.in_rate;
    std::fprintf(stderr, "[dpggb128] %zu -> %zu frames, %.3f s, %.2fx realtime, %d ch, workers %d\n",
                 frames, out_frames, best, audio_s / best, nch, per_ch);
    return 0;
}
