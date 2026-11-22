"""任务队列：把耗时的转换/测量丢到后台线程，前端轮询进度。

只用标准库 threading + 一个内存字典，不引入任何依赖。
"""
from __future__ import annotations

import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Job:
    id: str
    kind: str
    title: str
    status: str = "queued"          # queued | running | done | error | cancelled
    progress: float = 0.0
    message: str = ""
    result: Any = None
    error: str | None = None
    created: float = field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None
    _cancel: bool = False

    @property
    def elapsed(self) -> float:
        if self.started is None:
            return 0.0
        end = self.finished or time.time()
        return end - self.started

    def to_dict(self) -> dict:
        return {
            "id": self.id, "kind": self.kind, "title": self.title,
            "status": self.status, "progress": round(self.progress, 4),
            "message": self.message, "error": self.error,
            "elapsed": round(self.elapsed, 2),
            "created": self.created,
        }


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def submit(self, kind: str, title: str,
               fn: Callable[[Job], Any]) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], kind=kind, title=title)
        with self._lock:
            self._jobs[job.id] = job
            self._prune()

        def _run() -> None:
            job.status = "running"
            job.started = time.time()
            try:
                job.result = fn(job)
                if job.status != "cancelled":
                    job.status = "done"
                    job.progress = 1.0
            except Exception as exc:  # noqa: BLE001
                job.status = "error"
                job.error = f"{type(exc).__name__}: {exc}"
                job.result = {"traceback": traceback.format_exc()[-2000:]}
            finally:
                job.finished = time.time()

        threading.Thread(target=_run, daemon=True, name=f"job-{job.id}").start()
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
        if job and job.status in ("queued", "running"):
            job._cancel = True
            job.status = "cancelled"
            return True
        return False

    def list(self, kind: str | None = None) -> list[Job]:
        with self._lock:
            items = list(self._jobs.values())
        if kind:
            items = [j for j in items if j.kind == kind]
        return sorted(items, key=lambda j: j.created, reverse=True)

    def _prune(self, keep: int = 40) -> None:
        if len(self._jobs) <= keep:
            return
        old = sorted(self._jobs.values(), key=lambda j: j.created)
        for j in old[: len(self._jobs) - keep]:
            if j.status in ("done", "error", "cancelled"):
                self._jobs.pop(j.id, None)


JOBS = JobManager()


def progress_reporter(job: Job) -> Callable[[float, str], None]:
    def _report(p: float, msg: str) -> None:
        job.progress = max(0.0, min(1.0, p))
        job.message = msg
        if job._cancel:
            raise RuntimeError("任务已取消")
    return _report
