"""
AIM Executor — manages a pool of locally registered tasks and runs them.

The Executor is the compute workhorse inside a node.  It maintains a
priority queue of pending TaskItems, runs them concurrently up to
``max_concurrency``, and stores results for later retrieval.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


class TaskState(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    DONE      = "done"
    FAILED    = "failed"


@dataclass
class TaskItem:
    """A unit of work submitted to the Executor."""
    name:       str
    args:       dict[str, Any]
    task_id:    str            = field(default_factory=lambda: str(uuid.uuid4()))
    state:      TaskState      = TaskState.PENDING
    result:     Any            = None
    error:      str | None     = None
    created_at: float          = field(default_factory=time.time)
    started_at: float | None   = None
    ended_at:   float | None   = None
    creator:    str            = "Cbetts1"


TaskFn = Callable[[dict[str, Any]], Awaitable[Any]]


class Executor:
    """
    Async task executor with a local task function registry.

    Parameters
    ----------
    max_concurrency : maximum number of tasks running simultaneously
    """

    def __init__(self, max_concurrency: int = 8) -> None:
        self._functions: dict[str, TaskFn] = {}
        self._tasks: dict[str, TaskItem] = {}
        self._queue: asyncio.Queue[TaskItem] = asyncio.Queue()
        self._semaphore: asyncio.Semaphore | None = None
        self._max_concurrency = max_concurrency
        self._running = False

    # ------------------------------------------------------------------
    # Task function registry
    # ------------------------------------------------------------------

    def register(self, name: str, fn: TaskFn) -> None:
        """Register a coroutine function under *name*."""
        self._functions[name] = fn

    def task(self, name: str) -> Callable[[TaskFn], TaskFn]:
        """Decorator that registers a coroutine as a named task."""
        def decorator(fn: TaskFn) -> TaskFn:
            self.register(name, fn)
            return fn
        return decorator

    # ------------------------------------------------------------------
    # Submission
    # ------------------------------------------------------------------

    def submit(
        self,
        name: str,
        args: dict[str, Any] | None = None,
        creator: str = "Cbetts1",
    ) -> TaskItem:
        """Submit a task for execution; returns the TaskItem immediately."""
        item = TaskItem(name=name, args=args or {}, creator=creator)
        self._tasks[item.task_id] = item
        self._queue.put_nowait(item)
        return item

    async def submit_and_wait(
        self,
        name: str,
        args: dict[str, Any] | None = None,
        creator: str = "Cbetts1",
        poll_interval: float = 0.05,
        timeout: float = 30.0,
    ) -> TaskItem:
        """Submit a task and block until it completes (or times out)."""
        item = self.submit(name, args, creator)
        deadline = time.time() + timeout
        while item.state in (TaskState.PENDING, TaskState.RUNNING):
            if time.time() > deadline:
                raise asyncio.TimeoutError(f"Task {item.task_id} timed out")
            await asyncio.sleep(poll_interval)
        return item

    # ------------------------------------------------------------------
    # Result lookup
    # ------------------------------------------------------------------

    def get_task(self, task_id: str) -> TaskItem | None:
        return self._tasks.get(task_id)

    def all_tasks(self) -> list[TaskItem]:
        return list(self._tasks.values())

    # ------------------------------------------------------------------
    # Execution loop
    # ------------------------------------------------------------------

    async def _run_task(self, item: TaskItem) -> None:
        if self._semaphore is None:
            raise RuntimeError("Executor must be started before running tasks")
        async with self._semaphore:
            fn = self._functions.get(item.name)
            item.state = TaskState.RUNNING
            item.started_at = time.time()
            if fn is None:
                item.state = TaskState.FAILED
                item.error = f"Unknown task: {item.name!r}"
                item.ended_at = time.time()
                logger.warning("Unknown task %r submitted to executor", item.name)
                return
            try:
                item.result = await fn(item.args)
                item.state = TaskState.DONE
            except Exception as exc:
                item.state = TaskState.FAILED
                item.error = str(exc)
                logger.exception("Task %s (%s) failed", item.name, item.task_id)
            finally:
                item.ended_at = time.time()

    async def _worker(self) -> None:
        while self._running:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            asyncio.create_task(self._run_task(item))
            self._queue.task_done()

    async def start(self) -> None:
        """Start the executor worker loop."""
        self._semaphore = asyncio.Semaphore(self._max_concurrency)
        self._running = True
        asyncio.create_task(self._worker())
        logger.debug("Executor started (max_concurrency=%d)", self._max_concurrency)

    async def stop(self) -> None:
        """Stop the executor after draining the queue."""
        self._running = False
        try:
            await asyncio.wait_for(self._queue.join(), timeout=10.0)
        except asyncio.TimeoutError:
            pass
        logger.debug("Executor stopped")
