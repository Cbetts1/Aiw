"""Tests for the AIM Builder module."""

from __future__ import annotations

import json
import os

import pytest

from aim.builder.engine import BuilderEngine, ModuleSpec, BuildResult


# ---------------------------------------------------------------------------
# ModuleSpec
# ---------------------------------------------------------------------------

class TestModuleSpec:
    def test_default_template(self):
        spec = ModuleSpec(name="mymod", description="A test module")
        assert spec.template == "agent_node"

    def test_capabilities_default_empty(self):
        spec = ModuleSpec(name="mymod", description="desc")
        assert spec.capabilities == []

    def test_extra_default_empty(self):
        spec = ModuleSpec(name="mymod", description="desc")
        assert spec.extra == {}

    def test_custom_capabilities(self):
        spec = ModuleSpec(name="mymod", description="desc", capabilities=["query", "task"])
        assert "query" in spec.capabilities


# ---------------------------------------------------------------------------
# BuildResult
# ---------------------------------------------------------------------------

class TestBuildResult:
    def test_success_and_errors(self):
        result = BuildResult(success=True, module_path="/some/path")
        assert result.success is True
        assert result.errors == []
        assert result.files_created == []

    def test_failure_result(self):
        result = BuildResult(success=False, module_path="/x", errors=["oops"])
        assert result.success is False
        assert "oops" in result.errors


# ---------------------------------------------------------------------------
# BuilderEngine.build_module
# ---------------------------------------------------------------------------

class TestBuilderEngineBuildModule:
    def test_build_module_creates_files(self, tmp_path):
        engine = BuilderEngine(base_path=str(tmp_path))
        spec = ModuleSpec(
            name="widget",
            description="A widget module",
            capabilities=["query"],
        )
        result = engine.build_module(spec)

        assert result.success is True
        module_dir = tmp_path / "widget"
        assert module_dir.is_dir()
        assert (module_dir / "__init__.py").exists()
        assert (module_dir / "node.py").exists()
        assert (module_dir / "registry.py").exists()

    def test_build_module_files_listed_in_result(self, tmp_path):
        engine = BuilderEngine(base_path=str(tmp_path))
        spec = ModuleSpec(name="sprocket", description="Sprocket module")
        result = engine.build_module(spec)
        assert len(result.files_created) == 3

    def test_build_module_agent_node_template(self, tmp_path):
        engine = BuilderEngine(base_path=str(tmp_path))
        spec = ModuleSpec(name="agmod", description="Agent module", template="agent_node")
        result = engine.build_module(spec)
        node_code = (tmp_path / "agmod" / "node.py").read_text()
        assert "AgentNode" in node_code

    def test_build_module_base_node_template(self, tmp_path):
        engine = BuilderEngine(base_path=str(tmp_path))
        spec = ModuleSpec(name="basemod", description="Base module", template="base_node")
        result = engine.build_module(spec)
        node_code = (tmp_path / "basemod" / "node.py").read_text()
        assert "BaseNode" in node_code

    def test_build_module_registry_is_thread_safe(self, tmp_path):
        engine = BuilderEngine(base_path=str(tmp_path))
        spec = ModuleSpec(name="regmod", description="Registry test")
        engine.build_module(spec)
        registry_code = (tmp_path / "regmod" / "registry.py").read_text()
        assert "RLock" in registry_code


# ---------------------------------------------------------------------------
# BuilderEngine.list_modules
# ---------------------------------------------------------------------------

class TestBuilderEngineListModules:
    def test_list_modules_returns_list(self, tmp_path):
        engine = BuilderEngine(base_path=str(tmp_path))
        modules = engine.list_modules()
        assert isinstance(modules, list)

    def test_list_modules_includes_built_module(self, tmp_path):
        engine = BuilderEngine(base_path=str(tmp_path))
        spec = ModuleSpec(name="listed", description="Should appear in list")
        engine.build_module(spec)
        modules = engine.list_modules()
        assert "listed" in modules

    def test_list_modules_empty_for_new_dir(self, tmp_path):
        engine = BuilderEngine(base_path=str(tmp_path / "newdir"))
        modules = engine.list_modules()
        assert modules == []


# ---------------------------------------------------------------------------
# BuilderEngine.build_config
# ---------------------------------------------------------------------------

class TestBuilderEngineBuildConfig:
    def test_build_config_writes_json(self, tmp_path):
        engine = BuilderEngine(base_path=str(tmp_path / "aim"))
        result = engine.build_config("myconfig", {"key": "value", "num": 42})
        assert result.success is True
        config_path = result.module_path
        with open(config_path) as fh:
            data = json.load(fh)
        assert data["key"] == "value"
        assert data["num"] == 42

    def test_build_config_result_has_file(self, tmp_path):
        engine = BuilderEngine(base_path=str(tmp_path / "aim"))
        result = engine.build_config("testcfg", {})
        assert len(result.files_created) == 1
        assert result.files_created[0].endswith("testcfg.json")
