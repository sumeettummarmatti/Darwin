"""Agent skill registry — extension point 2.

A skill is a directory under ``skills/`` with:

* ``manifest.yaml`` — the contract: declared inputs (the PII proxy strips
  everything else), outputs schema, model tier and *measured* escalation
  trigger, capabilities (reserved verbs can never appear), prompt version.
* ``handler.py``    — ``run(ctx) -> dict``. Gets a ``SkillContext``: declared
  inputs, policy evaluation, a metered model call, and ``propose()``. No HTTP
  client, no database, no connector handle. That is invariant 1.
* ``prompt.vN.md``  — versioned prompt (model skills only). Never contains a rule.
* ``simulated.py``  — deterministic responder for the ``sim`` provider.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

import yaml

from core.rules.expr import Expression, ExpressionError

_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "number": (int, float),
    "integer": (int,),
    "boolean": (bool,),
    "object": (dict,),
    "array": (list,),
    "any": (object,),
}


class SkillLoadError(Exception):
    pass


@dataclass
class SkillSpec:
    name: str
    version: int
    description: str
    kind: str                                  # model | deterministic
    inputs: list[str]
    outputs: dict[str, str]
    capabilities: list[str]
    directory: Path
    run: Callable[[Any], dict[str, Any]]
    model_tier: int | None = None
    escalate_to_tier: int | None = None
    escalate_when: Expression | None = None
    prompt_version: str | None = None
    prompt_text: str | None = None
    simulate: Callable[[dict[str, Any], int], dict[str, Any]] | None = None
    policy_tags: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def ref(self) -> str:
        return f"{self.name}@v{self.version}"

    def validate_output(self, output: Any) -> list[str]:
        """Return a list of schema violations (empty when valid)."""
        if not isinstance(output, dict):
            return ["output is not a JSON object"]
        problems = []
        for key, type_name in self.outputs.items():
            optional = type_name.endswith("?")
            base = type_name.rstrip("?")
            if key not in output:
                if not optional:
                    problems.append(f"missing '{key}'")
                continue
            if output[key] is None and optional:
                continue
            expected = _TYPES.get(base, (object,))
            if base == "number" and isinstance(output[key], bool):
                problems.append(f"'{key}' should be number")
            elif not isinstance(output[key], expected):
                problems.append(f"'{key}' should be {base}")
        return problems


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SkillLoadError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_skill(directory: Path, *, may_never: list[str], prohibited: list[str]) -> SkillSpec:
    manifest_path = directory / "manifest.yaml"
    raw = yaml.safe_load(manifest_path.read_text())
    name = raw.get("skill")
    if not name:
        raise SkillLoadError(f"{manifest_path}: missing 'skill'")
    where = f"{manifest_path} ({name})"

    capabilities = list(raw.get("capabilities") or [])
    granted_reserved = sorted(set(capabilities) & set(may_never))
    if granted_reserved:
        # Invariant 3: reserved verbs are never granted. Fail at load, not at run.
        raise SkillLoadError(f"{where}: capabilities include reserved verb(s) {granted_reserved} — cannot be granted to an agent")

    inputs = list(raw.get("inputs") or [])
    leaked = sorted({i for i in inputs if i.rsplit('.', 1)[-1] in set(prohibited)})
    if leaked:
        raise SkillLoadError(f"{where}: declares prohibited criteria as inputs {leaked}")

    kind = raw.get("kind", "model" if raw.get("model_tier") else "deterministic")
    if kind == "deterministic" and raw.get("model_tier"):
        raise SkillLoadError(f"{where}: a deterministic skill cannot declare a model_tier")

    handler = _load_module(directory / "handler.py", f"setu_skill_{directory.name}")
    if not hasattr(handler, "run"):
        raise SkillLoadError(f"{where}: handler.py must define run(ctx)")

    spec = SkillSpec(
        name=name,
        version=int(raw.get("version", 1)),
        description=raw.get("description", ""),
        kind=kind,
        inputs=inputs,
        outputs=dict(raw.get("outputs") or {}),
        capabilities=capabilities,
        directory=directory,
        run=handler.run,
        policy_tags=list(raw.get("policy_tags") or []),
        raw=raw,
    )
    if kind == "model":
        spec.model_tier = int(raw.get("model_tier", 1))
        spec.escalate_to_tier = int(raw.get("escalate_to_tier", spec.model_tier))
        if raw.get("escalate_when"):
            try:
                spec.escalate_when = Expression(raw["escalate_when"])
            except ExpressionError as exc:
                raise SkillLoadError(f"{where}: escalate_when: {exc}") from exc
        spec.prompt_version = str(raw.get("prompt_version", "1"))
        prompt_file = directory / f"prompt.v{spec.prompt_version}.md"
        if not prompt_file.exists():
            raise SkillLoadError(f"{where}: missing {prompt_file.name}")
        spec.prompt_text = prompt_file.read_text()
        sim_file = directory / "simulated.py"
        if sim_file.exists():
            spec.simulate = _load_module(sim_file, f"setu_skill_sim_{directory.name}").respond
        if spec.escalate_to_tier and spec.escalate_to_tier >= 3 and not raw.get("tier3_opt_in"):
            raise SkillLoadError(f"{where}: tier 3 requires an explicit tier3_opt_in with a justification")
    return spec
