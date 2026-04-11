"""Tests for the Meshara Virtual Node Layer."""

import asyncio
import pytest

from meshara.node.base import BaseNode
from meshara.node.agent import AgentNode, ReasoningEngine
from meshara.node.registry import NodeRegistry, NodeRecord
from meshara.protocol.message import MesharaMessage, Intent


# ---------------------------------------------------------------------------
# ReasoningEngine
# ---------------------------------------------------------------------------

class TestReasoningEngine:
    @pytest.mark.asyncio
    async def test_rule_match(self):
        engine = ReasoningEngine()
        engine.add_rule("hello", "Hi there!")
        result = await engine.reason("hello world", {})
        assert result == "Hi there!"

    @pytest.mark.asyncio
    async def test_no_match_returns_default(self):
        engine = ReasoningEngine()
        result = await engine.reason("unrecognised query", {})
        assert "unrecognised query" in result

    @pytest.mark.asyncio
    async def test_case_insensitive_match(self):
        engine = ReasoningEngine()
        engine.add_rule("meshara", "Meshara is the mesh.")
        result = await engine.reason("What is Meshara?", {})
        assert result == "Meshara is the mesh."


# ---------------------------------------------------------------------------
# NodeRegistry
# ---------------------------------------------------------------------------

class TestNodeRegistry:
    def setup_method(self):
        # Use isolated registry per test
        self.registry = NodeRegistry()

    def test_register_and_get(self):
        rec = NodeRecord("n1", "127.0.0.1", 7700, ["query"])
        self.registry.register(rec)
        assert self.registry.get("n1") == rec

    def test_deregister(self):
        rec = NodeRecord("n2", "127.0.0.1", 7701)
        self.registry.register(rec)
        self.registry.deregister("n2")
        assert self.registry.get("n2") is None

    def test_find_by_capability(self):
        self.registry.register(NodeRecord("a", "127.0.0.1", 7700, ["query", "task"]))
        self.registry.register(NodeRecord("b", "127.0.0.1", 7701, ["task"]))
        self.registry.register(NodeRecord("c", "127.0.0.1", 7702, ["memory"]))
        results = self.registry.find_by_capability("task")
        ids = {r.node_id for r in results}
        assert ids == {"a", "b"}

    def test_count(self):
        for i in range(5):
            self.registry.register(NodeRecord(f"n{i}", "127.0.0.1", 7700 + i))
        assert self.registry.count() == 5

    def test_all_nodes(self):
        self.registry.register(NodeRecord("x", "127.0.0.1", 7700))
        self.registry.register(NodeRecord("y", "127.0.0.1", 7701))
        assert len(self.registry.all_nodes()) == 2


# ---------------------------------------------------------------------------
# BaseNode — in-process handler dispatch (no actual networking)
# ---------------------------------------------------------------------------

class TestBaseNodeHandlers:
    @pytest.mark.asyncio
    async def test_heartbeat_handler(self):
        node = BaseNode(node_id="test-node", port=9900)
        hb = MesharaMessage.heartbeat(sender_id="client")
        # Access the handler directly (bypassing networking)
        response = await node._handler.dispatch(hb)
        assert response is not None
        assert response.payload["result"]["alive"] is True
        assert response.payload["result"]["node_id"] == "test-node"

    @pytest.mark.asyncio
    async def test_query_handler(self):
        node = BaseNode(node_id="qnode", port=9901)
        msg = MesharaMessage.query("hello?", sender_id="cli")
        response = await node._handler.dispatch(msg)
        assert response is not None
        result = response.payload["result"]
        assert "qnode" in result["node_id"]
        assert result["creator"] == "Cbetts1"

    @pytest.mark.asyncio
    async def test_task_handler(self):
        node = BaseNode(node_id="tnode", port=9902)
        msg = MesharaMessage.task("run_analysis", {"param": 1}, sender_id="cli")
        response = await node._handler.dispatch(msg)
        assert response is not None
        result = response.payload["result"]
        assert result["status"] == "acknowledged"

    @pytest.mark.asyncio
    async def test_announce_registers_peer(self):
        node = BaseNode(node_id="anode", port=9903)
        ann = MesharaMessage.announce(["query"], sender_id="peer-001")
        ann.payload["addr"] = ["127.0.0.1", 8888]
        await node._handler.dispatch(ann)
        assert "peer-001" in node._peers
        assert node._peers["peer-001"] == ("127.0.0.1", 8888)


# ---------------------------------------------------------------------------
# AgentNode — memory and task registry
# ---------------------------------------------------------------------------

class TestAgentNode:
    @pytest.mark.asyncio
    async def test_memory_set_get_local(self):
        node = AgentNode(port=9910)
        node.memory_set("key1", "value1")
        assert node.memory_get("key1") == "value1"

    @pytest.mark.asyncio
    async def test_memory_set_handler(self):
        node = AgentNode(node_id="mem-node", port=9911)
        msg = MesharaMessage(
            intent=Intent.MEMORY_SET,
            payload={"key": "x", "value": 42},
            sender_id="cli",
        )
        response = await node._handler.dispatch(msg)
        assert response is not None
        assert response.payload["result"]["stored"] == "x"
        assert node.memory_get("x") == 42

    @pytest.mark.asyncio
    async def test_memory_get_missing_key_returns_none(self):
        node = AgentNode(node_id="mem-node3", port=9916)
        msg = MesharaMessage(
            intent=Intent.MEMORY_GET,
            payload={"key": "does_not_exist"},
            sender_id="cli",
        )
        response = await node._handler.dispatch(msg)
        assert response is not None
        assert response.payload["result"]["value"] is None

    @pytest.mark.asyncio
    async def test_memory_get_handler(self):
        node = AgentNode(node_id="mem-node2", port=9912, memory={"greeting": "hello"})
        msg = MesharaMessage(
            intent=Intent.MEMORY_GET,
            payload={"key": "greeting"},
            sender_id="cli",
        )
        response = await node._handler.dispatch(msg)
        assert response.payload["result"]["value"] == "hello"

    @pytest.mark.asyncio
    async def test_register_and_execute_task(self):
        node = AgentNode(node_id="exec-node", port=9913)

        async def double(args):
            return args["n"] * 2

        node.register_task("double", double)
        msg = MesharaMessage.task("double", {"n": 21}, sender_id="cli")
        response = await node._handler.dispatch(msg)
        assert response.payload["result"]["result"] == 42
        assert response.payload["result"]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_unknown_task_returns_error(self):
        node = AgentNode(node_id="u-node", port=9914)
        msg = MesharaMessage.task("nonexistent_task", {})
        response = await node._handler.dispatch(msg)
        assert response.payload["result"]["status"] == "unknown_task"

    @pytest.mark.asyncio
    async def test_reasoning_engine_integration(self):
        node = AgentNode(node_id="r-node", port=9915)
        node.engine.add_rule("meshara", "Meshara is the The Artificial Intelligence Mesh.")
        msg = MesharaMessage.query("Tell me about meshara", sender_id="cli")
        response = await node._handler.dispatch(msg)
        assert "The Artificial Intelligence Mesh" in response.payload["result"]["answer"]
