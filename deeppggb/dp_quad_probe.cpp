// dp_quad_probe.cpp - measurement harness for the binary128 path.
//
// The ruler is built first: every number below is produced by quad arithmetic
// (projection, residual, FFT), so the floor of the measurement sits near
// -650 dB and cannot mask the engine. Stimulus precision is matched to the
// engine under test: a float64 engine gets a float64 sine, the quad engine
// gets a quad sine. Anything else measures the input quantiser, not the
// resampler.
#include "src/dpggb.h"
#include "src/quad_fft.h"

#include <fftw3.h>
#include <quadmath.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <map>
#include <random>
#include <string>
#include <thread>
#include <vector>

using qf = __float128;
static const qf kPiQ =
    3.14159265358979323846264338327950288419716939937510582097494459Q;

static long long gcd_ll(long long a, long long b) { while (b) { auto t = a % b; a = b; b = t; } return a; }

// ---------------------------------------------------------------- stimulus
static std::vector<qf> gen_tone(double freq, int fs, long long n, double amp) {
    const long long f = (long long) std::llround(freq);
    std::vector<qf> x((size_t) n);
    const qf a = (qf) amp;
    const qf two_pi = 2 * kPiQ;
    for (long long i = 0; i < n; ++i) {
        const long long m = (f * i) % fs;          // exact integer phase
        x[(size_t) i] = a * sinq(two_pi * (qf) m / (qf) fs);
    }
    return x;
}

// 40-tone multitone, same construction as dp_exact_verify.py.
static std::vector<qf> gen_multitone(const std::vector<int>& freqs, int fs, long long n,
                                     double total_amp, unsigned seed) {
    std::vector<double> amp(freqs.size()), ph(freqs.size());
    std::mt19937_64 rng(seed);
    std::uniform_real_distribution<double> u(0.0, 1.0);
    double s = 0;
    for (size_t i = 0; i < freqs.size(); ++i) { amp[i] = 0.05 + 0.45 * u(rng); s += amp[i]; }
    for (size_t i = 0; i < freqs.size(); ++i) { amp[i] = amp[i] / s * total_amp; ph[i] = 2 * 3.141592653589793 * u(rng); }
    std::vector<qf> x((size_t) n, 0);
    for (size_t t = 0; t < freqs.size(); ++t) {
        const long long f = freqs[t];
        const qf a = (qf) amp[t], p = (qf) ph[t];
        for (long long i = 0; i < n; ++i) {
            const long long m = (f * i) % fs;
            x[(size_t) i] += a * sinq(2 * kPiQ * (qf) m / (qf) fs + p);
        }
    }
    return x;
}

// ---------------------------------------------------------------- analysis
struct Proj { qf d, a, b; };

static Proj project(const qf* x, long long n, long long stride0, int fs, long long f) {
    const long long period = fs / gcd_ll(f, fs);
    // Key the cache on (f, fs), NOT on the period: two different frequencies can
    // share a period (19000 and 38000 both give 441 samples at 88.2 kHz), and a
    // period-keyed table then projects one tone onto the other's basis, which
    // reads the full tone level instead of the floor.
    static std::map<std::pair<long long, int>, std::vector<qf>> ctab, stab;
    const std::pair<long long, int> key{f, fs};
    auto& cs = ctab[key];
    auto& sn = stab[key];
    if ((long long) cs.size() != period) {
        cs.resize((size_t) period);
        sn.resize((size_t) period);
        for (long long i = 0; i < period; ++i) {
            const qf th = 2 * kPiQ * (qf) ((f * i) % fs) / (qf) fs;
            cs[(size_t) i] = cosq(th);
            sn[(size_t) i] = sinq(th);
        }
    }
    qf sd = 0, sa = 0, sb = 0;
    for (long long i = 0; i < n; ++i) {
        const long long j = (stride0 + i) % period;
        const qf v = x[(size_t) i];
        sd += v;
        sa += v * cs[(size_t) j];
        sb += v * sn[(size_t) j];
    }
    const qf inv = 1 / (qf) n;
    return { sd * inv, 2 * sa * inv, 2 * sb * inv };
}

// Null against an analytic sine, with a two-step re-projection of the residual
// (the same refinement dp_sinad uses). Returns dB, positive = better.
static double qnull(const qf* y, long long n, long long i0, long long len, int fs, long long f,
                    double* out_amp = nullptr) {
    const qf* seg = y + i0;
    Proj p = project(seg, len, i0, fs, f);
    const long long period0 = fs / gcd_ll(f, fs);
    std::vector<qf> c0((size_t) period0), s0((size_t) period0);
    for (long long i = 0; i < period0; ++i) {
        const qf th = 2 * kPiQ * (qf) ((f * i) % fs) / (qf) fs;
        c0[(size_t) i] = cosq(th);
        s0[(size_t) i] = sinq(th);
    }
    std::vector<qf> r((size_t) len);
    for (long long i = 0; i < len; ++i) {
        const long long j = (i0 + i) % period0;
        r[(size_t) i] = seg[i] - (p.d + p.a * c0[(size_t) j] + p.b * s0[(size_t) j]);
    }
    // residual after subtracting the fitted model
    {
        const long long period = period0;
        const std::vector<qf>& c = c0;
        const std::vector<qf>& s = s0;
        for (int it = 0; it < 2; ++it) {
            Proj q{0, 0, 0};
            qf inv = 1 / (qf) len;
            for (long long i = 0; i < len; ++i) {
                const long long j = (i0 + i) % period;
                const qf v = r[(size_t) i];
                q.d += v;
                q.a += v * c[(size_t) j];
                q.b += v * s[(size_t) j];
            }
            q.d *= inv; q.a *= 2 * inv; q.b *= 2 * inv;
            p.d += q.d; p.a += q.a; p.b += q.b;
            for (long long i = 0; i < len; ++i) {
                const long long j = (i0 + i) % period;
                r[(size_t) i] -= q.d + q.a * c[(size_t) j] + q.b * s[(size_t) j];
            }
        }
    }
    qf pres = 0;
    for (long long i = 0; i < len; ++i) pres += r[(size_t) i] * r[(size_t) i];
    pres /= (qf) len;
    const qf psig = 0.5Q * (p.a * p.a + p.b * p.b);
    if (out_amp) *out_amp = (double) sqrtq(p.a * p.a + p.b * p.b);
    return (double) (10 * log10q(psig / pres));
}

