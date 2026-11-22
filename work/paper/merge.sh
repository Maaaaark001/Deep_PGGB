cd "C:/Users/Administrator/Documents/Python_Code/src/work/paper"
export PYTHONIOENCODING=utf-8
python - <<'PY'
import io
parts = ["build_paper_1.py", "build_paper_2.py", "build_paper_3.py"]
out = []
for f in parts:
    out.append(open(f, encoding="utf-8").read())
open("build_paper.py", "w", encoding="utf-8", newline="\n").write("\n".join(out))
print("merged")
PY
python build_paper.py
python -c "import json;b=json.load(open('blocks.json',encoding='utf-8'));print(len(b));print(sum(len(x.get('x','')) for x in b),'chars');print([k for k in set(x['t'] for x in b)])"