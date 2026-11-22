// dpggb_cli.cpp - command line front end.
//
// Modes:
//   raw     float64 in / float64 out (the form the Python driver uses)
//   dsd     float64 in at the DSD rate -> packed 1-bit bytes
//   pcm     float64 in -> integer PCM at --bits
#include "dpggb.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

// Windows opens stdin/stdout in text mode, which turns every 0x0A byte into
// 0x0D 0x0A and silently corrupts a binary float64 stream. Anything that can
// write to a pipe has to switch both to binary first.
static void use_binary_stdio() {
#ifdef _WIN32
    _setmode(_fileno(stdin), _O_BINARY);
    _setmode(_fileno(stdout), _O_BINARY);
#endif
}

// "-" means stdin/stdout. Piping avoids writing a multi-hundred-megabyte
// float64 scratch file per conversion, which on a 180 s stereo job cost more
// wall time than the resampling itself.
static bool read_raw(const char* path, std::vector<double>& v) {
    const bool pipe = (std::strcmp(path, "-") == 0);
    if (pipe) use_binary_stdio();
    FILE* f = pipe ? stdin : fopen(path, "rb");
    if (!f) return false;
    if (pipe) {
        // A pipe has no size, so grow as data arrives.
        v.clear();
        const size_t chunk = 1 << 20;
        size_t have = 0;
        for (;;) {
            v.resize(have + chunk / 8);
            const size_t got = fread(v.data() + have, 8, chunk / 8, f);
            have += got;
            if (got < chunk / 8) break;
        }
        v.resize(have);
        return true;
    }
    fseek(f, 0, SEEK_END);
    const long long bytes = ftell(f);
    fseek(f, 0, SEEK_SET);
    v.resize((size_t) (bytes / 8));
    const size_t got = fread(v.data(), 8, v.size(), f);
    fclose(f);
    return got == v.size();
}

static bool write_raw(const char* path, const void* data, size_t bytes) {
    const bool pipe = (std::strcmp(path, "-") == 0);
    if (pipe) use_binary_stdio();
    FILE* f = pipe ? stdout : fopen(path, "wb");
    if (!f) return false;
    const size_t put = fwrite(data, 1, bytes, f);
    fflush(f);
    if (!pipe) fclose(f);
    return put == bytes;
}

