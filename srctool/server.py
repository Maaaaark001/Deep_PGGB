"""FastAPI 应用装配。

为什么用 ui.run_with 而不是 ui.run：
  我们需要自己控制 uvicorn（端口、日志、以及 /files 静态目录），
  并且要把"下载输出文件"挂在同一个 app 上，避免再起一个服务。
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from nicegui import ui
from starlette.staticfiles import StaticFiles

from . import config
from .ui import pages, theme

# 整页拖放上传的落地目录（与 pages.UPLOAD_DIR 保持一致）
UPLOAD_DIR = config.WORK / "uploads"
_SAFE = re.compile(r"[^\w.\-()\[\] ]+")


def create_app() -> FastAPI:
    config.ensure_dirs()
    app = FastAPI(title=config.APP_TITLE, docs_url=None, redoc_url=None)

    # 输出文件下载：直接把 work/ 挂出去
    config.WORK.mkdir(parents=True, exist_ok=True)
    app.mount("/files", StaticFiles(directory=str(config.WORK)), name="files")

    @app.get("/healthz")
    def _health() -> dict:
        return {"ok": True, "app": config.APP_NAME, "version": config.APP_VERSION,
                "env": config.env_report()}

    @app.post("/api/upload")
    async def _upload(file: UploadFile = File(...)) -> dict:
        """浏览器整页拖放的落地端点。

        Quasar 的 q-uploader 只认它自己那块标题栏，页面其它位置的 drop
        事件只能自己接：前端把 File 塞进 FormData POST 到这里，
        落盘后返回绝对路径，再经 emitEvent 送回 NiceGUI 页面。
        """
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        name = Path(file.filename or "audio").name
        safe = _SAFE.sub("_", name).strip() or "audio"
        dest = UPLOAD_DIR / f"{int(time.time())}_{safe}"
        size = 0
        with dest.open("wb") as fh:
            while True:
                buf = await file.read(1 << 20)
                if not buf:
                    break
                size += len(buf)
                if size > 4 * 1024**3:
                    fh.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(413, "文件超过 4 GB")
                fh.write(buf)
        return {"ok": True, "path": str(dest), "name": safe, "bytes": size}

    @app.get("/favicon.ico")
    def _favicon() -> RedirectResponse:
        return RedirectResponse("/")

    ui.run_with(
        app,
        storage_secret="sonarsrc-local-only",
        title=config.APP_TITLE,
        favicon="🎚️",
        dark=theme.dark_enabled(),
        binding_refresh_interval=0.15,
    )
    # 导入页面模块即完成 @ui.page 注册
    _ = pages
    return app
