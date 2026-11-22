"""SonarSRC 启动器。

    python app.py                # 默认 http://127.0.0.1:8080
    python app.py --port 9000 --host 0.0.0.0 --reload

首次启动会打印环境自检（ffmpeg / sox_ng / r8brain / ssrc 是否就位），
缺任何一个都只影响对应功能，不影响界面启动。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> None:
    ap = argparse.ArgumentParser(description="SonarSRC 多格式采样率工具箱")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--reload", action="store_true", help="开发模式：代码改动自动重载")
    args = ap.parse_args()

    import uvicorn

    from srctool import config
    from srctool.server import create_app

    env = config.env_report()
    print("=" * 62)
    print(f"  {config.APP_TITLE}   v{config.APP_VERSION}")
    print("=" * 62)
    for k, v in env.items():
        print(f"  {k:<10} {v}")
    print("-" * 62)
    print(f"  http://{args.host}:{args.port}")
    print("=" * 62)

    if args.reload:
        uvicorn.run("srctool.server:create_app", factory=True, host=args.host,
                    port=args.port, reload=True, log_level="info")
    else:
        uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