static void usage(const char* a0) {
    fprintf(stderr, "usage: %s in_rate out_rate in.f64 out [options]\n", a0);
    fprintf(stderr, "  --ch N          channels (default 1)\n");
    fprintf(stderr, "  --block SEC     block length in seconds, default 16 (0 = whole file)\n");
    fprintf(stderr, "  --mem MB        memory budget in MB (default 1024)\n");
    fprintf(stderr, "  --fade MS       head/tail fade in ms (default 20)\n");
    fprintf(stderr, "  --context MS    block context in ms (default 800)\n");
    fprintf(stderr, "  --mptaps MS     min-phase FIR length = 4 x MS (default 50)\n");
    fprintf(stderr, "  --rolloff HZ    transition band below Nyquist (default 200, 0 = brick wall)\n");
    fprintf(stderr, "  --rollorder N   rolloff shape exponent (default 2 = squared cosine)\n");
    fprintf(stderr, "  --btaper MS     block-edge taper length (default 20)\n");
    fprintf(stderr, "  --taper SHAPE   smooth5 | smooth4 | smooth6 | smooth2 | cos | blackman | none\n");
    fprintf(stderr, "  --prec P        double | long\n");
    fprintf(stderr, "  --phase PH      linear | min\n");
    fprintf(stderr, "  --threads N     FFT threads inside one transform (0 = auto)\n");
    fprintf(stderr, "  --workers N     blocks processed concurrently (0 = auto)\n");
    fprintf(stderr, "  --mode M        raw | pcm | dsd\n");
    fprintf(stderr, "  --bits N        PCM depth for --mode pcm (16/24/32)\n");
    fprintf(stderr, "  --ns N          noise shaping order for --mode pcm (0/4)\n");
    fprintf(stderr, "  --dsd N         DSD multiple for --mode dsd (64/128/256)\n");
    fprintf(stderr, "  --dsd-order N   sigma-delta order (default 5)\n");
}
int main(int argc, char** argv) {
    if (argc < 5) { usage(argv[0]); return 1; }

    dpggb::Cfg cfg;
    cfg.in_rate = atof(argv[1]);
    cfg.out_rate = atof(argv[2]);
    std::string mode = "raw";
    int bits = 24, ns = 0, dsd_mult = 64, dsd_order = 5;

    for (int i = 5; i + 1 < argc; i += 2) {
        const std::string k = argv[i];
        const char* v = argv[i + 1];
        if (k == "--ch") cfg.channels = atoi(v);
        else if (k == "--block") cfg.block_sec = atof(v);
        else if (k == "--mem") cfg.mem_mb = atof(v);
        else if (k == "--fade") cfg.taper_ms = atof(v);
        else if (k == "--context") cfg.context_ms = atof(v);
        else if (k == "--mptaps") cfg.mp_taps_ms = atof(v);
        else if (k == "--rolloff") cfg.rolloff_hz = atof(v);
        else if (k == "--rollorder") cfg.roll_order = std::max(1, atoi(v));
        else if (k == "--btaper") cfg.block_taper_ms = atof(v);
        else if (k == "--taper") {
            const std::string s = v;
            cfg.taper_shape = s == "none" ? dpggb::TAPER_NONE
                            : s == "cos" ? dpggb::TAPER_COS
                            : s == "blackman" ? dpggb::TAPER_BLACKMAN
                            : s == "smooth2" ? dpggb::TAPER_SMOOTH
                            : s == "smooth4" ? dpggb::TAPER_SMOOTH4
                            : s == "smooth6" ? dpggb::TAPER_SMOOTH6
                            : dpggb::TAPER_SMOOTH5;   // "smooth" and "smooth5"
        }
        else if (k == "--prec") cfg.precision = std::string(v) == "long" ? 1 : 0;
        else if (k == "--phase") cfg.phase = std::string(v) == "min" ? dpggb::PHASE_MIN : dpggb::PHASE_LINEAR;
        else if (k == "--threads") cfg.threads = atoi(v);
        else if (k == "--workers") cfg.workers = atoi(v);
        else if (k == "--mode") mode = v;
        else if (k == "--bits") bits = atoi(v);
        else if (k == "--ns") ns = atoi(v);
        else if (k == "--dsd") dsd_mult = atoi(v);
        else if (k == "--dsd-order") dsd_order = atoi(v);
        else { fprintf(stderr, "unknown option %s\n", k.c_str()); return 1; }
    }
    if (cfg.channels < 1) cfg.channels = 1;

    const auto t_read = std::chrono::steady_clock::now();
    std::vector<double> all;
    if (!read_raw(argv[3], all)) { fprintf(stderr, "cannot read %s\n", argv[3]); return 1; }
    const size_t frames = all.size() / (size_t) cfg.channels;

    auto t0 = std::chrono::steady_clock::now();

    // DSD is always at a fixed absolute rate (2.8224 MHz for DSD64), not at a
    // multiple of the source rate, so the conversion target changes here.
    if (mode == "dsd") cfg.out_rate = 2822400.0 * (double) dsd_mult / 64.0;

    const dpggb::Ratio r = dpggb::reduce_ratio(cfg.in_rate, cfg.out_rate);
    const size_t out_frames = (size_t) llround((double) frames * (double) r.L / (double) r.M);

    std::vector<double> out((size_t) out_frames * (size_t) cfg.channels, 0.0);

    // Channels are independent, so they run concurrently too. The worker budget
    // is split between the two axes rather than multiplied: with 4 cores and 2
    // channels each channel gets 2 block workers, which keeps the total at 4
    // instead of oversubscribing to 8.
    unsigned hw = (unsigned) (cfg.workers > 0 ? cfg.workers : std::thread::hardware_concurrency());
    if (hw == 0) hw = 1;
    const int nch = std::max(1, cfg.channels);
    const int ch_par = std::min<int>(nch, (int) hw);
    const int per_ch = std::max<int>(1, (int) hw / ch_par);

    auto do_channel = [&](int c) {
        dpggb::Cfg cc = cfg;
        cc.workers = per_ch;
        std::vector<double> ch((size_t) frames);
        for (size_t i = 0; i < frames; ++i) ch[i] = all[i * (size_t) cfg.channels + (size_t) c];
        std::vector<double> y = dpggb::resample_channel(ch.data(), frames, cc, r);
        for (size_t i = 0; i < y.size() && i < out_frames; ++i)
            out[i * (size_t) cfg.channels + (size_t) c] = y[i];
    };

    if (ch_par <= 1) {
        for (int c = 0; c < nch; ++c) do_channel(c);
    } else {
        std::vector<std::thread> pool;
        pool.reserve((size_t) ch_par);
        std::atomic<int> next(0);
        for (int w = 0; w < ch_par; ++w) {
            pool.emplace_back([&]() {
                for (;;) {
                    const int c = next.fetch_add(1);
                    if (c >= nch) break;
                    do_channel(c);
                }
            });
        }
        for (auto& t : pool) t.join();
    }

    const auto t_calc = std::chrono::steady_clock::now();
    const double secs = std::chrono::duration<double>(t_calc - t0).count();
    const double audio = (double) frames / cfg.in_rate;

    bool ok = true;
    if (mode == "dsd") {
        const std::vector<uint8_t> packed =
            dpggb::to_dsd(out, cfg.channels, dsd_mult, cfg.out_rate, dsd_order);
        ok = write_raw(argv[4], packed.data(), packed.size());
    } else if (mode == "pcm") {
        const std::vector<int32_t> q = dpggb::quantise(out, cfg.channels, bits, ns, cfg.out_rate);
        const int bytes = bits / 8;
        std::vector<uint8_t> buf((size_t) q.size() * (size_t) bytes);
        for (size_t i = 0; i < q.size(); ++i) {
            const uint32_t v = (uint32_t) q[i];
            for (int b = 0; b < bytes; ++b)
                buf[i * (size_t) bytes + (size_t) b] = (uint8_t) ((v >> (8 * b)) & 0xFF);
        }
        ok = write_raw(argv[4], buf.data(), buf.size());
    } else {
        ok = write_raw(argv[4], out.data(), out.size() * sizeof(double));
    }

    const auto t_write = std::chrono::steady_clock::now();
    if (!ok) { fprintf(stderr, "cannot write %s\n", argv[4]); return 1; }
    const double d_read = std::chrono::duration<double>(t0 - t_read).count();
    const double d_write = std::chrono::duration<double>(t_write - t_calc).count();
    fprintf(stderr, "mode=%s in=%zu out=%zu frames  %.2f s audio in %.2f s (%.1fx)\n",
            mode.c_str(), frames, out_frames, audio, secs, audio / secs);
    fprintf(stderr, "  stage: read %.3f s, convert %.3f s, write %.3f s\n",
            d_read, secs, d_write);
    return 0;
}
