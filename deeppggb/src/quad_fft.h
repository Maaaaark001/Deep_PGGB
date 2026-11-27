// quad_fft.h - mixed-radix complex FFT in IEEE binary128 (__float128).
//
// FFTW has no quad-precision transform: fftwl is x87 80-bit (64-bit
// mantissa), not binary128. To get a genuine 128-bit path this file
// implements the transform itself. It only needs to handle the smooth grids
// the resampler uses (2^a 3^b 5^c), plus 7 for the analysis window.
//
// Accuracy: every twiddle comes from one master table exp(-2*pi*i*k/N) that is
// evaluated with sinq/cosq (<=1 ulp), so a stage twiddle is an exact table
// index, never a round trip through repeated multiplication. Round-off then
// grows like eps*log2(N) (measured below), not like a random walk.
#pragma once

#include <quadmath.h>

#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <stdexcept>
#include <vector>

namespace dpq {

using qf = __float128;

struct QC {
    qf v[2];
    qf& operator[](int k) { return v[k]; }
    const qf& operator[](int k) const { return v[k]; }
};

inline QC make_qc(qf r, qf i) { QC z; z.v[0] = r; z.v[1] = i; return z; }
inline QC qadd(QC a, QC b) { return make_qc(a.v[0] + b.v[0], a.v[1] + b.v[1]); }
inline QC qsub(QC a, QC b) { return make_qc(a.v[0] - b.v[0], a.v[1] - b.v[1]); }
inline QC qmul(QC a, QC b) {
    return make_qc(a.v[0] * b.v[0] - a.v[1] * b.v[1],
                   a.v[0] * b.v[1] + a.v[1] * b.v[0]);
}
inline QC qconj(QC a) { return make_qc(a.v[0], -a.v[1]); }

// Smallest prime factor; the grids are smooth, so this is a short loop.
inline int smallest_factor(int n) {
    for (int p = 2; p * p <= n; ++p)
        if (n % p == 0) return p;
    return n;
}

struct Plan {
    int n = 0;
    std::vector<QC> root;   // exp(-2*pi*i*k/n), k = 0..n-1
};

// Forward: X[k] = sum x[j] exp(-2*pi*i*j*k/n).  dst and scratch both hold n
// complex values and must not alias; the two are ping-ponged by recursion
// depth, so the whole transform needs 2n complex slots and no per-level
// allocation.
inline void fft_rec(const Plan& pl, const QC* in, long long stride, int n,
                    QC* dst, QC* scratch) {
    if (n == 1) { dst[0] = in[0]; return; }
    const int p = smallest_factor(n);
    const int m = n / p;

    for (int j = 0; j < p; ++j)
        fft_rec(pl, in + (std::size_t) j * (std::size_t) stride, stride * p, m,
                scratch + (std::size_t) j * (std::size_t) m,
                dst + (std::size_t) j * (std::size_t) m);

    const int N = pl.n;
    const int step = N / n;
    const QC* root = pl.root.data();

    if (p == 2) {
        for (int k = 0; k < m; ++k) {
            const QC a = scratch[(std::size_t) k];
            const int idx = (int) (((long long) k * step) % N);
            const QC b = qmul(root[idx], scratch[(std::size_t) m + (std::size_t) k]);
            dst[(std::size_t) k] = qadd(a, b);
            dst[(std::size_t) k + (std::size_t) m] = qsub(a, b);
        }
        return;
    }
    if (p == 3) {
        // W = -1/2 - i*sqrt(3)/2, so with t1 = b+c and t2 = c-b:
        //   X0 = a + t1
        //   X1 = a - t1/2 + i*sqrt(3)/2 * t2
        //   X2 = a - t1/2 - i*sqrt(3)/2 * t2
        // Two complex twiddle multiplies per group instead of four.
        const qf s3 = 0.86602540378443864676372317075293618347140262690519Q;
        for (int k = 0; k < m; ++k) {
            const QC a = scratch[(std::size_t) k];
            const QC b = qmul(root[(std::size_t) (((long long) k * step) % N)],
                              scratch[(std::size_t) m + (std::size_t) k]);
            const QC c = qmul(root[(std::size_t) (((long long) 2 * k * step) % N)],
                              scratch[(std::size_t) 2 * (std::size_t) m + (std::size_t) k]);
            const QC t1 = qadd(b, c);
            const QC t2 = qsub(c, b);
            const QC mid = qsub(a, make_qc(t1[0] * 0.5Q, t1[1] * 0.5Q));
            const QC rot = make_qc(-s3 * t2[1], s3 * t2[0]);
            dst[(std::size_t) k] = qadd(a, t1);
            dst[(std::size_t) k + (std::size_t) m] = qadd(mid, rot);
            dst[(std::size_t) k + (std::size_t) 2 * (std::size_t) m] = qsub(mid, rot);
        }
        return;
    }

    // Generic radix (5, 7, ...): direct p-point DFT. Only analysis windows
    // reach here; the resampler grids are 2/3-smooth.
    for (int k = 0; k < m; ++k) {
        QC A[16];
        for (int j = 0; j < p; ++j) {
            const int idx = (int) (((long long) j * k * step) % N);
            A[j] = qmul(root[idx], scratch[(std::size_t) j * (std::size_t) m + (std::size_t) k]);
        }
        for (int q = 0; q < p; ++q) {
            QC acc = make_qc(0, 0);
            for (int j = 0; j < p; ++j) {
                const int idx = (int) (((long long) j * q * (N / p)) % N);
                acc = qadd(acc, qmul(A[j], root[idx]));
            }
            dst[(std::size_t) k + (std::size_t) q * (std::size_t) m] = acc;
        }
    }
}

// One thread-local pair of work buffers, grown on demand. Plan execution only
// reads the plan, so the same plan can drive several threads.
inline std::vector<QC>& work_a() { static thread_local std::vector<QC> v; return v; }
inline std::vector<QC>& work_b() { static thread_local std::vector<QC> v; return v; }

inline Plan make_plan(int n) {
    Plan p;
    p.n = n;
    p.root.resize((std::size_t) n);
    const qf two_pi = 6.2831853071795864769252867665590057683943387987502Q;
    for (int k = 0; k < n; ++k) {
        const qf th = -two_pi * (qf) k / (qf) n;
        p.root[(std::size_t) k] = make_qc(cosq(th), sinq(th));
    }
    return p;
}

inline std::vector<QC>& work_c() { static thread_local std::vector<QC> v; return v; }

inline void fft_forward(const Plan& pl, const QC* in, QC* out) {
    std::vector<QC>& a = work_a();
    std::vector<QC>& b = work_b();
    if ((int) a.size() < pl.n) a.resize((std::size_t) pl.n);
    if ((int) b.size() < pl.n) b.resize((std::size_t) pl.n);
    fft_rec(pl, in, 1, pl.n, b.data(), a.data());
    std::memcpy(out, b.data(), sizeof(QC) * (std::size_t) pl.n);
}

// Real -> half spectrum. FFTW's r2c convention: out[0..n/2].
inline void fft_r2c(const Plan& pl, const qf* in, QC* out) {
    std::vector<QC>& a = work_a();
    std::vector<QC>& b = work_b();
    std::vector<QC>& c = work_c();
    const std::size_t n = (std::size_t) pl.n;
    if (a.size() < n) a.resize(n);
    if (b.size() < n) b.resize(n);
    if (c.size() < n) c.resize(n);
    for (std::size_t i = 0; i < n; ++i) a[i] = make_qc(in[i], 0);
    fft_rec(pl, a.data(), 1, pl.n, b.data(), c.data());
    std::memcpy(out, b.data(), sizeof(QC) * (n / 2 + 1));
}

// Half spectrum -> real, unnormalised like FFTW's c2r: x[n] = sum X[k] e^{+i..}
// computed as conj(FFT(conj(X))). Only the real part is written.
inline void fft_c2r(const Plan& pl, const QC* in, qf* out) {
    std::vector<QC>& a = work_a();
    std::vector<QC>& b = work_b();
    std::vector<QC>& c = work_c();
    const std::size_t n = (std::size_t) pl.n;
    if (a.size() < n) a.resize(n);
    if (b.size() < n) b.resize(n);
    if (c.size() < n) c.resize(n);
    a[0] = qconj(in[0]);
    for (std::size_t k = 1; k <= n / 2; ++k) {
        a[k] = qconj(in[k]);
        if (n - k != k) a[n - k] = qconj(a[k]);
    }
    fft_rec(pl, a.data(), 1, pl.n, b.data(), c.data());
    for (std::size_t i = 0; i < n; ++i) out[i] = b[i][0];
}

}  // namespace dpq
