"""Exact IEEE binary128 codec.

encode(mpf) rounds to 113 significant bits, round-half-to-even, returning 16
little-endian bytes.  decode(bytes) returns the *exact* dyadic value as an Arb
ball, because arb(int) * 2**k is exact in Arb.
"""
import struct
from mpmath import mpf, mp

EXP_BIAS = 16383
MANT_BITS = 112


def _round_to_bits(man, exp, bits):
    if man == 0:
        return 0, 0
    bl = man.bit_length()
    if bl > bits:
        shift = bl - bits
        q, r = divmod(man, 1 << shift)
        half = 1 << (shift - 1)
        if r > half or (r == half and (q & 1)):
            q += 1
        man, exp = q, exp + shift
        if man.bit_length() > bits:
            man >>= 1
            exp += 1
    elif bl < bits:
        shift = bits - bl
        man, exp = man << shift, exp - shift
    return man, exp


def encode(value):
    # mpf(value) rounds to mp.prec, and mpmath's default is 53 bits: without
    # raising it here, a 400-bit Arb sample is silently written as a 53-bit
    # value (a -320 dB floor that looks like a property of the data).
    with mp.workprec(max(mp.prec, 160)):
        v = value if isinstance(value, mpf) else mpf(value)
        return _encode_mpf(v)


def _encode_mpf(v):
    sign = 1 if v < 0 else 0
    a = -v if sign else v
    if a == 0:
        return b"\x00" * 16
    man, exp = a.man, a.exp
    man, exp = _round_to_bits(man, exp, MANT_BITS + 1)
    E = exp + MANT_BITS + EXP_BIAS
    if E >= 32767:
        return struct.pack("<Q", (sign << 63) | (32767 << 48)) + b"\x00" * 8
    if E <= 0:
        man >>= (1 - E)
        E = 0
    mant = man - (1 << MANT_BITS) if E > 0 else man
    high = (sign << 63) | (E << 48) | (mant >> 64)
    low = mant & ((1 << 64) - 1)
    # IEEE binary128 is a 128-bit big-endian field stored little-endian: the
    # sign/exponent word is the *last* eight bytes on disk.
    return struct.pack("<QQ", low, high)


def decode(raw):
    low, high = struct.unpack("<QQ", raw)
    sign = high >> 63
    E = (high >> 48) & 0x7FFF
    mant = ((high & ((1 << 48) - 1)) << 64) | low
    if E == 0:
        if mant == 0:
            return 0, 0
        m, e = mant, 1 - EXP_BIAS - MANT_BITS
    elif E == 0x7FFF:
        raise ValueError("inf/nan")
    else:
        m, e = (1 << MANT_BITS) | mant, E - EXP_BIAS - MANT_BITS
    return (-m if sign else m), e


def to_arb(raw):
    """Exact value as an Arb ball.  Call this at the working precision: the
    mantissa has 113 bits, so decoding under ctx.prec=53 rounds it and hands
    every later stage a 1e-16 floor."""
    from flint import arb
    m, e = decode(raw)
    if m == 0:
        return arb(0)
    return arb(m) * (arb(2) ** e)


def value_of(raw):
    m, e = decode(raw)
    return mpf(m) * mpf(2) ** e


def read_file(path, bits=None):
    """Decode a whole file.  `bits` raises ctx.prec for the decode, because a
    113-bit mantissa read at 53 bits is rounded (see to_arb)."""
    from flint import ctx
    data = open(path, "rb").read()
    if len(data) % 16:
        raise ValueError("file length not a multiple of 16 bytes")
    old = ctx.prec
    if bits:
        ctx.prec = bits
    try:
        return [to_arb(data[i:i + 16]) for i in range(0, len(data), 16)]
    finally:
        ctx.prec = old


def write_file(path, values):
    with open(path, "wb") as f:
        for v in values:
            f.write(encode(v))
