"""Connector SDK — extension point 3.

A connector adapts one external system. It declares its actions in a manifest
(which are side-effecting, which are irreversible, how to compensate, how to
verify) and implements three methods. Only the kernel's executor ever calls a
connector; agents never hold a handle to one.

Connectors reach the system through a ``Transport`` so the same connector runs
against the in-process TBO mocks (default, zero setup) or over HTTP.
"""

from __future__ import annotations

import importlib.util
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import yaml


class TransportError(Exception):
    """The external system failed (5xx, timeout, connection reset)."""

    def __init__(self, message: str, *, status: int = 500, timeout: bool = False):
        super().__init__(message)
        self.status = status
        self.timeout = timeout


class Transport(Protocol):
    def call(self, system: str, op: str, payload: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class ActionSpec:
    name: str
    side_effect: bool = True
    irreversible: bool = False
    money: bool = False
    compensation: str | None = None
    verify: bool = True
    capability: str = "provision"   # must be in the reserved registry's agent allow-list
    description: str = ""


@dataclass
class ConnectorManifest:
    name: str
    version: int
    system: str
    actions: dict[str, ActionSpec]
    queries: list[str] = field(default_factory=list)
    cost_inr_per_call: float = 0.0
    description: str = ""
    domain: str | None = None       # RBAC domain, e.g. "it", "payroll"
    purpose: str | None = None      # DPDP purpose this system processes PII for


class Connector(ABC):
    """Subclass this in ``connectors/<name>/connector.py``."""

    manifest: ConnectorManifest

    def __init__(self, manifest: ConnectorManifest, transport: Transport):
        self.manifest = manifest
        self.transport = transport

    @property
    def name(self) -> str:
        return self.manifest.name

    def call(self, op: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.transport.call(self.manifest.system, op, payload)

    @abstractmethod
    def execute(self, action: str, args: dict[str, Any], idem_key: str) -> dict[str, Any]:
        """Perform the action. Pass ``idem_key`` to the system as the client reference."""

    def read_back(self, action: str, args: dict[str, Any], idem_key: str) -> list[dict[str, Any]]:
        """Every record this idempotency key produced in the external system.

        Used for post-state verification (expect exactly one) and to decide
        whether a timed-out call actually landed before retrying."""
        return self.call("get_by_reference", {"reference": idem_key}).get("records", [])

    def prior_effects(self, action: str, args: dict[str, Any], idem_key: str) -> list[dict[str, Any]]:
        """Open effects of the same kind for the same subject that this key did
        NOT produce. Prativaad gate A's duplicate_side_effect check uses it."""
        return []

    def is_effect_closed(self, record: dict[str, Any]) -> tuple[bool, str]:
        """Resolve a duplicate_side_effect objection: is this prior effect actually closed?"""
        return False, "connector cannot verify; route to a human"

    def query(self, name: str, args: dict[str, Any]) -> Any:
        """Read-only queries (e.g. open allocations for a person). Never side-effecting."""
        raise NotImplementedError(f"{self.name} has no query '{name}'")


def load_manifest(path: Path) -> ConnectorManifest:
    raw = yaml.safe_load(path.read_text())
    actions = {
        name: ActionSpec(name=name, **{k: v for k, v in (spec or {}).items() if k in ActionSpec.__dataclass_fields__})
        for name, spec in (raw.get("actions") or {}).items()
    }
    return ConnectorManifest(
        name=raw["connector"],
        version=int(raw.get("version", 1)),
        system=raw["system"],
        actions=actions,
        queries=list(raw.get("queries") or []),
        cost_inr_per_call=float(raw.get("cost_inr_per_call", 0.0)),
        description=raw.get("description", ""),
        domain=raw.get("domain"),
        purpose=raw.get("purpose"),
    )


def load_connector(directory: Path, transport: Transport) -> Connector:
    manifest = load_manifest(directory / "manifest.yaml")
    module_path = directory / "connector.py"
    spec = importlib.util.spec_from_file_location(f"setu_connector_{directory.name}", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cls = getattr(module, "CONNECTOR")
    return cls(manifest, transport)