// SINAD/SFDR/ENOB of one integer-cycle window.
struct Tone { double sinad, sinad_fs, sfdr, enob, amp, spur_hz; };

static dpq::Plan& analysis_plan(int n) {
    static std::map<int, dpq::Plan> cache;
    auto it = cache.find(n);
    if (it == cache.end()) it = cache.emplace(n, dpq::make_plan(n)).first;
    return it->second;
}

static Tone qsinad(const qf* y, long long len, int fs, long long f) {
    const double kk = (double) f * (double) len / (double) fs;
    const long long k = (long long) std::llround(kk);
    if (std::fabs(kk - (double) k) > 1e-6) { std::fprintf(stderr, "window not integer cycles\n"); std::exit(2); }
    const qf inv = 1 / (qf) len;
    std::vector<qf> c((size_t) len), s((size_t) len);
    for (long long i = 0; i < len; ++i) {
        const qf th = 2 * kPiQ * (qf) ((k * i) % len) / (qf) len;
        c[(size_t) i] = cosq(th);
        s[(size_t) i] = sinq(th);
    }
    Proj p{0, 0, 0};
    for (long long i = 0; i < len; ++i) {
        p.d += y[i]; p.a += y[i] * c[(size_t) i]; p.b += y[i] * s[(size_t) i];
    }
    p.d *= inv; p.a *= 2 * inv; p.b *= 2 * inv;
    std::vector<qf> r((size_t) len);
    for (long long i = 0; i < len; ++i) r[(size_t) i] = y[i] - (p.d + p.a * c[(size_t) i] + p.b * s[(size_t) i]);
    for (int it = 0; it < 2; ++it) {
        Proj q{0, 0, 0};
        for (long long i = 0; i < len; ++i) { q.d += r[(size_t) i]; q.a += r[(size_t) i] * c[(size_t) i]; q.b += r[(size_t) i] * s[(size_t) i]; }
        q.d *= inv; q.a *= 2 * inv; q.b *= 2 * inv;
        p.d += q.d; p.a += q.a; p.b += q.b;
        for (long long i = 0; i < len; ++i) r[(size_t) i] -= q.d + q.a * c[(size_t) i] + q.b * s[(size_t) i];
    }
    qf pres = 0;
    for (long long i = 0; i < len; ++i) pres += r[(size_t) i] * r[(size_t) i];
    pres *= inv;
    const qf psig = 0.5Q * (p.a * p.a + p.b * p.b);
    const double amp = (double) sqrtq(p.a * p.a + p.b * p.b);
    const double sinad = (double) (10 * log10q(psig / pres));
    const double sinad_fs = sinad + 20 * std::log10(1.0 / amp);

    std::vector<dpq::QC> spec((size_t) len);
    for (long long i = 0; i < len; ++i) spec[(size_t) i] = dpq::make_qc(r[(size_t) i], 0);
    dpq::fft_forward(analysis_plan((int) len), spec.data(), spec.data());
    double worst = 0; long long worst_bin = 0;
    for (long long j = 3; j <= len / 2; ++j) {
        if (std::llabs(j - k) <= 1) continue;
        const double m = 2.0 * (double) sqrtq(spec[(size_t) j][0] * spec[(size_t) j][0] +
                                              spec[(size_t) j][1] * spec[(size_t) j][1]) / (double) len;
        if (m > worst) { worst = m; worst_bin = j; }
    }
    Tone t;
    t.sinad = sinad; t.sinad_fs = sinad_fs; t.amp = amp;
    t.sfdr = 20 * std::log10(amp / std::max(worst, 1e-300));
    t.enob = (sinad_fs - 1.76) / 6.02;
    t.spur_hz = (double) worst_bin * fs / (double) len;
    return t;
}

// ---------------------------------------------------------------- engine
struct Run { double wall; double speed; };
static double g_btaper = 20.0;
static double g_context = 800.0;
static double g_fade = 20.0;   // file-end fade (Cfg::taper_ms); DPQ_FADE overrides
static int g_shape = dpggb::TAPER_SMOOTH12;  // matches Cfg's default
// Stimulus level. A relative error keeps its dBc at any level, an absolute one
// (rounding, a fixed offset) scales with it, so the level is its own axis.
static double g_amp = 0.5;

