"""Tests for the AIM Compute Layer."""

import asyncio
import pytest

from aim.compute.executor import Executor, TaskState


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------

class TestExecutor:
    @pytest.mark.asyncio
    async def test_register_and_run_task(self):
        ex = Executor()
        await ex.start()

        @ex.task("add")
        async def add(args):
            return args["a"] + args["b"]

        item = await ex.submit_and_wait("add", {"a": 3, "b": 4}, timeout=5.0)
        assert item.state == TaskState.DONE
        assert item.result == 7
        await ex.stop()

    @pytest.mark.asyncio
    async def test_unknown_task_fails(self):
        ex = Executor()
        await ex.start()
        item = await ex.submit_and_wait("missing_task", {}, timeout=5.0)
        assert item.state == TaskState.FAILED
        assert "Unknown task" in (item.error or "")
        await ex.stop()

    @pytest.mark.asyncio
    async def test_task_exception_captured(self):
        ex = Executor()
        await ex.start()

        @ex.task("boom")
        async def boom(args):
            raise ValueError("deliberate error")

        item = await ex.submit_and_wait("boom", {}, timeout=5.0)
        assert item.state == TaskState.FAILED
        assert "deliberate error" in (item.error or "")
        await ex.stop()

    @pytest.mark.asyncio
    async def test_multiple_concurrent_tasks(self):
        ex = Executor(max_concurrency=4)
        await ex.start()

        @ex.task("square")
        async def square(args):
            await asyncio.sleep(0.01)
            return args["n"] ** 2

        items = [ex.submit("square", {"n": i}) for i in range(5)]
        # Wait for all
        deadline = asyncio.get_event_loop().time() + 10.0
        while any(i.state in (TaskState.PENDING, TaskState.RUNNING) for i in items):
            if asyncio.get_event_loop().time() > deadline:
                pytest.fail("Tasks did not complete in time")
            await asyncio.sleep(0.05)

        results = {i.args["n"]: i.result for i in items}
        assert results[3] == 9
        assert results[4] == 16
        await ex.stop()

    @pytest.mark.asyncio
    async def test_get_task_by_id(self):
        ex = Executor()
        await ex.start()

        @ex.task("noop")
        async def noop(args):
            return "done"

        item = await ex.submit_and_wait("noop", {}, timeout=5.0)
        fetched = ex.get_task(item.task_id)
        assert fetched is item
        await ex.stop()

    @pytest.mark.asyncio
    async def test_creator_signature_on_task(self):
        ex = Executor()
        await ex.start()

        @ex.task("sig_check")
        async def sig_check(args):
            return "ok"

        item = await ex.submit_and_wait("sig_check", {}, creator="Cbetts1", timeout=5.0)
        assert item.creator == "Cbetts1"
        assert item.state == TaskState.DONE
        await ex.stop()
