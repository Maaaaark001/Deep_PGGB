#include <fftw3.h>
#include <cmath>
#include <cstdio>
#include <vector>

static void design_linear(std::vector<double>& h, int L, double fc) {
    // windowed-sinc low-pass, fc normalised to Nyquist, odd length for symmetry
    h.assign((size_t) L, 0.0);
    const int c = L / 2;
    for (int i = 0; i < L; ++i) {
        const double d = (double) (i - c);
        const double s = (d == 0.0) ? fc : std::sin(M_PI * fc * d) / (M_PI * d);
        const double w = 0.42 - 0.5 * std::cos(2 * M_PI * i / (L - 1))
                       + 0.08 * std::cos(4 * M_PI * i / (L - 1));
        h[(size_t) i] = s * w;
    }
    double sum = 0;
    for (double v : h) sum += v;
    for (double& v : h) v /= sum;
}

static void to_minphase(const std::vector<double>& lin, std::vector<double>& out) {
    const int L = (int) lin.size();
    int n = 1;
    while (n < 8 * L) n <<= 1;
    const int nc = n / 2 + 1;

    double* in = (double*) fftw_malloc(sizeof(double) * n);
    fftw_complex* spec = (fftw_complex*) fftw_malloc(sizeof(fftw_complex) * nc);
    fftw_plan fwd = fftw_plan_dft_r2c_1d(n, in, spec, FFTW_ESTIMATE);

    for (int i = 0; i < n; ++i) in[i] = 0;
    for (int i = 0; i < L; ++i) in[i] = lin[(size_t) i];
    fftw_execute(fwd);

    // log magnitude of the linear-phase response
    std::vector<double> logmag((size_t) nc);
    for (int i = 0; i < nc; ++i) {
        const double m = std::hypot(spec[i][0], spec[i][1]);
        logmag[(size_t) i] = std::log(std::fmax(m, 1e-12));
    }
    for (int i = 0; i < n; ++i) in[i] = 0;
    for (int i = 0; i < nc; ++i) in[i] = logmag[(size_t) i];
    for (int i = 1; i < n - nc + 1; ++i) in[n - i] = in[i];
    fftw_execute(fwd);

    std::vector<double> cep((size_t) n, 0.0);
    for (int i = 0; i < nc; ++i) cep[(size_t) i] = spec[i][0] / n;
    for (int i = 1; i < n - nc + 1; ++i) cep[(size_t) (n - i)] = cep[(size_t) i];
    for (int i = 1; i < n / 2; ++i) cep[(size_t) i] *= 2.0;
    for (int i = n / 2 + 1; i < n; ++i) cep[(size_t) i] = 0.0;

    for (int i = 0; i < n; ++i) in[i] = cep[(size_t) i];
    fftw_execute(fwd);

    // min-phase spectrum = exp(cepstrum spectrum); its inverse transform is
    // causal. Recover the impulse response with an explicit inverse FFT.
    double* outbuf = (double*) fftw_malloc(sizeof(double) * n);
    fftw_plan inv = fftw_plan_dft_c2r_1d(n, spec, outbuf, FFTW_ESTIMATE);
    for (int i = 0; i < nc; ++i) {
        const double a = spec[i][0], b = spec[i][1];
        const double m = std::exp(a);
        spec[i][0] = m * std::cos(b);
        spec[i][1] = m * std::sin(b);
    }
    fftw_execute(inv);
    out.assign((size_t) L, 0.0);
    for (int i = 0; i < L; ++i) out[(size_t) i] = outbuf[i] / n;

    fftw_destroy_plan(fwd);
    fftw_destroy_plan(inv);
    fftw_free(in);
    fftw_free(spec);
    fftw_free(outbuf);
}

int main() {
    std::vector<double> lin, mp;
    const int L = 1023;
    design_linear(lin, L, 0.95);
    to_minphase(lin, mp);

    double e_lin = 0, e_mp = 0, dc = 0;
    int peak_at = 0;
    double peak = 0;
    for (int i = 0; i < L; ++i) {
        e_lin += lin[(size_t) i] * lin[(size_t) i];
        e_mp += mp[(size_t) i] * mp[(size_t) i];
        dc += mp[(size_t) i];
        if (std::fabs(mp[(size_t) i]) > peak) { peak = std::fabs(mp[(size_t) i]); peak_at = i; }
    }
    printf("linear energy %.6f  minphase energy %.6f  ratio %.4f\n", e_lin, e_mp, e_mp / e_lin);
    printf("minphase DC gain %.6f  peak at tap %d of %d\n", dc, peak_at, L);
    printf("first 5 taps: %.6f %.6f %.6f %.6f %.6f\n", mp[0], mp[1], mp[2], mp[3], mp[4]);
    printf("taps 500-504: %.3e %.3e %.3e %.3e %.3e\n", mp[500], mp[501], mp[502], mp[503], mp[504]);
    return 0;
}