static Run run_engine(int prec, const std::vector<qf>& xq, const std::vector<double>& xd,
                      int fs_in, int fs_out, double block_sec, int workers) {
    dpggb::Cfg cfg;
    cfg.in_rate = fs_in; cfg.out_rate = fs_out; cfg.precision = prec;
    cfg.block_sec = block_sec; cfg.workers = workers;
    cfg.block_taper_ms = g_btaper; cfg.taper_shape = g_shape;
    cfg.context_ms = g_context; cfg.edge_taper_ms = g_fade;
    const dpggb::Ratio r = dpggb::reduce_ratio(cfg.in_rate, cfg.out_rate);
    const auto t0 = std::chrono::steady_clock::now();
    if (prec == 2) {
        auto y = dpggb::resample_channel_q(xq.data(), xq.size(), cfg, r);
    } else if (prec == 1) {
        std::vector<long double> xl(xd.begin(), xd.end());
        auto y = dpggb::resample_channel_ld(xl.data(), xl.size(), cfg, r);
    } else {
        std::vector<double> x(xd.begin(), xd.end());
        auto y = dpggb::resample_channel(x.data(), x.size(), cfg, r);
    }
    const double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    return {wall, (double) xd.size() / (double) fs_in / wall};
}

// keep the output alive for analysis
static std::vector<qf> run_and_keep(int prec, const std::vector<qf>& xq, const std::vector<double>& xd,
                                    int fs_in, int fs_out, double block_sec, int workers,
                                    double* wall) {
    dpggb::Cfg cfg;
    cfg.in_rate = fs_in; cfg.out_rate = fs_out; cfg.precision = prec;
    cfg.block_sec = block_sec; cfg.workers = workers;
    cfg.block_taper_ms = g_btaper; cfg.taper_shape = g_shape;
    cfg.context_ms = g_context; cfg.edge_taper_ms = g_fade;
    const dpggb::Ratio r = dpggb::reduce_ratio(cfg.in_rate, cfg.out_rate);
    const auto t0 = std::chrono::steady_clock::now();
    std::vector<qf> out;
    if (prec == 2) {
        out = dpggb::resample_channel_q(xq.data(), xq.size(), cfg, r);
    } else if (prec == 1) {
        std::vector<long double> xl(xd.begin(), xd.end());
        auto y = dpggb::resample_channel_ld(xl.data(), xl.size(), cfg, r);
        out.assign(y.begin(), y.end());
    } else {
        std::vector<double> x(xd.begin(), xd.end());
        auto y = dpggb::resample_channel(x.data(), x.size(), cfg, r);
        out.assign(y.begin(), y.end());
    }
    *wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    return out;
}

