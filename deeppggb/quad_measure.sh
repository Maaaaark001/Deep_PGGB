#!/usr/bin/env bash
# One-shot measurement sweep for the binary128 build. All lines are JSON.
set -u
P=./dp_quad_probe.exe
echo '# null 16s mono 44.1->88.2, quad analysis'
for p in 0 1 2; do for f in 997 1000 5000 15000 17999; do
  $P null $p 16 $f 16 0 20 5 800 44100 88200 0.05
done; done
echo '# sinad 16s mono 1kHz'
for p in 0 1 2; do $P sinad $p 16 1000 16 0 20 5 800 44100 88200 0.05; done
echo '# speed 60s stereo block16 w0, 5 interleaved rounds'
for r in 1 2 3 4 5; do for p in 0 1 2; do $P speed $p 60 16 0; done; done
echo '# fft intrinsic'
$P fft
echo '# other ratios'
for p in 0 2; do
  $P null $p 16 1000 16 0 20 5 800 44100 48000 0.05
  $P null $p 16 1000 16 0 20 5 800 96000 44100 0.05
done
