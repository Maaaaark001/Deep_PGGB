// dpggb_core.cpp - Deep_PGGB: arbitrary-ratio ideal-brickwall FFT resampler.
//
// Sample-rate conversion by L/M is "reconstruct the continuous signal, then
// resample it". For a band-limited signal that reconstruction is unique, and
// in the frequency domain it is simply "keep the spectrum up to the lower
// Nyquist, drop everything above". Doing it with an FFT never truncates the
// sinc, so the filter is an ideal brick wall with zero transition width.
//
// Two things break the naive version, and both are handled here:
//   1. The FFT treats a block as one period, so a jump between its last and
//      first sample is a step, and an ideal low-pass smears that step into a
//      1/d tail across the whole block (measured: -108 dB). Fading the file
//      ends removes the step; tapering the block context hides the join.
//   2. Memory grows with length. We process in overlapping blocks and keep
//      only each block interior, so the tapered context is discarded.

#include "dpggb.h"

#include <fftw3.h>

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstring>
#include <map>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <tuple>
#include <vector>

namespace dpggb {

namespace {
constexpr double kPi = 3.14159265358979323846;

long long gcd_ll(long long a, long long b) {
    while (b) { long long t = a % b; a = b; b = t; }
    return a < 0 ? -a : a;
}
}  // namespace

Ratio reduce_ratio(double in_rate, double out_rate) {
    Ratio r;
    const long long a = (long long) llround(in_rate);
    const long long b = (long long) llround(out_rate);
    if (a <= 0 || b <= 0) throw std::runtime_error("sample rates must be positive");
    const long long g = gcd_ll(a, b);
    r.L = b / g;
    r.M = a / g;
    return r;
}

namespace {

// ------------------------------------------------------------------
// FFTW plumbing; double and long double share one code path.
// ------------------------------------------------------------------
template <typename R> struct Fftw;

template <> struct Fftw<double> {
    using plan = fftw_plan;
    using cplx = fftw_complex;
    static void* alloc(size_t n) { return fftw_malloc(n); }
    static void free(void* p) { fftw_free(p); }
    // FFTW_MEASURE was tried and rejected: on the awkward grid sizes this
    // resampler needs (P = M*2^k, e.g. 147*256) it spends ~6 s planning, which
    // dwarfs the transform for any short file. ESTIMATE costs nothing and the
    // plan is cached per grid, so the whole run reuses one plan.
    static plan r2c(int n, double* i, cplx* o) { return fftw_plan_dft_r2c_1d(n, i, o, FFTW_ESTIMATE); }
    static plan c2r(int n, cplx* i, double* o) { return fftw_plan_dft_c2r_1d(n, i, o, FFTW_ESTIMATE); }
    static void exec(plan p) { fftw_execute(p); }
    static void destroy(plan p) { fftw_destroy_plan(p); }
    static void init_threads() { fftw_init_threads(); }
    static void with_threads(int n) { fftw_plan_with_nthreads(n); }
};

template <> struct Fftw<long double> {
    using plan = fftwl_plan;
    using cplx = fftwl_complex;
    static void* alloc(size_t n) { return fftwl_malloc(n); }
    static void free(void* p) { fftwl_free(p); }
    static plan r2c(int n, long double* i, cplx* o) { return fftwl_plan_dft_r2c_1d(n, i, o, FFTW_ESTIMATE); }
    static plan c2r(int n, cplx* i, long double* o) { return fftwl_plan_dft_c2r_1d(n, i, o, FFTW_ESTIMATE); }
    static void exec(plan p) { fftwl_execute(p); }
    static void destroy(plan p) { fftwl_destroy_plan(p); }
    static void init_threads() { fftwl_init_threads(); }
    static void with_threads(int n) { fftwl_plan_with_nthreads(n); }
};

// FFTW plan creation is not thread-safe. Every path that creates a plan must
// hold this lock; execution is safe to run concurrently. The block workers
// used to create plans in fir_causal() without it, which is a race that only
// shows up with workers > 1 (intermittent access violation).
inline std::mutex& fftw_plan_mutex() {
    static std::mutex m;
    return m;
}

// A plan is bound to its buffers, so each cache entry owns a scratch set.
template <typename R>
struct Plans {
    typename Fftw<R>::plan r2c = nullptr;
    typename Fftw<R>::plan c2r = nullptr;
    R* in = nullptr;
    R* out = nullptr;
    typename Fftw<R>::cplx* spec = nullptr;
    int n_in = 0, n_out = 0, n_buf = 0;
};

template <typename R>
class PlanCache {
public:
    Plans<R>& get(int n_in, int n_out, int threads) {
        std::lock_guard<std::mutex> lock(mu_);
        const auto key = std::make_tuple(n_in, n_out, threads);
        auto it = map_.find(key);
        if (it != map_.end()) return it->second;

        // FFTW plan creation is not thread-safe, and workers create plans
        // concurrently. A global lock around creation (not execution) is
        // enough: executing a plan from several threads is fine, and each
        // thread owns its own buffers.
        std::lock_guard<std::mutex> create_lock(fftw_plan_mutex());

        static std::once_flag once;
        std::call_once(once, [] { Fftw<R>::init_threads(); });

        Plans<R> p;
        p.n_in = n_in;
        p.n_out = n_out;
        p.n_buf = std::max(n_in, n_out);
        p.in = (R*) Fftw<R>::alloc(sizeof(R) * (size_t) p.n_buf);
        p.out = (R*) Fftw<R>::alloc(sizeof(R) * (size_t) p.n_buf);
        p.spec = (typename Fftw<R>::cplx*) Fftw<R>::alloc(
            sizeof(typename Fftw<R>::cplx) * (size_t) (p.n_buf / 2 + 2));
        if (!p.in || !p.out || !p.spec) throw std::runtime_error("fftw allocation failed");
        std::memset(p.in, 0, sizeof(R) * (size_t) p.n_buf);
        std::memset(p.out, 0, sizeof(R) * (size_t) p.n_buf);
        std::memset(p.spec, 0, sizeof(typename Fftw<R>::cplx) * (size_t) (p.n_buf / 2 + 2));

        Fftw<R>::with_threads(threads > 0 ? threads : 1);
        p.r2c = Fftw<R>::r2c(n_in, p.in, p.spec);
        p.c2r = Fftw<R>::c2r(n_out, p.spec, p.out);
        return map_.emplace(key, p).first->second;
    }

