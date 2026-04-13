"""
AIM Builder — Code-generation engine for new AIM modules.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class ModuleSpec:
    """
    Specification for a new AIM subpackage.

    Parameters
    ----------
    name         : Python identifier used as the directory/package name.
    description  : Human-readable description embedded in docstrings.
    capabilities : List of capability tags the generated node advertises.
    template     : Code template style: ``"agent_node"`` or ``"base_node"``.
    extra        : Arbitrary extra metadata passed through to the builder.
    """

    name: str
    description: str
    capabilities: list[str] = field(default_factory=list)
    template: str = "agent_node"
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class BuildResult:
    """
    Outcome of a :class:`BuilderEngine` operation.

    Parameters
    ----------
    success      : Whether the operation completed without errors.
    module_path  : Filesystem path to the generated artefact.
    files_created: List of every file that was written.
    errors       : Error messages accumulated during the build.
    """

    success: bool
    module_path: str
    files_created: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

_AGENT_NODE_TEMPLATE = '''\
"""
AIM {name} — auto-generated AgentNode subclass.

{description}
"""

from __future__ import annotations

import logging
from typing import Any

from aim.node.agent import AgentNode

logger = logging.getLogger(__name__)

ORIGIN_CREATOR = "Cbetts1"


class {class_name}Node(AgentNode):
    """
    {description}

    Capabilities: {capabilities}
    """

    CREATOR: str = ORIGIN_CREATOR

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("capabilities", {capabilities_list!r})
        super().__init__(*args, **kwargs)
        self._register_domain_handlers()

    def _register_domain_handlers(self) -> None:
        """Register domain-specific protocol handlers."""

    async def on_query(self, text: str, context: dict[str, Any]) -> dict[str, Any]:
        result = await self.engine.reason(text, context)
        return {{"text": result, "node": self.node_id, "creator": self.CREATOR}}
'''

_BASE_NODE_TEMPLATE = '''\
"""
AIM {name} — auto-generated BaseNode subclass.

{description}
"""

from __future__ import annotations

import logging
from typing import Any

from aim.node.base import BaseNode

logger = logging.getLogger(__name__)

ORIGIN_CREATOR = "Cbetts1"


class {class_name}Node(BaseNode):
    """
    {description}

    Capabilities: {capabilities}
    """

    CREATOR: str = ORIGIN_CREATOR

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("capabilities", {capabilities_list!r})
        super().__init__(*args, **kwargs)

    async def on_query(self, text: str, context: dict[str, Any]) -> dict[str, Any]:
        return {{"text": f"{{self.__class__.__name__}} received: {{text}}", "node": self.node_id}}
'''

_REGISTRY_TEMPLATE = '''\
"""
AIM {name} — thread-safe in-process registry.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class {class_name}Record:
    """A record stored in the {name} registry."""

    record_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