int main(int argc, char** argv) {
    if (argc < 2) { std::fprintf(stderr, "mode: null|sinad|speed|ruler\n"); return 1; }
    const std::string mode = argv[1];
    if (mode == "ruler") {
        const int fs = 88200; const long long n = 88200; const double f = 1000;
        auto ideal = gen_tone(f, fs, n, 0.5);
        // 1. quad ideal -> quad analysis
        {
            std::vector<qf> lb(ideal.begin(), ideal.end());
            printf("ruler quad->quad       null %.2f dB\n", qnull(lb.data(), n, 0, n, fs, (long long) f));
        }
        // 2. same tone rounded to double, then widened
        {
            std::vector<qf> d((size_t) n);
            for (long long i = 0; i < n; ++i) d[(size_t) i] = (qf) (double) ideal[(size_t) i];
            printf("ruler quad->double     null %.2f dB\n", qnull(d.data(), n, 0, n, fs, (long long) f));
        }
        // 3. rounded to x87 long double (64-bit mantissa)
        {
            std::vector<qf> d((size_t) n);
            for (long long i = 0; i < n; ++i) d[(size_t) i] = (qf) (long double) ideal[(size_t) i];
            printf("ruler quad->longdouble null %.2f dB\n", qnull(d.data(), n, 0, n, fs, (long long) f));
        }
        // 4. quad FFT round trip on the same tone
        {
            dpq::Plan pl = dpq::make_plan((int) n);
            std::vector<dpq::QC> h((size_t) (n / 2 + 1));
            std::vector<qf> back((size_t) n);
            dpq::fft_r2c(pl, ideal.data(), h.data());
            dpq::fft_c2r(pl, h.data(), back.data());
            for (long long i = 0; i < n; ++i) back[(size_t) i] /= (qf) 1; // unnormalised
            // compare against n*ideal, which is what the unnormalised c2r returns
            std::vector<qf> ref((size_t) n);
            for (long long i = 0; i < n; ++i) ref[(size_t) i] = ideal[(size_t) i] * (qf) n;
            printf("ruler fft r2c->c2r    null %.2f dB\n", qnull(back.data(), n, 0, n, fs, (long long) f));
            (void) ref;
        }
        return 0;
    }
    if (mode == "even") {
        const int prec = std::atoi(argv[2]);
        const double f = std::atof(argv[3]);
        const double secs = std::atof(argv[4]);
        const int fs_in = 44100, fs_out = 88200;
        const long long n = (long long) std::llround(secs * fs_in);
        auto xq = gen_tone(f, fs_in, n, 0.5);
        std::vector<double> xd((size_t) n);
        for (long long i = 0; i < n; ++i) xd[(size_t) i] = (double) xq[(size_t) i];
        double wall = 0;
        auto y = run_and_keep(prec, xq, xd, fs_in, fs_out, 16, 0, &wall);
        const long long skip = (long long) (0.05 * n);
        qf ne = 0, no = 0, soc = 0;
        long long cnt = 0;
        for (long long m = skip; m < n - skip; ++m) {
            const qf de = y[(size_t) (2 * m)] - xq[(size_t) m];
            const qf ref = (qf) 0.5 * sinq(2 * kPiQ * (qf) ((long long) (f * (2 * m + 1)) % fs_out) / (qf) fs_out);
            const qf dodd = y[(size_t) (2 * m + 1)] - ref;
            ne += de * de; no += dodd * dodd; soc += xq[(size_t) m] * xq[(size_t) m];
            ++cnt;
        }
        const qf psig = soc / (qf) cnt;
        printf("{\"mode\":\"even\",\"prec\":%d,\"freq\":%.0f,\"even_db\":%.2f,\"odd_db\":%.2f,\"wall\":%.2f}\n",
               prec, f, (double) (10 * log10q(psig / (ne / (qf) cnt))),
               (double) (10 * log10q(psig / (no / (qf) cnt))), wall);
        return 0;
    }
    if (mode == "rt") {
        // quad FFT round trip on the exact block grid: r2c -> c2r -> null.
        // This is the ceiling any binary128 transform path can reach, because
        // the transform is an identity in the interior when nothing is removed.
        const double secs = argc > 2 ? std::atof(argv[2]) : 16.0;
        const int fs = argc > 3 ? std::atoi(argv[3]) : 44100;
        const long long n = (long long) std::llround(secs * fs);
        auto x = gen_tone(1000, fs, n, 0.5);
        dpq::Plan pl = dpq::make_plan((int) n);
        std::vector<dpq::QC> h((size_t) (n / 2 + 1));
        std::vector<qf> back((size_t) n);
        dpq::fft_r2c(pl, x.data(), h.data());
        dpq::fft_c2r(pl, h.data(), back.data());
        for (long long i = 0; i < n; ++i) back[(size_t) i] /= (qf) n;
        const long long per = fs / gcd_ll(1000, fs);
        const long long sk = ((n / 20 + per - 1) / per) * per;
        const long long len = ((n - 2 * sk) / per) * per;
        printf("{\"mode\":\"rt\",\"n\":%lld,\"fs\":%d,\"null_db\":%.2f}\n",
               n, fs, qnull(back.data(), len, sk, len, fs, 1000));
        return 0;
    }
    if (mode == "rt2") {
        // The actual pipeline operation: r2c at P, zero-pad the spectrum to
        // Q/2+1, c2r at Q. This is what the resampler does for every block, so
        // it is the ceiling of the block path, not the same-size round trip.
        const int P = argc > 2 ? std::atoi(argv[2]) : 705600;
        const int Q = argc > 3 ? std::atoi(argv[3]) : 1411200;
        const int fs = argc > 4 ? std::atoi(argv[4]) : 44100;
        auto x = gen_tone(1000, fs, P, 0.5);
        dpq::Plan pp = dpq::make_plan(P);
        dpq::Plan pq = dpq::make_plan(Q);
        std::vector<dpq::QC> h((size_t) (Q / 2 + 1));
        for (auto& z : h) z = dpq::make_qc(0, 0);
        dpq::fft_r2c(pp, x.data(), h.data());
        std::vector<qf> y((size_t) Q);
        dpq::fft_c2r(pq, h.data(), y.data());
        const qf inv = 1 / (qf) P;
        for (int i = 0; i < Q; ++i) y[(size_t) i] *= inv;
        const int fs_out = fs * 2;
        const long long per = fs_out / gcd_ll(1000, fs_out);
        const long long sk = ((Q / 20 + per - 1) / per) * per;
        const long long len = ((Q - 2 * sk) / per) * per;
        printf("{\"mode\":\"rt2\",\"P\":%d,\"Q\":%d,\"null_db\":%.2f}\n",
               P, Q, qnull(y.data(), len, sk, len, fs_out, 1000));
        return 0;
    }
    if (mode == "self") {
        const double f = std::atof(argv[2]);
        const int fs = argc > 3 ? std::atoi(argv[3]) : 88200;
        const double secs = argc > 4 ? std::atof(argv[4]) : 4.0;
        const long long n = (long long) std::llround(secs * fs);
        auto y = gen_tone(f, fs, n, 0.5);
        const double sk = argc > 5 ? std::atof(argv[5]) : 0.0;
        const long long per = fs / gcd_ll((long long) f, (long long) fs);
        long long m = (long long) (sk * n);
        m = ((m + per - 1) / per) * per;
        const long long len = ((n - 2 * m) / per) * per;
        printf("{\"mode\":\"self\",\"freq\":%.0f,\"fs\":%d,\"skip\":%.2f,\"null_db\":%.2f}\n",
               f, fs, sk, qnull(y.data(), len, m, len, fs, (long long) f));
        return 0;
    }
    if (mode == "dump") {
        // dump <secs> <f> [fs_in] [fs_out] [block] [path]  -> raw f128 output
        const double secs = argc > 2 ? std::atof(argv[2]) : 16.0;
        const double f = argc > 3 ? std::atof(argv[3]) : 1000.0;
        const int fs_in = argc > 4 ? std::atoi(argv[4]) : 44100;
        const int fs_out = argc > 5 ? std::atoi(argv[5]) : 88200;
        const double block = argc > 6 ? std::atof(argv[6]) : 16.0;
        const char* path = argc > 7 ? argv[7] : "probe_out.f128";
        const long long n = (long long) std::llround(secs * fs_in);
        auto xq = gen_tone(f, fs_in, n, 0.5);
        std::vector<double> xd((size_t) n);
        for (long long i = 0; i < n; ++i) xd[(size_t) i] = (double) xq[(size_t) i];
        double wall = 0;
        auto y = run_and_keep(2, xq, xd, fs_in, fs_out, block, 0, &wall);
        FILE* fp = std::fopen(path, "wb");
        if (!fp) { std::fprintf(stderr, "cannot write %s\n", path); return 1; }
        const size_t wr = std::fwrite(y.data(), 16, y.size(), fp);
        std::fclose(fp);
        std::printf("{\"mode\":\"dump\",\"frames\":%zu,\"written\":%zu,\"wall\":%.3f}\n",
                    y.size(), wr, wall);
        return 0;
    }
    if (mode == "null" || mode == "sinad") {
        const int prec = std::atoi(argv[2]);
        const double secs = std::atof(argv[3]);
        const double f = std::atof(argv[4]);
        const double block = argc > 5 ? std::atof(argv[5]) : 16.0;
        const int workers = argc > 6 ? std::atoi(argv[6]) : 0;
        g_btaper = argc > 7 ? std::atof(argv[7]) : 20.0;
        g_context = argc > 9 ? std::atof(argv[9]) : 800.0;
        g_shape = argc > 8 ? std::atoi(argv[8]) : dpggb::TAPER_SMOOTH5;
        if (g_shape != 16 && g_shape != 20 && (g_shape < 0 || g_shape > 12))
            g_shape = dpggb::TAPER_SMOOTH5;
        const int fs_in = argc > 10 ? std::atoi(argv[10]) : 44100;
        const int fs_out = argc > 11 ? std::atoi(argv[11]) : 88200;
        const double g_skip = argc > 12 ? std::atof(argv[12]) : 0.05;
        if (const char* e = std::getenv("DPQ_FADE")) g_fade = std::atof(e);
        if (const char* e = std::getenv("DPQ_AMP")) g_amp = std::atof(e);
        const long long n = (long long) std::llround(secs * fs_in);
        auto xq = gen_tone(f, fs_in, n, g_amp);
        std::vector<double> xd((size_t) n);
        for (long long i = 0; i < n; ++i) xd[(size_t) i] = (double) xq[(size_t) i];
        double wall = 0;
        auto y = run_and_keep(prec, xq, xd, fs_in, fs_out, block, workers, &wall);
        const long long no = (long long) std::llround((double) n * fs_out / fs_in);
        const long long skip = (long long) (g_skip * no);
        if (mode == "null") {
            double amp = 0;
            // A rectangular-window projection is only exact when the segment
            // holds an integer number of cycles. Otherwise the residual is the
            // window's leakage skirt (-260 dB at 997 Hz over 3.6 s), which has
            // nothing to do with the engine. Snap skip and length to whole
            // periods of fs/gcd(f,fs).
            const long long per = fs_out / gcd_ll((long long) f, (long long) fs_out);
            long long sk = ((skip + per - 1) / per) * per;
            long long len = ((no - 2 * sk) / per) * per;
            const double nl = qnull(y.data(), len, sk, len, fs_out, (long long) f, &amp);
            printf("{\"mode\":\"null\",\"prec\":%d,\"freq\":%.0f,\"sec\":%.1f,\"block\":%.1f,"
                   "\"workers\":%d,\"null_db\":%.2f,\"amp\":%.9f,\"wall\":%.3f,"
                   "\"speed\":%.2f}\n", prec, f, secs, block, workers, nl, amp, wall, (double) n / fs_in / wall);
        } else {
            const long long w = fs_out;   // 1 s
            const long long m = skip;
            std::vector<double> rows, settled;
            double med_sfdr = 0, med_enob = 0;
            std::vector<double> sf, en;
            for (long long st = m; st + w <= no - m; st += fs_out / 4) {
                Tone t = qsinad(y.data() + st, w, fs_out, (long long) f);
                const double tt = (double) st / fs_out;
                rows.push_back(t.sinad);
                sf.push_back(t.sfdr);
                en.push_back(t.enob);
                if (tt >= 2.0 && tt <= 13.0) settled.push_back(t.sinad);
                if (getenv("DPQ_ALL")) printf("  t=%.2f sinad %.2f sfdr %.2f enob %.2f spur %.1f Hz\n",
                       tt, t.sinad, t.sfdr, t.enob, t.spur_hz);
            }
            std::sort(rows.begin(), rows.end());
            std::sort(settled.begin(), settled.end());
            std::sort(sf.begin(), sf.end());
            std::sort(en.begin(), en.end());
            med_sfdr = sf[sf.size() / 2];
            med_enob = en[en.size() / 2];
            printf("{\"mode\":\"sinad\",\"prec\":%d,\"block\":%.1f,\"workers\":%d,"
                   "\"settled\":%.2f,\"median\":%.2f,\"worst\":%.2f,\"sfdr\":%.2f,"
                   "\"enob\":%.3f,\"windows\":%d,\"wall\":%.3f,\"speed\":%.2f}\n",
                   prec, block, workers, settled.empty() ? 0.0 : settled[settled.size() / 2],
                   rows[rows.size() / 2], rows.front(), med_sfdr, med_enob, (int) rows.size(),
                   wall, (double) n / fs_in / wall);
        }
        return 0;
    }
    // Two-tone intermodulation and a single-tone image/harmonic scan. Both use
    // the same exact integer-phase projection as qnull, so a product that is
    // not there reads the analyser floor, not a window skirt.
    // 40-tone multitone: the worst per-tone residual is what a broadband
    // signal actually sees, and it is not the single-tone number.
    if (mode == "mt") {
        const int prec = std::atoi(argv[2]);
        const double secs = std::atof(argv[3]);
        const int ntone = argc > 4 ? std::atoi(argv[4]) : 40;
        const int step = argc > 5 ? std::atoi(argv[5]) : 500;   // spacing, so count and bandwidth are separate axes
        const int start = argc > 6 ? std::atoi(argv[6]) : 200;  // band position, so count and band are separate too
        const int fs_in = 44100, fs_out = 88200;
        const long long n = (long long) std::llround(secs * fs_in);
        std::vector<int> fr;
        for (int k = 0; k < ntone; ++k) fr.push_back(start + k * step);
        // Equal amplitudes and zero phase: the truth is known exactly, so the
        // per-tone gain error is measurable, not just the residual.
        const double tone_amp = 0.5 / ntone;
        std::vector<qf> xq((size_t) n, 0);
        for (int k = 0; k < ntone; ++k) {
            const long long f = fr[(size_t) k];
            const qf a = (qf) tone_amp;
            for (long long i = 0; i < n; ++i) {
                const long long m = (f * i) % fs_in;
                xq[(size_t) i] += a * sinq(2 * kPiQ * (qf) m / (qf) fs_in);
            }
        }
        std::vector<double> xd((size_t) n);
        for (long long i = 0; i < n; ++i) xd[(size_t) i] = (double) xq[(size_t) i];
        double wall = 0;
        auto y = run_and_keep(prec, xq, xd, fs_in, fs_out, 16.0, 0, &wall);
        const long long no = (long long) y.size();
        const long long w = fs_out;
        const long long st = ((long long) (0.25 * no) / w) * w;
        const qf* seg = y.data() + st;
        // Fit DC + every tone, subtract the whole model, then read what is left.
        // Reading each tone's own level instead would just print the stimulus.
        std::vector<Proj> fit((size_t) ntone);
        for (int k = 0; k < ntone; ++k) fit[(size_t) k] = project(seg, w, st, fs_out, fr[(size_t) k]);
        qf dc = 0;
        for (long long i = 0; i < w; ++i) dc += seg[i];
        dc /= (qf) w;
        // Two rounds of re-projection on the residual, the same refinement
        // qnull uses. Without them the first-order fit leaves a bias that sits
        // 30 dB above the engine and would be read as engine error.
        std::vector<qf> r((size_t) w);
        auto rebuild = [&]() {
            for (long long i = 0; i < w; ++i) {
                qf m = dc;
                for (int k = 0; k < ntone; ++k) {
                    const long long f = fr[(size_t) k];
                    const long long per = fs_out / gcd_ll(f, fs_out);
                    const qf th = 2 * kPiQ * (qf) (((st + i) % per) * (f % fs_out)) / (qf) fs_out;
                    m += fit[(size_t) k].a * cosq(th) + fit[(size_t) k].b * sinq(th);
                }
                r[(size_t) i] = seg[i] - m;
            }
        };
        rebuild();
        const int nref = std::getenv("DPQ_REFINE") ? std::atoi(std::getenv("DPQ_REFINE")) : 2;
        for (int it = 0; it < nref; ++it) {
            qf dd = 0;
            for (long long i = 0; i < w; ++i) dd += r[(size_t) i];
            dc += dd / (qf) w;
            for (int k = 0; k < ntone; ++k) {
                Proj q = project(r.data(), w, st, fs_out, fr[(size_t) k]);
                fit[(size_t) k].a += q.a;
                fit[(size_t) k].b += q.b;
            }
            rebuild();
        }
        qf pres = 0, psig = 0;
        for (long long i = 0; i < w; ++i) {
            pres += r[(size_t) i] * r[(size_t) i];
            psig += seg[i] * seg[i];
        }
        double worst_gain = -1e9;
        for (int k = 0; k < ntone; ++k) {
            const double a = (double) sqrtq(fit[(size_t) k].a * fit[(size_t) k].a +
                                           fit[(size_t) k].b * fit[(size_t) k].b);
            const double e = 20 * std::log10(std::max(a, 1e-300) / tone_amp);
            if (e > worst_gain) worst_gain = e;
        }
        const double null_db = (double) (10 * log10q(psig / pres));
        printf("{\"mode\":\"mt\",\"prec\":%d,\"ntone\":%d,\"null\":%.2f,\"worst_gain_db\":%.2f,"
               "\"wall\":%.3f", prec, ntone, null_db, worst_gain, wall);
        if (std::getenv("DPQ_DEBUG")) {
            printf(",\"psig\":%.3e,\"pres\":%.3e,\"dc\":%.3e,\"amps\":[", (double) psig, (double) pres, (double) dc);
            for (int k = 0; k < ntone; ++k)
                printf("%s%.6f", k ? "," : "",
                       (double) sqrtq(fit[(size_t) k].a * fit[(size_t) k].a +
                                      fit[(size_t) k].b * fit[(size_t) k].b));
            printf("]");
        }
        printf("}\n");
        return 0;
    }
    if (mode == "imd" || mode == "image") {
        const int prec = std::atoi(argv[2]);
        const double secs = std::atof(argv[3]);
        std::vector<long long> tf;
        if (mode == "imd") {
            tf.push_back((long long) std::llround(std::atof(argv[4])));
            tf.push_back((long long) std::llround(std::atof(argv[5])));
        } else {
            tf.push_back((long long) std::llround(std::atof(argv[4])));
        }
        const int fs_in = 44100, fs_out = 88200;
        const long long n = (long long) std::llround(secs * fs_in);
        const double per_amp = tf.size() == 1 ? 0.5 : 0.25;
        std::vector<qf> xq((size_t) n, 0);
        for (size_t k = 0; k < tf.size(); ++k) {
            const long long f = tf[k];
            const qf a = (qf) per_amp;
            for (long long i = 0; i < n; ++i) {
                const long long m = (f * i) % fs_in;
                xq[(size_t) i] += a * sinq(2 * kPiQ * (qf) m / (qf) fs_in);
            }
        }
        std::vector<double> xd((size_t) n);
        for (long long i = 0; i < n; ++i) xd[(size_t) i] = (double) xq[(size_t) i];
        double wall = 0;
        auto y = run_and_keep(prec, xq, xd, fs_in, fs_out, 16.0, 0, &wall);
        const long long no = (long long) y.size();
        const long long w = fs_out;                       // 1 s holds whole cycles of any integer f
        const long long st = ((long long) (0.25 * no) / w) * w;
        const qf* seg = y.data() + st;
        auto lvl = [&](long long p) {
            Proj q = project(seg, w, st, fs_out, p);
            return (double) sqrtq(q.a * q.a + q.b * q.b);
        };
        std::vector<long long> prods;
        if (mode == "imd") {
            const long long f1 = tf[0], f2 = tf[1];
            prods = {f1, f2, 2 * f1, 3 * f1, 2 * f2, 3 * f2, f2 - f1, f1 + f2,
                     2 * f1 - f2, 2 * f2 - f1, 2 * f1 + f2, f1 + 2 * f2};
        } else {
            const long long f = tf[0];
            prods = {f, 2 * f, 3 * f, fs_in - f, fs_in + f};
        }
        printf("{\"mode\":\"%s\",\"prec\":%d,\"wall\":%.3f,\"rows\":[", mode.c_str(), prec, wall);
        for (size_t i = 0; i < prods.size(); ++i) {
            const double a = lvl(prods[i]);
            printf("%s{\"f\":%lld,\"db\":%.2f}", i ? "," : "", prods[i],
                   20 * std::log10(std::max(a, 1e-300)));
        }
        printf("]}\n");
        return 0;
    }
    if (mode == "fft") {
        const int P = 708588, Q = 1417176;
        std::vector<qf> x((size_t) P);
        for (int i = 0; i < P; ++i) x[(size_t) i] = sinq(2 * kPiQ * (qf) i / (qf) P);
        auto t0 = std::chrono::steady_clock::now();
        dpq::Plan p1 = dpq::make_plan(P);
        dpq::Plan p2 = dpq::make_plan(Q);
        auto t1 = std::chrono::steady_clock::now();
        std::vector<dpq::QC> h((size_t) (Q / 2 + 1));
        for (auto& z : h) z = dpq::make_qc(0, 0);
        std::vector<qf> y((size_t) Q);
        double best_r2c = 1e9, best_c2r = 1e9;
        for (int rep = 0; rep < 3; ++rep) {
            auto a = std::chrono::steady_clock::now();
            dpq::fft_r2c(p1, x.data(), h.data());
            auto b = std::chrono::steady_clock::now();
            dpq::fft_c2r(p2, h.data(), y.data());
            auto c = std::chrono::steady_clock::now();
            best_r2c = std::min(best_r2c, std::chrono::duration<double>(b - a).count());
            best_c2r = std::min(best_c2r, std::chrono::duration<double>(c - b).count());
        }
        // FFTW double, same grids
        std::vector<double> xd((size_t) P), yd((size_t) Q);
        for (int i = 0; i < P; ++i) xd[(size_t) i] = (double) x[(size_t) i];
        std::vector<fftw_complex> hd((size_t) (Q / 2 + 1));
        fftw_plan pr = fftw_plan_dft_r2c_1d(P, xd.data(), hd.data(), FFTW_ESTIMATE);
        fftw_plan pc = fftw_plan_dft_c2r_1d(Q, hd.data(), yd.data(), FFTW_ESTIMATE);
        double bd_r = 1e9, bd_c = 1e9;
        for (int rep = 0; rep < 5; ++rep) {
            auto a = std::chrono::steady_clock::now();
            fftw_execute(pr);
            auto b = std::chrono::steady_clock::now();
            fftw_execute(pc);
            auto c = std::chrono::steady_clock::now();
            bd_r = std::min(bd_r, std::chrono::duration<double>(b - a).count());
            bd_c = std::min(bd_c, std::chrono::duration<double>(c - b).count());
        }
        fftw_destroy_plan(pr); fftw_destroy_plan(pc);
        printf("{\"mode\":\"fft\",\"plan_s\":%.3f,\"quad_r2c\":%.3f,\"quad_c2r\":%.3f,"
               "\"dbl_r2c\":%.4f,\"dbl_c2r\":%.4f}\n",
               std::chrono::duration<double>(t1 - t0).count(), best_r2c, best_c2r, bd_r, bd_c);
        return 0;
    }
    if (mode == "ld") {
        // The x87 80-bit path with long double I/O: the input tone and the
        // output both carry a 64-bit mantissa, so this is the strongest
        // "cheap" precision the machine offers, and it is what a user gets
        // from precision=1 plus a 16-byte file format.
        const double secs = std::atof(argv[2]);
        const double f = std::atof(argv[3]);
        const int fs_in = 44100, fs_out = 88200;
        const long long n = (long long) std::llround(secs * fs_in);
        auto xq = gen_tone(f, fs_in, n, 0.5);
        std::vector<long double> xl((size_t) n);
        for (long long i = 0; i < n; ++i) xl[(size_t) i] = (long double) xq[(size_t) i];
        dpggb::Cfg cfg;
        cfg.in_rate = fs_in;
        cfg.out_rate = fs_out;
        cfg.channels = 1;
        cfg.block_sec = 16.0;
        cfg.context_ms = g_context;
        cfg.block_taper_ms = g_btaper;
        cfg.taper_shape = g_shape;
        cfg.rolloff_hz = 200.0;
        cfg.workers = 0;
        cfg.precision = 1;
        const dpggb::Ratio rr = dpggb::reduce_ratio(fs_in, fs_out);
        const auto t0 = std::chrono::steady_clock::now();
        auto ld_y = dpggb::resample_channel_ld(xl.data(), (size_t) n, cfg, rr);
        const double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
        std::vector<qf> y(ld_y.size());
        for (size_t i = 0; i < y.size(); ++i) y[(size_t) i] = (qf) ld_y[i];
        const long long no = (long long) y.size();
        const long long per = fs_out / gcd_ll((long long) f, (long long) fs_out);
        long long sk = (long long) (0.05 * no);
        sk = ((sk + per - 1) / per) * per;
        const long long len = ((no - 2 * sk) / per) * per;
        const double nl = qnull(y.data(), len, sk, len, fs_out, (long long) f);
        printf("{\"mode\":\"ld\",\"prec\":1,\"freq\":%.0f,\"sec\":%.1f,\"null_db\":%.2f,\"wall\":%.3f,\"speed\":%.2f}\n",
               f, secs, nl, wall, (double) n / fs_in / wall);
        return 0;
    }
    if (mode == "compare") {
        const int fs_in = 44100, fs_out = 88200;
        const long long n = 4LL * fs_in;
        auto xq = gen_tone(1000, fs_in, n, 0.5);
        std::vector<double> xd((size_t) n);
        for (long long i = 0; i < n; ++i) xd[(size_t) i] = (double) xq[(size_t) i];
        double w0 = 0, w2 = 0;
        auto yd = run_and_keep(0, xq, xd, fs_in, fs_out, 16, 0, &w0);
        auto yq = run_and_keep(2, xq, xd, fs_in, fs_out, 16, 0, &w2);
        const size_t m = std::min(yd.size(), yq.size());
        qf num = 0, den = 0, mx = 0;
        for (size_t i = 0; i < m; ++i) {
            const qf d = yq[i] - (qf) (double) yd[i];
            num += d * d;
            den += (qf) (double) yd[i] * (qf) (double) yd[i];
            mx = std::max(mx, (qf) (d < 0 ? -d : d));
        }
        printf("{\"mode\":\"compare\",\"rms_diff_db\":%.2f,\"max_abs\":%.3e,\"n\":%zu}\n",
               (double) (10 * log10q(num / den)), (double) mx, m);
        return 0;
    }
    if (mode == "speed") {
        const int prec = std::atoi(argv[2]);
        const double secs = std::atof(argv[3]);
        const double block = argc > 4 ? std::atof(argv[4]) : 16.0;
        const int workers = argc > 5 ? std::atoi(argv[5]) : 0;
        const int fs_in = 44100, fs_out = 88200;
        const long long n = (long long) std::llround(secs * fs_in);
        auto mono = gen_tone(1000, fs_in, n, 0.5);
        std::vector<qf> xq;
        xq.reserve(mono.size() * 2);
        for (int c = 0; c < 2; ++c) xq.insert(xq.end(), mono.begin(), mono.end());
        std::vector<double> xd(xq.size());
        for (size_t i = 0; i < xq.size(); ++i) xd[i] = (double) xq[i];
        // two channels, split the worker budget the way the CLI does
        const int hw = workers > 0 ? workers : (int) std::thread::hardware_concurrency();
        const int ch_par = std::min(2, hw);
        const int per_ch = std::max(1, hw / ch_par);
        std::vector<double> walls(2);
        const auto t0 = std::chrono::steady_clock::now();
        std::vector<std::thread> pool;
        for (int c = 0; c < ch_par; ++c) {
            pool.emplace_back([&, c]() {
                std::vector<qf> ch(xq.begin() + c * n, xq.begin() + (c + 1) * n);
                std::vector<double> cd(xd.begin() + c * n, xd.begin() + (c + 1) * n);
                walls[c] = run_engine(prec, ch, cd, fs_in, fs_out, block, per_ch).wall;
            });
        }
        for (auto& t : pool) t.join();
        const double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
        printf("{\"mode\":\"speed\",\"prec\":%d,\"sec\":%.1f,\"block\":%.1f,\"workers\":%d,"
               "\"per_ch\":%d,\"wall\":%.3f,\"speed\":%.2f}\n",
               prec, secs, block, hw, per_ch, wall, secs / wall);
        return 0;
    }
    std::fprintf(stderr, "unknown mode\n");
    return 1;
}