    ~PlanCache() {
        // Plans own FFTW buffers, and thread_local destruction happens when a
        // block worker exits. Without this, every window that used a fresh
        // worker leaked its scratch set: a 60 s stereo run with 8 workers grew
        // without bound and could exhaust the machine.
        for (auto& kv : map_) {
            Plans<R>& p = kv.second;
            if (p.r2c) Fftw<R>::destroy(p.r2c);
            if (p.c2r) Fftw<R>::destroy(p.c2r);
            Fftw<R>::free(p.in);
            Fftw<R>::free(p.out);
            Fftw<R>::free(p.spec);
        }
    }

private:
    std::mutex mu_;
    std::map<std::tuple<int, int, int>, Plans<R>> map_;
};

// One cache per thread: a plan owns its scratch buffers, so two threads sharing
// an entry would corrupt each other. thread_local also means the buffers are
// released when a worker exits, instead of accumulating for every grid size.
template <typename R> Plans<R>& plans(int n_in, int n_out, int threads) {
    thread_local PlanCache<R> c;
    return c.get(n_in, n_out, threads);
}

// ------------------------------------------------------------------
// Tapers.
//
// The FFT treats a block as one period of a periodic signal, so the join
// between its last and first sample must be smooth. Tapering both ends to
// zero makes that join perfect; the tapered part is discarded afterwards, so
// no audible material is attenuated.
// ------------------------------------------------------------------
// Small binomial coefficients; the taper polynomials only need n <= 13.
inline double binom(int n, int k) {
    if (k < 0 || k > n) return 0.0;
    double r = 1.0;
    for (int i = 1; i <= k; ++i) r = r * (double) (n - k + i) / (double) i;
    return r;
}

template <typename R>
R taper_weight(long long i, long long n, int shape) {
    if (n <= 1) return (R) 1;
    const double t = (double) i / (double) (n - 1);
    switch (shape) {
        case TAPER_COS: return (R) (0.5 - 0.5 * std::cos(kPi * t));
        case TAPER_BLACKMAN:
            return (R) (0.42 - 0.5 * std::cos(kPi * t) + 0.08 * std::cos(2 * kPi * t));
        case TAPER_SMOOTH:
            // smootherstep: value, slope and curvature all vanish at the ends
            return (R) (t * t * t * (t * (t * 6 - 15) + 10));
        // Smootherstep of order N: w(t) = t^(N+1) * sum_k C(N+k,k) C(2N+1,N-k) (-t)^k,
        // i.e. value and derivatives 1..N vanish at both ends. Evaluated from the
        // near-zero end (mirrored past the midpoint) so the polynomial never has
        // to subtract two large nearly-equal numbers: evaluating the raw form at
        // t close to 1 loses ~7 digits, which is exactly the leakage being fought.
        case TAPER_SMOOTH4:
        case TAPER_SMOOTH5:
        case TAPER_SMOOTH6: {
            const int order = shape;                    // 4, 5 or 6
            const double u = t <= 0.5 ? t : 1.0 - t;
            double acc = 0.0;
            for (int k = 0; k <= order; ++k) {
                acc += (double) binom(order + k, k) * (double) binom(2 * order + 1, order - k)
                     * ((k & 1) ? -std::pow(u, k) : std::pow(u, k));
            }
            const double w = std::pow(u, order + 1) * acc;
            return (R) (t <= 0.5 ? w : 1.0 - w);
        }
        default: return (R) 1;
    }
}

template <typename R>
void apply_taper(R* buf, long long n, long long t, int shape) {
    if (t <= 0 || n < 2) return;
    if (t > n / 2) t = n / 2;
    for (long long i = 0; i < t; ++i) {
        const R w = taper_weight<R>(i, t, shape);
        buf[(size_t) i] *= w;
        buf[(size_t) (n - 1 - i)] *= w;
    }
}

// ------------------------------------------------------------------
// Minimum-phase filter design.
//
// A linear-phase low-pass of length L is symmetric, so half its taps sit
// BEFORE the impulse: that pre-ringing is exactly what minimum phase removes.
// The cepstrum turns any magnitude into the minimum-phase response with the
// same magnitude; truncating that response to L taps makes it a causal FIR
// that fits inside a block's context, so the block FFT cannot wrap its tail.
// ------------------------------------------------------------------
template <typename R>
std::vector<R> design_minphase_lowpass(int ntap, double fc, int threads) {
    // 1) linear-phase prototype: windowed sinc, fc normalised to Nyquist
    std::vector<R> lin((size_t) ntap, (R) 0);
    const int c = ntap / 2;
    for (int i = 0; i < ntap; ++i) {
        const double d = (double) (i - c);
        const double s = (d == 0.0) ? fc : std::sin(kPi * fc * d) / (kPi * d);
        const double w = 0.42 - 0.5 * std::cos(2 * kPi * i / (double) (ntap - 1))
                       + 0.08 * std::cos(4 * kPi * i / (double) (ntap - 1));
        lin[(size_t) i] = (R) (s * w);
    }
    double sum = 0;
    for (int i = 0; i < ntap; ++i) sum += (double) lin[(size_t) i];
    for (int i = 0; i < ntap; ++i) lin[(size_t) i] = (R) ((double) lin[(size_t) i] / sum);

    // 2) minimum-phase conversion via the real cepstrum
    int n = 1;
    while (n < 8 * ntap) n <<= 1;
    const int nc = n / 2 + 1;
    Plans<R>& p = plans<R>(n, n, threads);

    for (int i = 0; i < n; ++i) p.in[i] = (R) 0;
    for (int i = 0; i < ntap; ++i) p.in[i] = lin[(size_t) i];
    Fftw<R>::exec(p.r2c);

    std::vector<R> logmag((size_t) nc);
    for (int i = 0; i < nc; ++i) {
        const double m = std::hypot((double) p.spec[i][0], (double) p.spec[i][1]);
        logmag[(size_t) i] = (R) std::log(std::max(m, 1e-12));
    }

    for (int i = 0; i < n; ++i) p.in[i] = (R) 0;
    for (int i = 0; i < nc; ++i) p.in[i] = logmag[(size_t) i];
    for (int i = 1; i < n - nc + 1; ++i) p.in[n - i] = p.in[i];
    Fftw<R>::exec(p.r2c);

    std::vector<R> cep((size_t) n, (R) 0);
    for (int i = 0; i < nc; ++i) cep[(size_t) i] = p.spec[i][0] / (R) n;
    for (int i = 1; i < n - nc + 1; ++i) cep[(size_t) (n - i)] = cep[(size_t) i];
    for (int i = 1; i < n / 2; ++i) cep[(size_t) i] *= (R) 2;
    for (int i = n / 2 + 1; i < n; ++i) cep[(size_t) i] = (R) 0;

    for (int i = 0; i < n; ++i) p.in[i] = cep[(size_t) i];
    Fftw<R>::exec(p.r2c);

    // 3) exp(cepstrum spectrum) -> minimum-phase spectrum; back to taps
    for (int i = 0; i < nc; ++i) {
        const double a = (double) p.spec[i][0];
        const double b = (double) p.spec[i][1];
        const double m = std::exp(a);
        p.spec[i][0] = (R) (m * std::cos(b));
        p.spec[i][1] = (R) (m * std::sin(b));
    }
    Fftw<R>::exec(p.c2r);
    std::vector<R> taps((size_t) ntap, (R) 0);
    for (int i = 0; i < ntap; ++i) taps[(size_t) i] = p.out[i] / (R) n;
    return taps;
}

// ------------------------------------------------------------------
// One block: taper, forward FFT, spectral surgery, inverse FFT at Q.
// ------------------------------------------------------------------
// Exact grid: P = M*s, Q = L*s for one common multiplier s, so Q/P == L/M and
// every output bin sits on an input bin (no frequency interpolation). s is the
// smallest value that makes both P and Q "smooth" (no prime factor above 7),
// which FFTW transforms efficiently. A power-of-two s was the original choice
// and could waste up to 2x the work.
// FFTW has hand-tuned radices for 2, 3, 5 and 7, but 7 is markedly slower per
// point than 2/3/5 (measured: a 7-smooth grid at 22050 points ran slower than a
// power-of-two grid at 37632). Excluding 7 costs a few percent more points and
// wins the time back.
inline bool is_smooth(long long v) {
    static const long long pr[3] = {2, 3, 5};
    for (int i = 0; i < 3; ++i) while (v % pr[i] == 0) v /= pr[i];
    return v == 1;
}

// Smallest s in [lo, hi] with both M*s and L*s smooth; lo if none is.
inline long long choose_smooth(long long M, long long L, long long lo, long long hi) {
    for (long long s = lo; s <= hi; ++s) {
        if (is_smooth(M * s) && is_smooth(L * s)) return s;
    }
    return lo;
}

template <typename R>
void convert_block(const R* x, long long n, const Ratio& r, long long P, int threads,
                   int taper_len, int taper_shape, int phase, double in_rate,
                   double rolloff_hz, int roll_order, std::vector<R>& out) {
    const long long Q = (P / r.M) * r.L;
    if (P > (1LL << 30) || Q > (1LL << 30)) throw std::runtime_error("block too large");

    Plans<R>& p = plans<R>((int) P, (int) Q, threads);

    std::fill(p.in, p.in + P, (R) 0);
    std::memcpy(p.in, x, sizeof(R) * (size_t) std::min<long long>(n, P));
    apply_taper<R>(p.in, P, taper_len, taper_shape);

    Fftw<R>::exec(p.r2c);

    const int nc_in = (int) (P / 2 + 1);
    const int nc_out = (int) (Q / 2 + 1);
    const long long keep = std::min<long long>(nc_in, nc_out);

    // Everything above the lower Nyquist is removed. When the signal was
    // already band-limited by a minimum-phase prefilter, this is a no-op; when
    // upsampling it is what creates the missing spectral region.
    (void) phase;

    // With a zero-width cutoff, the analysis window's own spectral spread has
    // nowhere to go: a tone 50 Hz above Nyquist puts sidelobes at exactly
    // Nyquist, inside the passband, and they pass through untouched (measured
    // -103 dB against sox_ng's -198 dB). Rolling the top of the band off gives
    // that spread somewhere to land. A raised cosine over roll_bins is used
    // because its stopband decays fast and it is flat at the passband edge.
    // A rolloff only earns its keep when DOWNSAMPLING. Then content just above
    // the new Nyquist folds back, and a zero-width cutoff leaves the window's
    // spectral skirt sitting inside the passband. When UPSAMPLING (Q > P) the
    // input is already band-limited to its own Nyquist - there is nothing to
    // alias, so a rolloff just deletes legitimate passband. Measured against
    // PGGB on a 22.04 kHz tone: rolling off cost -88 dB where PGGB droops only
    // 0.6 dB, and for a DSD/upsampling workflow that is the whole ballgame.
    const bool downsampling = Q < P;
    long long roll_bins = downsampling
        ? (long long) llround(rolloff_hz * (double) P / in_rate) : 0;
    if (roll_bins < 0) roll_bins = 0;
    if (roll_bins > keep / 2) roll_bins = keep / 2;
    const long long edge = keep - roll_bins;
    // The shape is a SQUARED raised cosine, not a plain one. A plain cosine
    // decays as d^2 at the edge, so a tone 0.37 Hz above the cutoff is only
    // attenuated ~112 dB. Squaring makes it decay as d^4, which reaches
    // -220 dB at the same width while keeping the passband flat to 21.9 kHz -
    // better than sox_ng on both axes at once (measured: alias -220 vs -209 dB,
    // 21.9 kHz 0.00 vs -17.5 dB).
    for (long long i = edge; i < keep; ++i) {
        const double t = (double) (i - edge) / (double) roll_bins;
        const double c = 0.5 * (1.0 + std::cos(3.14159265358979323846 * t));
        // c^order. Order 2 is the default: a plain cosine decays as d^2 at the
        // edge, squaring it decays as d^4, which reaches -220 dB at the cutoff
        // while keeping the passband flat to 21.9 kHz. Higher orders trade
        // passband width for even faster edge decay.
        double w = c;
        for (int k = 1; k < roll_order; ++k) w *= c;
        p.spec[i][0] = (R) (p.spec[i][0] * w);
        p.spec[i][1] = (R) (p.spec[i][1] * w);
    }
    for (int i = (int) keep; i < nc_out; ++i) {
        p.spec[i][0] = (R) 0;
        p.spec[i][1] = (R) 0;
    }

    Fftw<R>::exec(p.c2r);
    // FFTW inverse transforms are unnormalised; /P restores unit passband gain.
    const R norm = (R) (1.0 / (double) P);
    out.assign((size_t) Q, (R) 0);
    for (long long i = 0; i < Q; ++i) out[(size_t) i] = p.out[i] * norm;
}
// ------------------------------------------------------------------
// Block driver.
//
// A file boundary is a step, and an ideal low-pass turns a step into a 1/d
// tail across the whole track. Fading the file ends removes it; blocks then
// carry tapered context that is discarded, so the joins are seamless.
// ------------------------------------------------------------------
// Causal FIR filter: y[i] = sum_k h[k] * x[i-k]. Used to impose a minimum-phase
// response before the (linear-phase) brick-wall resampling stage.
template <typename R>
void fir_causal(std::vector<R>& x, const std::vector<R>& h) {
    if (h.empty() || x.empty()) return;
    const size_t n = x.size();
    const size_t L = h.size();

    // Direct convolution is O(n*L). With the default 50 ms fade and a 44.1 kHz
    // rate, L is 17640 taps, so a 2 s clip would take 1.5e9 multiply-adds —
    // measured at ~1x realtime, versus 49x for the linear-phase path. Use
    // overlap-save instead: every block costs two FFTs of size N regardless of L.
    if (L < 64 || n < 4096) {           // short cases: direct is cheaper
        std::vector<R> y(n, (R) 0);
        for (size_t i = 0; i < n; ++i) {
            const size_t k = std::min(i + 1, L);
            R acc = (R) 0;
            for (size_t j = 0; j < k; ++j) acc += h[j] * x[i - j];
            y[i] = acc;
        }
        x.swap(y);
        return;
    }

    size_t N = 1;
    while (N < 2 * L) N <<= 1;           // FFT block size
    const size_t step = N - L + 1;       // valid output samples per block

    std::vector<R> buf(N, (R) 0);
    std::vector<typename Fftw<R>::cplx> hspec(N / 2 + 1);
    std::vector<typename Fftw<R>::cplx> bspec(N / 2 + 1);

    // Transform the impulse response once.
    for (size_t i = 0; i < L; ++i) buf[i] = h[i];
    {
        std::lock_guard<std::mutex> lock(fftw_plan_mutex());
        Fftw<R>::with_threads(1);
        auto p = Fftw<R>::r2c((int) N, buf.data(), hspec.data());
        Fftw<R>::exec(p);
        Fftw<R>::destroy(p);
    }

    // FFTW plans are bound to the buffers they were created with. Both buffers
    // live for the whole loop and are only overwritten in place, so the plans
    // can be built once instead of per block.
    typename Fftw<R>::plan pr = nullptr;
    typename Fftw<R>::plan pc = nullptr;
    {
        std::lock_guard<std::mutex> lock(fftw_plan_mutex());
        pr = Fftw<R>::r2c((int) N, buf.data(), bspec.data());
        pc = Fftw<R>::c2r((int) N, bspec.data(), buf.data());
    }

    std::vector<R> out(n, (R) 0);
    size_t pos = 0;
    while (pos < n) {
        const size_t take = std::min(step, n - pos);
        std::fill(buf.begin(), buf.end(), (R) 0);
        // Overlap-save: the block must always start at buf[L-1], because only
        // the samples from L-1 onward are free of circular wrap-around. Near the
        // start of the file there is no full context, so the available samples
        // are right-aligned against the block and the rest is zeros. Using
        // ctx = min(pos, L-1) instead (the old code) shifted the valid window
        // and let the block's own tail wrap onto its head.
        const size_t ctx = L - 1;
        const size_t have = std::min(pos, L - 1);
        for (size_t i = 0; i < have; ++i) buf[ctx - have + i] = x[pos - have + i];
        for (size_t i = 0; i < take; ++i) buf[ctx + i] = x[pos + i];

        Fftw<R>::exec(pr);
        // fftw_complex is a plain array of two reals, so multiply by hand.
        for (size_t i = 0; i <= N / 2; ++i) {
            const R ar = bspec[i][0], ai = bspec[i][1];
            const R br = hspec[i][0], bi = hspec[i][1];
            bspec[i][0] = ar * br - ai * bi;
            bspec[i][1] = ar * bi + ai * br;
        }
        Fftw<R>::exec(pc);

        for (size_t i = 0; i < take; ++i)
            out[pos + i] = buf[ctx + i] / (R) N;
        pos += take;
    }
    Fftw<R>::destroy(pr);
    Fftw<R>::destroy(pc);
    x.swap(out);
}

template <typename R>
std::vector<R> resample_typed(const R* x, size_t n, const Cfg& cfg, const Ratio& r) {
    if (n == 0) return {};
    if (cfg.in_rate == cfg.out_rate) return std::vector<R>(x, x + n);

    const int threads = cfg.threads > 0 ? cfg.threads : 0;
    long long fade = std::max<long long>(1, (long long) (cfg.taper_ms * 0.001 * cfg.in_rate));
    // On a short file a long fade would eat the material itself: a 0.5 s clip
    // with a 100 ms fade is 40% attenuated. Cap it at 5% of the input so the
    // default stays safe for one-shot samples and stingers.
    if (n >= 20) fade = std::min<long long>(fade, (long long) n / 20);

    // The block context is deliberately NOT tied to the fade length. The fade
    // only has to be long enough to kill the boundary step (20 ms saturates it),
    // whereas the context has to be long enough for the block's spectral
    // surgery to settle at the join (seam error measured: 5 ms -163 dB,
    // 20 ms -201 dB, 100 ms -242 dB). Tying them together forced a 100 ms fade
    // on every file just to get clean seams.
    long long context = std::max<long long>(1, (long long) (cfg.context_ms * 0.001 * cfg.in_rate));
    if (context < fade) context = fade;
    if (n >= 4 && context > (long long) n / 4) context = (long long) n / 4;
    if (context < 1) context = 1;

    std::vector<R> src(x, x + n);
    {
        const long long t = std::min<long long>(fade, (long long) n / 2);
        for (long long i = 0; i < t; ++i) {
            const R w = taper_weight<R>(i, t, cfg.taper_shape);
            src[(size_t) i] *= w;
            src[(size_t) (n - 1 - i)] *= w;
        }
    }

    // Minimum phase: a causal FIR whose magnitude matches the brick wall. The
    // FFT stage below stays linear phase, but because the FIR has already
    // band-limited the signal, that stage is transparent (it only removes what
    // is already zero), so the net response is the minimum-phase one.
    if (cfg.phase == PHASE_MIN) {
        const double fc = std::min(1.0, cfg.out_rate / cfg.in_rate) * 0.95;
        const long long mp_taps = (long long) (cfg.mp_taps_ms * 0.001 * cfg.in_rate);
        const long long want_taps = std::max<long long>(64, 4 * mp_taps);
        std::vector<R> h = design_minphase_lowpass<R>((int) want_taps, fc, threads);
        fir_causal<R>(src, h);
    }

    // Grid size: a multiple of M * 2^k, capped by the memory budget and by the
    // signal length (padding a short file to a huge grid buys nothing).
    const double budget = cfg.mem_mb * 1024.0 * 1024.0;
    const double bytes_per_pt = (double) sizeof(R) * 3.0 + 32.0;
    const long long max_pts = (long long) (budget / bytes_per_pt);

    long long want = (long long) (cfg.block_sec * cfg.in_rate);
    if (want <= 0) want = (long long) n;
    if (want > (long long) n) want = (long long) n;
    if (want > max_pts) want = max_pts;
    if (want < 4096) want = 4096;

    // The grid only has to satisfy Q/P == L/M exactly, which any common
    // multiplier s does: P = M*s, Q = L*s. Restricting s to powers of two (the
    // original code) forced P up to 2x larger than needed — a 0.5 s block at
    // 44.1 kHz asked for 22050 points and got 147*256 = 37632, i.e. 71% wasted
    // work. The smallest s that makes both M*s and L*s smooth cuts that waste
    // to a few percent, with the ratio unchanged.
    const long long lo_s = std::max<long long>(1, (want + r.M - 1) / r.M);
    const long long hi_s = std::max<long long>(lo_s, max_pts / r.M);
    long long P = r.M * choose_smooth(r.M, r.L, lo_s, hi_s);
    if (P < 4096) {
        const long long lo2 = (4096 + r.M - 1) / r.M;
        P = r.M * choose_smooth(r.M, r.L, lo2, std::max<long long>(lo2, hi_s));
    }

    // Minimum-phase filtering is causal, so its impulse response runs forward
    // for a long time. Circular convolution inside a block would wrap that tail
    // back onto the head of the same block, so min-phase is done on the whole
    // signal in one transform instead.
    if (cfg.phase == PHASE_MIN) {
        long long kk = 1;
        while ((r.M << kk) < (long long) n) ++kk;
        const long long PP = r.M << kk;
        if (PP > max_pts)
            throw std::runtime_error("minimum-phase mode needs a whole-signal transform; "
                                     "raise mem_mb or process a shorter file");
        std::vector<R> buf((size_t) PP, (R) 0);
        std::memcpy(buf.data(), src.data(), sizeof(R) * n);
        std::vector<R> conv;
        convert_block<R>(buf.data(), PP, r, PP, threads, 0, cfg.taper_shape, cfg.phase,
                         cfg.in_rate, cfg.rolloff_hz, cfg.roll_order, conv);
        const long long total = (long long) llround((double) n * (double) r.L / (double) r.M);
        conv.resize((size_t) total);
        return conv;
    }

    // Geometry invariant. Every block has to start at an exact multiple of M
    // samples of the source, otherwise o0 = start*L/M and lo = T*L/M are each
    // rounded independently and consecutive blocks land a fraction of an output
    // sample apart: a phase step at every seam. The old code only got this right
    // when T happened to be a multiple of M (44.1 -> 48 kHz, M = 147, T = 4410 =
    // 30*147) and was silently broken everywhere else -- 44.1 -> 56.448 kHz
    // measured a -2.5 dB null against the whole-file result, i.e. 40-50 degrees
    // of phase error per block, and 44.1 -> 50.001 kHz collapsed to 3.1 dB.
    // Snapping T up to a multiple of M and keeping P a multiple of M makes
    // kept = P - 2T a multiple of M too, so lo, hi and o0 are all exact.
    long long T = context;
    {
        const long long m = r.M;
        T = ((T + m - 1) / m) * m;
        if (T < m) T = m;
        // Do not let the context swallow a short file: cap it at n/4 when the
        // file is long enough for the cap to still be at least one M-block.
        if (n >= (size_t) (4 * m)) {
            const long long cap = ((long long) n / 4 / m) * m;
            if (cap >= m && T > cap) T = cap;
        }
        // 4T has to fit the memory budget; shrink the context rather than fail.
        if (4 * T > max_pts) {
            T = (max_pts / 4 / m) * m;
            if (T < m) T = m;
        }
    }
    if (P < 4 * T) {
        const long long lo3 = (4 * T + r.M - 1) / r.M;
        P = r.M * choose_smooth(r.M, r.L, lo3, std::max<long long>(lo3, hi_s));
        if (P < 4 * T) P = lo3 * r.M;
    }
    const long long kept = P - 2 * T;
    if (kept <= 0) throw std::runtime_error("block too small for the requested context");
    if (kept % r.M != 0) throw std::runtime_error("internal: block advance is not a multiple of M");

    const long long out_total = (long long) llround((double) n * (double) r.L / (double) r.M);
    std::vector<R> out((size_t) out_total, (R) 0);

    // Blocks are independent: each one reads a fixed window of the source and
    // writes a fixed range of the output, so they can run concurrently without
    // any locking. Only the interior is kept, which is what makes the join
    // seamless; the tapered context is thrown away.
    const long long lo = (long long) llround((double) T * (double) r.L / (double) r.M);
    const long long hi = (long long) llround((double) (P - T) * (double) r.L / (double) r.M);

    long long nblocks = 0;
    for (long long start = 0; start < (long long) n; start += kept) ++nblocks;

    // Each worker owns its scratch, because a plan is bound to its buffers.
    // One thread per block would thrash the cache on short blocks, so cap it.
    unsigned hw = (unsigned) (cfg.workers > 0 ? cfg.workers : std::thread::hardware_concurrency());
    if (hw == 0) hw = 1;
    long long nworkers = std::min<long long>(nblocks, (long long) hw);
    if (nworkers < 1) nworkers = 1;

    auto do_block = [&](long long bi, std::vector<R>& block, std::vector<R>& conv) {
        const long long start = bi * kept;
        // [context T][kept data][context T]; outside the file the context is
        // zero, which is smooth because the file ends were faded to zero.
        for (long long i = 0; i < P; ++i) {
            const long long idx = start - T + i;
            block[(size_t) i] = (idx >= 0 && idx < (long long) n) ? src[(size_t) idx] : (R) 0;
        }
        long long bt = (long long) (cfg.block_taper_ms * 0.001 * cfg.in_rate);
        if (bt < 1) bt = 1;
        if (bt > T) bt = T;
        convert_block<R>(block.data(), P, r, P, 1, (int) bt, cfg.taper_shape, cfg.phase,
                         cfg.in_rate, cfg.rolloff_hz, cfg.roll_order, conv);

        const long long o0 = start * r.L / r.M;
        const long long cnt = std::min<long long>(hi - lo, out_total - o0);
        for (long long i = 0; i < cnt; ++i) out[(size_t) (o0 + i)] = conv[(size_t) (lo + i)];
    };

    if (nworkers == 1) {
        std::vector<R> block((size_t) P), conv;
        for (long long bi = 0; bi < nblocks; ++bi) do_block(bi, block, conv);
    } else {
        std::atomic<long long> next(0);
        std::vector<std::thread> pool;
        pool.reserve((size_t) nworkers);
        for (long long w = 0; w < nworkers; ++w) {
            pool.emplace_back([&]() {
                std::vector<R> block((size_t) P), conv;
                for (;;) {
                    const long long bi = next.fetch_add(1);
                    if (bi >= nblocks) break;
                    do_block(bi, block, conv);
                }
            });
        }
        for (auto& t : pool) t.join();
    }

    return out;
}

}  // namespace

std::vector<double> resample_channel(const double* x, size_t n, const Cfg& cfg,
                                     const Ratio& r) {
    if (cfg.precision == 1) {
        std::vector<long double> t((size_t) n);
        for (size_t i = 0; i < n; ++i) t[i] = (long double) x[i];
        std::vector<long double> y = resample_typed<long double>(t.data(), n, cfg, r);
        std::vector<double> d(y.size());
        for (size_t i = 0; i < y.size(); ++i) d[i] = (double) y[i];
        return d;
    }
    return resample_typed<double>(x, n, cfg, r);
}

std::vector<long double> resample_channel_ld(const long double* x, size_t n, const Cfg& cfg,
                                             const Ratio& r) {
    return resample_typed<long double>(x, n, cfg, r);
}

// ------------------------------------------------------------------
// Quantisation with error-feedback noise shaping.
//
// TPDF dither keeps the error white and signal-independent; the feedback
// filter (1 - z^-1)^order then moves that error out of the band the ear is
// most sensitive to, at the cost of more noise near Nyquist.
// ------------------------------------------------------------------
namespace {
double rnd_uniform() {
    static thread_local uint64_t s = 0x9E3779B97F4A7C15ull;
    s ^= s << 13;
    s ^= s >> 7;
    s ^= s << 17;
    return (double) (s >> 11) * (1.0 / 9007199254740992.0);
}

// Binomial coefficients of (1 - z^-1)^order, alternating sign.
std::vector<double> shaper_coeffs(int order) {
    std::vector<double> h((size_t) order + 1, 0.0);
    for (int i = 0; i <= order; ++i) {
        double c = 1.0;
        for (int j = 0; j < i; ++j) c *= (double) (order - j) / (double) (j + 1);
        h[(size_t) i] = (i % 2) ? -c : c;
    }
    return h;
}
}  // namespace

std::vector<int32_t> quantise(const std::vector<double>& y, int channels, int bits,
                              int noise_shape, double in_rate) {
    (void) in_rate;
    // noise_shape carries the feedback order directly (0 = off, 4 = classic
    // 4th-order shaper). Clamp so a stray value cannot destabilise the loop.
    const int order = noise_shape > 0 ? std::min(noise_shape, 8) : 0;
    const double full = std::ldexp(1.0, bits - 1);
    const double lsb = 1.0 / full;
    const double maxv = full - 1.0;
    std::vector<int32_t> out(y.size());
    const std::vector<double> h = shaper_coeffs(order);

    const size_t frames = y.size() / (size_t) std::max(1, channels);
    std::vector<std::vector<double>> hist(
        (size_t) channels, std::vector<double>((size_t) order + 1, 0.0));

    for (size_t f = 0; f < frames; ++f) {
        for (int c = 0; c < channels; ++c) {
            const double v = y[f * (size_t) channels + (size_t) c];
            // Error feedback: NTF(z) = (1 - z^-1)^order, so the value handed to
            // the quantiser is x minus the filtered past error. Subtracting (not
            // adding) is what turns the error into a high-pass; adding gives a
            // low-pass and actually increases in-band noise.
            double shaped = v;
            if (order > 0)
                for (int i = 1; i <= order; ++i) shaped -= h[(size_t) i] * hist[(size_t) c][(size_t) i];
            const double d = (rnd_uniform() - rnd_uniform()) * lsb;  // TPDF
            double q = std::floor(shaped * full + d + 0.5);
            if (q > maxv) q = maxv;
            if (q < -full) q = -full;
            if (order > 0) {
                const double err = shaped - q / full;
                for (int i = order; i > 1; --i)
                    hist[(size_t) c][(size_t) i] = hist[(size_t) c][(size_t) i - 1];
                hist[(size_t) c][1] = err;
            }
            out[f * (size_t) channels + (size_t) c] = (int32_t) q;
        }
    }
    return out;
}

// ------------------------------------------------------------------
// Sigma-delta modulation to 1 bit.
//
// A p-th order error-feedback modulator with NTF = (1 - z^-1)^p. In-band
// error is tiny; the cost is huge ultrasonic noise, which is exactly what
// DSD is. Input must already be at the DSD rate.
// ------------------------------------------------------------------
std::vector<uint8_t> to_dsd(const std::vector<double>& y, int channels, int dsd_mult,
                            double in_rate, int order) {
    (void) dsd_mult;
    (void) in_rate;
    const int p = order > 0 ? order : 5;
    const std::vector<double> h = shaper_coeffs(p);

    const size_t frames = y.size() / (size_t) std::max(1, channels);
    const size_t bytes_per_ch = (frames + 7) / 8;
    std::vector<uint8_t> out(bytes_per_ch * (size_t) channels, 0);
    std::vector<std::vector<double>> hist(
        (size_t) channels, std::vector<double>((size_t) p + 1, 0.0));

    for (size_t f = 0; f < frames; ++f) {
        for (int c = 0; c < channels; ++c) {
            double v = y[f * (size_t) channels + (size_t) c];
            if (v > 0.999) v = 0.999;
            if (v < -0.999) v = -0.999;
            for (int i = 1; i <= p; ++i) v -= h[(size_t) i] * hist[(size_t) c][(size_t) i];
            if (v > 4.0) v = 4.0;
            if (v < -4.0) v = -4.0;
            const int bit = v >= 0.0 ? 1 : 0;
            const double q = bit ? 1.0 : -1.0;
            for (int i = p; i > 1; --i)
                hist[(size_t) c][(size_t) i] = hist[(size_t) c][(size_t) i - 1];
            hist[(size_t) c][1] = v - q;
            if (bit) out[(size_t) c * bytes_per_ch + f / 8] |= (uint8_t) (1u << (f % 8));
        }
    }
    return out;
}

}  // namespace dpggb