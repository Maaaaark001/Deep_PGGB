#!/usr/bin/env bash
# Rebuild the manuscript: blocks.json -> Univer doc -> docx with embedded figures.
set -e
cd "C:/Users/Administrator/Documents/Python_Code/src/work/paper"
export PYTHONIOENCODING=utf-8
python build_paper.py
echo "blocks.json rebuilt"
