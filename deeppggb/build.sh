#!/usr/bin/env bash
# Build dpggb.dll and dpggb.exe with the MSYS2 UCRT64 toolchain.
# The FFTW import libraries and headers live in deeppggb/third_party (ignored
# by git because they are large); install them there or edit INC/LIB.
set -euo pipefail
cd "$(dirname "$0")"

CXX=${CXX:-g++}
INC="third_party/include"
LIB="third_party/lib"
# -O3 and nothing more: the core spends ~75% of a block inside the FFTW DLL,
# so -Ofast / -march=native move nothing here. Measured on 60 s stereo
# 44.1->88.2 (best of 5, interleaved): -O3 129x, -Ofast 126x, -O3 -march=native
# 123x, -Ofast -march=native 132x -- all inside the +/-5% run-to-run spread.
# Keep -O3 so the binary stays portable to any x86-64 CPU.
COMMON=(-O3 -std=c++20 -I"$INC")
LIBS=(-L"$LIB" -lfftw3 -lfftw3_threads -lfftw3l -lfftw3l_threads
      -static-libgcc -static-libstdc++ -lwinpthread)

# C API: whole-file + native streaming FIFO.
"$CXX" "${COMMON[@]}" -shared -o dpggb.dll \
    src/dpggb_dll.cpp src/dpggb_core.cpp "${LIBS[@]}" \
    -Wl,--out-implib,dpggb.dll.a

# CLI: same core, file/pipe front end.
"$CXX" "${COMMON[@]}" -o dpggb.exe \
    src/dpggb_cli.cpp src/dpggb_core.cpp "${LIBS[@]}"

echo "built dpggb.dll dpggb.exe"
