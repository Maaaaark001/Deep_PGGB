#!/usr/bin/env bash
# Build dpggb.dll and dpggb.exe with the MSYS2 UCRT64 toolchain.
# The FFTW import libraries and headers live in deeppggb/third_party (ignored
# by git because they are large); install them there or edit INC/LIB.
set -euo pipefail
cd "$(dirname "$0")"

CXX=${CXX:-g++}
INC="third_party/include"
LIB="third_party/lib"
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
