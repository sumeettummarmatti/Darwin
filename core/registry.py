"""Loads every extension point from disk: policy packs, the reserved registry,
skills, connectors and workflows. Nothing is compiled in.

``Registry.load(strict=False)`` collects problems instead of raising so that
``hrx validate`` can report all of them at once; the kernel loads strictly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from core import config
from core.connectors_sdk import Connector, Transport, load_connector
from core.reserved import RegistryLoadError, ReservedRegistry, parse_registry
from core.rules.packs import PackLoadError, PolicyPack, parse_pack
from core.skills import SkillLoadError, SkillSpec, load_skill
from core.workflows import WorkflowDef, WorkflowLoadError, load_workflow_file, validate_workflow


@dataclass
class LoadProblem:
    kind: str           # pack | registry | skill | connector | workflow
    path: str
    message: str


@dataclass
class Registry:
    packs: dict[str, list[PolicyPack]] = field(default_factory=dict)
    reserved: ReservedRegistry | None = None
    skills: dict[str, SkillSpec] = field(default_factory=dict)
    connectors: dict[str, Connector] = field(default_factory=dict)
    workflows: dict[str, list[WorkflowDef]] = field(default_factory=dict)
    problems: list[LoadProblem] = field(default_factory=list)

    # ── policy lookup ─────────────────────────────────────────────────────────

    def pack(self, name: str, as_of: date | str | None = None) -> PolicyPack:
        """The pack version in force on ``as_of`` (default: today)."""
        versions = self.packs.get(name)
        if not versions:
            raise KeyError(f"no policy pack '{name}'")
        when = date.fromisoformat(as_of[:10]) if isinstance(as_of, str) else (as_of or date.today())
        in_force = [p for p in versions if p.effective_from <= when]
        if not in_force:
            raise KeyError(f"no version of '{name}' in force on {when}")
        return max(in_force, key=lambda p: p.version)

    def pack_version(self, name: str, version: int) -> PolicyPack:
        for p in self.packs.get(name, []):
            if p.version == version:
                return p
        raise KeyError(f"{name}@v{version}")

    def prohibited_criteria(self) -> list[str]:
        try:
            return list(self.pack("fair_hiring").tables.get("prohibited_criteria", {}).keys())
        except KeyError:
            return []

    # ── workflow lookup ───────────────────────────────────────────────────────

    def workflow(self, name: str, version: int | None = None) -> WorkflowDef:
        versions = self.workflows.get(name)
        if not versions:
            raise KeyError(f"no workflow '{name}'")
        if version is None:
            return max(versions, key=lambda w: w.version)
        for w in versions:
            if w.version == version:
                return w
        raise KeyError(f"{name}@v{version}")

    def latest_workflows(self) -> list[WorkflowDef]:
        return [max(v, key=lambda w: w.version) for v in self.workflows.values()]

    # ── loading ───────────────────────────────────────────────────────────────

    @classmethod
    def load(cls, transport: Transport, *, strict: bool = True, root: Path | None = None) -> "Registry":
        root = root or config.ROOT
        reg = cls()

        def problem(kind: str, path: Path | str, message: str) -> None:
            if strict:
                raise RuntimeError(f"[{kind}] {message}")
            reg.problems.append(LoadProblem(kind, str(path), message))

        # 1. Policies and the reserved registry.
        for path in sorted((root / "policies").glob("*.yaml")):
            raw = yaml.safe_load(path.read_text()) or {}
            try:
                if raw.get("registry") == "reserved_decisions":
                    candidate = parse_registry(raw, str(path))
                    if reg.reserved is None or candidate.version > reg.reserved.version:
                        reg.reserved = candidate
                elif "pack" in raw:
                    pack = parse_pack(raw, str(path))
                    reg.packs.setdefault(pack.name, []).append(pack)
            except (PackLoadError, RegistryLoadError) as exc:
                problem("pack", path, str(exc))
        if reg.reserved is None:
            problem("registry", root / "policies", "no reserved_decisions registry found")
            return reg

        # 2. Connectors (spares included, so a live-test requirement can use them).
        for manifest in sorted((root / "connectors").glob("**/manifest.yaml")):
            try:
                conn = load_connector(manifest.parent, transport)
                reg.connectors[conn.name] = conn
            except Exception as exc:  # noqa: BLE001 - report any connector failure
                problem("connector", manifest, f"{manifest.parent.name}: {exc}")

        # 3. Skills.
        for manifest in sorted((root / "skills").glob("*/manifest.yaml")):
            try:
                spec = load_skill(manifest.parent, may_never=reg.reserved.may_never, prohibited=reg.prohibited_criteria())
                reg.skills[spec.name] = spec
            except (SkillLoadError, Exception) as exc:  # noqa: BLE001
                problem("skill", manifest, str(exc))

        # 4. Workflows, validated against everything above.
        for path in sorted((root / "workflows").glob("*.yaml")):
            try:
                wf = load_workflow_file(path)
                validate_workflow(wf, skills=reg.skills, connectors=reg.connectors, registry=reg.reserved)
                reg.workflows.setdefault(wf.name, []).append(wf)
            except (WorkflowLoadError, Exception) as exc:  # noqa: BLE001
                problem("workflow", path, str(exc))
        return reg

    def summary(self) -> dict[str, Any]:
        return {
            "packs": {name: [p.version for p in versions] for name, versions in self.packs.items()},
            "reserved": self.reserved.ref if self.reserved else None,
            "skills": sorted(self.skills),
            "connectors": sorted(self.connectors),
            "workflows": {name: [w.version for w in versions] for name, versions in self.workflows.items()},
        }
