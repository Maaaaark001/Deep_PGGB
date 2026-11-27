#!/usr/bin/env bash
# Build the IEEE binary128 front end. The normal build.sh deliberately does not
# define DPGGB_QUAD, so dpggb.dll keeps its existing FFTW-only dependency set.
set -euo pipefail
cd "$(dirname "$0")"

CXX=${CXX:-g++}
INC="third_party/include"
LIB="third_party/lib"
COMMON=(-O3 -std=c++20 -DDPGGB_QUAD -fext-numeric-literals -I"$INC")
LIBS=(-L"$LIB" -lfftw3 -lfftw3_threads -lfftw3l -lfftw3l_threads
      -lquadmath -static-libgcc -static-libstdc++ -lwinpthread)

"$CXX" "${COMMON[@]}" -o dpggb128.exe src/dpggb_q_cli.cpp src/dpggb_core.cpp "${LIBS[@]}"
"$CXX" "${COMMON[@]}" -I. -o dp_quad_probe.exe dp_quad_probe.cpp src/dpggb_core.cpp "${LIBS[@]}"
echo "built dpggb128.exe dp_quad_probe.exe"
