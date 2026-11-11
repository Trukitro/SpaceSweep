"""Background jobs with progress reporting and cancellation.

The UI starts a job, gets its id back immediately and polls `snapshot()`
until the job finishes. Every long operation in SpaceSweep runs this way so
the window never freezes.
"""

import threading
import time
import traceback
import uuid


class Cancelled(Exception):
    """Raised inside a job when the user pressed Cancel."""


class Job:
    def __init__(self, kind):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.status = "running"  # running | done | error | cancelled
        self.message = ""
        self.current = ""
        self.progress = -1.0  # 0..1, or -1 when the total is unknown
        self.count = 0
        self.result = None
        self.error = None
        self.started = time.time()
        self.finished = None
        self._cancel = threading.Event()

    @property
    def cancelled(self):
        return self._cancel.is_set()

    def check(self):
        if self._cancel.is_set():
            raise Cancelled()

    def update(self, message=None, current=None, progress=None, count=None):
        if message is not None:
            self.message = message
        if current is not None:
            self.current = current
        if progress is not None:
            self.progress = progress
        if count is not None:
            self.count = count

    def snapshot(self):
        data = {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "message": self.message,
            "current": self.current,
            "progress": self.progress,
            "count": self.count,
            "elapsed": round((self.finished or time.time()) - self.started, 1),
            "error": self.error,
        }
        if self.status == "done":
            data["result"] = self.result
        return data


class JobManager:
    MAX_KEPT = 30

    def __init__(self):
        self._jobs = {}
        self._lock = threading.Lock()

    def start(self, kind, fn, *args, **kwargs):
        job = Job(kind)

        def runner():
            try:
                job.result = fn(job, *args, **kwargs)
                job.status = "cancelled" if job.cancelled else "done"
            except Cancelled:
                job.status = "cancelled"
            except Exception as exc:  # surfaced to the UI, never swallowed
                job.status = "error"
                job.error = f"{type(exc).__name__}: {exc}"
                traceback.print_exc()
            finally:
                job.finished = time.time()

        with self._lock:
            self._jobs[job.id] = job
            if len(self._jobs) > self.MAX_KEPT:
                for old_id in sorted(self._jobs, key=lambda k: self._jobs[k].started)[: -self.MAX_KEPT]:
                    if self._jobs[old_id].status != "running":
                        del self._jobs[old_id]
        threading.Thread(target=runner, name=f"job-{kind}", daemon=True).start()
        return job.id

    def get(self, job_id):
        job = self._jobs.get(job_id)
        return job.snapshot() if job else None

    def cancel(self, job_id):
        job = self._jobs.get(job_id)
        if job:
            job._cancel.set()
        return bool(job)
