// dpggb.h - Deep_PGGB: arbitrary-ratio ideal-brickwall FFT sample-rate converter
#pragma once
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace dpggb {

// Taper shapes. Values 4/5/6 are smootherstep of that order (value and the
// first N derivatives vanish at both ends); TAPER_SMOOTH is the legacy order-2
// form, kept so old configurations reproduce bit-for-bit.
//
// The order is not cosmetic. The fade window is a multiplier, so it convolves
// the spectrum with its own transform: a tone 4 kHz below Nyquist gets a
// sidelobe landing exactly on Nyquist, and that sidelobe is what the output
// reference does not have. Measured on a 15 kHz tone (44.1 -> 176.4, 4 s), the
// level deposited at 22.05 kHz is -272 dB for order 2 and -360 dB for order 5,
// which is the difference between a 250 dB and a 303 dB null.
enum TaperShape { TAPER_NONE = 0, TAPER_COS = 1, TAPER_SMOOTH = 2, TAPER_BLACKMAN = 3,
                  TAPER_SMOOTH4 = 4, TAPER_SMOOTH5 = 5, TAPER_SMOOTH6 = 6,
                  TAPER_SMOOTH7 = 7, TAPER_SMOOTH8 = 8, TAPER_SMOOTH10 = 10,
                  TAPER_SMOOTH12 = 12, TAPER_SMOOTH16 = 16, TAPER_SMOOTH20 = 20 };
enum PhaseMode { PHASE_LINEAR = 0, PHASE_MIN = 1 };

// Name -> order for the command line and the DLL option string. The fallback is
// smooth12, matching Cfg, so an unknown name lands on the measured default
// instead of the legacy order 5 (which costs 225 dB on the quad path).
inline int taper_from_name(const std::string& s) {
    if (s == "none") return TAPER_NONE;
    if (s == "cos") return TAPER_COS;
    if (s == "blackman") return TAPER_BLACKMAN;
    if (s == "smooth2") return TAPER_SMOOTH;
    if (s == "smooth4") return TAPER_SMOOTH4;
    if (s == "smooth5") return TAPER_SMOOTH5;
    if (s == "smooth6") return TAPER_SMOOTH6;
    if (s == "smooth7") return TAPER_SMOOTH7;
    if (s == "smooth8") return TAPER_SMOOTH8;
    if (s == "smooth10") return TAPER_SMOOTH10;
    if (s == "smooth16") return TAPER_SMOOTH16;
    if (s == "smooth20") return TAPER_SMOOTH20;
    return TAPER_SMOOTH12;   // "smooth", "smooth12", anything unrecognised
}
enum NoiseShape { NS_NONE = 0, NS_SHIBATA = 1 };

struct Cfg {
    double in_rate = 44100.0;
    double out_rate = 48000.0;
    int channels = 1;
    // 16 s: files this long or shorter are processed in one transform, so there is
    // no block seam at all (the seam costs ~10 dB on the SMPTE sidebands for a 4 s
    // block). It is also the fastest setting measured on a 60 s stereo file
    // (81x realtime vs 73x at 8 s and 57x for r8brain-free): fewer, larger blocks
    // waste less on the context and the FFT grid is still cache-friendly.
    double block_sec = 16.0;   // 0 = whole file
    double mem_mb = 1024.0;    // budget used for automatic block sizing
    double taper_ms = 20.0;    // edge fade only: 20 ms saturates the boundary error
    // Edge fade override, in ms; 0 keeps taper_ms. Only the file's first and
    // last samples are faded, so this costs nothing elsewhere -- but the fade is
    // a real edit of the signal (a 480 ms fade-in on music is audible), which is
    // why it is opt-in rather than the default.
    //
    // Why it exists: the fade is a multiplier, so its spectrum is convolved with
    // the signal's. A tone f close to Nyquist has little room below fs/2, and the
    // fade's modulation sidelobes land right there, inside the output band. The
    // fix is a fade long compared with 1/(fs/2 - f). Measured at 16 s,
    // 44.1 -> 88.2, binary128 (null mode, whole-file block): a 19 kHz tone reads
    // 450.8 dB at 20 ms, 582.1 at 60, 654.8 at 120, 665.7 at 240, 666.1 at 480;
    // 21 kHz needs 480-620 ms (310.4 -> 666.2); 15 kHz is already there at 120
    // (548.4 -> 665.6). One law fits the whole sweep, fade_ms ~= 650000 /
    // (0.5*min(fs_in,fs_out) - f), capped at 900 ms; it holds 665-666.5 dB from
    // 20 Hz to 21 kHz.
    double edge_taper_ms = 0.0;
    // Block context has two jobs: give the block's spectral surgery room to
    // settle at the join, and let the near-Nyquist response decay. 400 ms was
    // enough for the seam alone, but the upsampling image band (42.6-44.1 kHz
    // when going 44.1 -> 88.2) only reaches the float64 floor at 800 ms:
    // measured -314.8 dBc at 400 ms, -320.9 at 600, -322.1 at 800, against
    // PGGB's -322.6. It also buys 16 dB at 22.05 kHz on the way down
    // (-195.1 -> -211.2) and costs ~21% throughput, which still leaves 4.5x
    // over PGGB.
    double context_ms = 800.0;
    double mp_taps_ms = 50.0;  // min-phase FIR length = 4 x this
    // Transition band, in Hz below the output Nyquist. A true zero-width brick
    // wall has nowhere for the window's own spectral spread to go: a tone 50 Hz
    // above Nyquist has sidelobes that fall INSIDE the passband and survive
    // untouched, so it measured -103 dB while sox_ng read -198 dB. Spending
    // 25 Hz of transition buys 86 dB there and costs nothing measurable at
    // 22.0 kHz; 0 restores the exact brick wall.
    double rolloff_hz = 200.0;
    int roll_order = 2;
    // Length of the taper applied at each block edge, independent of the
    // context. A short taper removes the block-edge step (that is all it has to
    // do) while putting its modulation sidebands far from the carrier; a long
    // one spreads them into the transition band where a near-Nyquist tone
    // survives. Context stays long so the response has room to decay.
    double block_taper_ms = 20.0;
    // Order 12, not 5. The taper is a multiplier, so its own spectrum is
    // convolved with the signal: a low order leaves sidelobes that land inside
    // the output band and cap the null. Measured at 16 s, 1 kHz, 44.1 -> 88.2,
    // binary128, with the 20 ms lengths unchanged: order 5 gives 440.2 dB,
    // order 6 451.2, 7 516.5, 8 528.4, 10 601.7, 12 665.3, and 665-666 is the
    // round-trip ceiling of the quad transform itself. Order 12 also lifts a
    // 19 kHz tone in float64 from 293.3 to 306.5 dB, i.e. onto the float64
    // floor, so this is not a quad-only setting.
    int taper_shape = TAPER_SMOOTH12;
    // 0 = double, 1 = long double (x87 80-bit on this toolchain, 64-bit
    // mantissa), 2 = quad (IEEE binary128, 113-bit mantissa). "long double"
    // is NOT binary128 on Windows: sizeof is 16 but only 64 bits are used.
    int precision = 0;
    int phase = PHASE_LINEAR;
    int threads = 0;           // 0 = auto (FFTW threads inside one transform)
    int workers = 0;           // 0 = auto (blocks processed concurrently)
    int bits = 64;             // 64/32 float, 24/16 integer
    int noise_shape = NS_NONE;
    int dsd = 0;               // 0, 64, 128, 256
    double gain_db = 0.0;
    bool quiet = false;
    // min-phase smoothing: transition width in bins of the design grid
    double minphase_bins = 2.0;
};

// Exact rational ratio L/M reduced, plus the FFT grid sizes.
struct Ratio {
    long long L = 1;   // up factor
    long long M = 1;   // down factor
};

Ratio reduce_ratio(double in_rate, double out_rate);

// Resample one channel of float64 samples. Returns the resampled channel.
std::vector<double> resample_channel(const double* x, size_t n, const Cfg& cfg,
                                     const Ratio& r);
std::vector<long double> resample_channel_ld(const long double* x, size_t n, const Cfg& cfg,
                                             const Ratio& r);
#ifdef DPGGB_QUAD
// IEEE binary128 path. FFTW has no quad transform, so this uses the
// mixed-radix __float128 FFT in quad_fft.h. Input and output are quad, which
// is the only way the arithmetic floor can sit below the float64 one.
std::vector<__float128> resample_channel_q(const __float128* x, size_t n, const Cfg& cfg,
                                           const Ratio& r);
#endif

// Quantise float64 to integer PCM with optional error-feedback noise shaping.
// Returns interleaved integer samples as int32 (value already scaled to the target depth).
std::vector<int32_t> quantise(const std::vector<double>& y, int channels, int bits,
                              int noise_shape, double in_rate);

// 1-bit sigma-delta modulation at the given DSD multiple (64/128/256 -> 2.8224 MHz * n/64).
// Returns packed bytes, LSB first, per channel.
std::vector<uint8_t> to_dsd(const std::vector<double>& y, int channels, int dsd_mult,
                            double in_rate, int order);

}  // namespace dpggb