class {class_name}Registry:
    """Thread-safe registry for {name} records."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: dict[str, {class_name}Record] = {{}}

    def register(self, record: {class_name}Record) -> None:
        with self._lock:
            self._records[record.record_id] = record

    def get(self, record_id: str) -> {class_name}Record | None:
        with self._lock:
            return self._records.get(record_id)

    def deregister(self, record_id: str) -> None:
        with self._lock:
            self._records.pop(record_id, None)

    def all(self) -> list[{class_name}Record]:
        with self._lock:
            return list(self._records.values())

    @classmethod
    def default(cls) -> "{class_name}Registry":
        """Return the module-level singleton registry."""
        return _default_registry


_default_registry: {class_name}Registry = {class_name}Registry()
'''

_INIT_TEMPLATE = '''\
"""
AIM {name} — {description}
"""

from __future__ import annotations

from aim.{name}.node import {class_name}Node
from aim.{name}.registry import {class_name}Registry, {class_name}Record

__all__ = ["{class_name}Node", "{class_name}Registry", "{class_name}Record"]
'''


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class BuilderEngine:
    """
    Generates new AIM subpackages, scripts, and config files.

    Parameters
    ----------
    base_path : Root directory for AIM subpackages (default ``"aim"``).
    """

    def __init__(self, base_path: str = "aim") -> None:
        self._base_path = base_path

    # ------------------------------------------------------------------
    # Module building
    # ------------------------------------------------------------------

    def build_module(self, spec: ModuleSpec) -> BuildResult:
        """
        Scaffold a new AIM subpackage on disk.

        Creates ``{base_path}/{spec.name}/`` with:
        * ``__init__.py`` — exports
        * ``node.py``     — AgentNode or BaseNode subclass
        * ``registry.py`` — thread-safe registry
        """
        module_dir = os.path.join(self._base_path, spec.name)
        errors: list[str] = []
        files_created: list[str] = []

        try:
            os.makedirs(module_dir, exist_ok=True)
        except OSError as exc:
            return BuildResult(
                success=False,
                module_path=module_dir,
                errors=[str(exc)],
            )

        class_name = spec.name.capitalize()
        capabilities_str = ", ".join(spec.capabilities) if spec.capabilities else "general"

        template_src = (
            _AGENT_NODE_TEMPLATE if spec.template == "agent_node" else _BASE_NODE_TEMPLATE
        )
        node_code = template_src.format(
            name=spec.name,
            class_name=class_name,
            description=spec.description,
            capabilities=capabilities_str,
            capabilities_list=spec.capabilities,
        )

        registry_code = _REGISTRY_TEMPLATE.format(
            name=spec.name,
            class_name=class_name,
        )

        init_code = _INIT_TEMPLATE.format(
            name=spec.name,
            class_name=class_name,
            description=spec.description,
        )

        for filename, content in [
            ("node.py", node_code),
            ("registry.py", registry_code),
            ("__init__.py", init_code),
        ]:
            path = os.path.join(module_dir, filename)
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(content)
                files_created.append(path)
            except OSError as exc:
                errors.append(f"{filename}: {exc}")

        return BuildResult(
            success=len(errors) == 0,
            module_path=module_dir,
            files_created=files_created,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Script building
    # ------------------------------------------------------------------

    def build_script(self, name: str, description: str, content: str) -> BuildResult:
        """Write a shell script to ``scripts/{name}.sh``."""
        scripts_dir = os.path.join(self._base_path, "..", "scripts")
        scripts_dir = os.path.normpath(scripts_dir)
        errors: list[str] = []
        files_created: list[str] = []

        try:
            os.makedirs(scripts_dir, exist_ok=True)
        except OSError as exc:
            return BuildResult(success=False, module_path=scripts_dir, errors=[str(exc)])

        path = os.path.join(scripts_dir, f"{name}.sh")
        header = f"#!/usr/bin/env bash\n# {description}\n# Generated by AIM BuilderEngine\n\n"
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(header + content)
            os.chmod(path, 0o755)
            files_created.append(path)
        except OSError as exc:
            errors.append(str(exc))

        return BuildResult(
            success=len(errors) == 0,
            module_path=path,
            files_created=files_created,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Config building
    # ------------------------------------------------------------------

    def build_config(self, name: str, data: dict[str, Any]) -> BuildResult:
        """Write a JSON config file to ``configs/{name}.json``."""
        configs_dir = os.path.join(self._base_path, "..", "configs")
        configs_dir = os.path.normpath(configs_dir)
        errors: list[str] = []
        files_created: list[str] = []

        try:
            os.makedirs(configs_dir, exist_ok=True)
        except OSError as exc:
            return BuildResult(success=False, module_path=configs_dir, errors=[str(exc)])

        path = os.path.join(configs_dir, f"{name}.json")
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
            files_created.append(path)
        except OSError as exc:
            errors.append(str(exc))

        return BuildResult(
            success=len(errors) == 0,
            module_path=path,
            files_created=files_created,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def list_modules(self) -> list[str]:
        """Return names of existing Python subpackages inside *base_path*."""
        try:
            entries = os.listdir(self._base_path)
        except OSError:
            return []
        return sorted(
            e for e in entries
            if os.path.isdir(os.path.join(self._base_path, e))
            and os.path.isfile(os.path.join(self._base_path, e, "__init__.py"))
        )

    # ------------------------------------------------------------------
    # Expand (build + auto-register capabilities in ANS)
    # ------------------------------------------------------------------

    def expand(self, spec: ModuleSpec) -> BuildResult:
        """
        Build a module and register its capabilities in the ANS registry.

        This is an alias for :meth:`build_module` that additionally inserts
        an ``aim://{name}.aim`` record into the local ANS registry so the
        new module is immediately discoverable inside the mesh.
        """
        result = self.build_module(spec)
        if result.success:
            try:
                from aim.ans.registry import ANSRegistry, ANSRecord
                registry = ANSRegistry.default()
                record = ANSRecord(
                    name=f"{spec.name}.aim",
                    node_id=f"builder-{spec.name}",
                    host="127.0.0.1",
                    port=0,
                    capabilities=list(spec.capabilities),
                )
                registry.register(record)
            except Exception:
                pass  # ANS registration is best-effort
        return result
