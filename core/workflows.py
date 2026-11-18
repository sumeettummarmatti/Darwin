"""Workflow definitions — extension point 1.

A workflow is declarative YAML: steps, dependencies, idempotency keys,
compensation, reserved flags and a budget. There is no orchestration code in a
workflow file; retries, audit, metering and approvals come from the kernel.

``validate_workflow`` enforces the invariants at **load time**:

* side-effecting connector actions carry a templated, unique idempotency key;
* ``deterministic: true`` steps cannot use a model skill;
* agent-run steps cannot carry a reserved verb (``approve``, ``accept``…);
* reserved steps must name an action the reserved registry knows;
* dependencies exist and contain no cycles; templates parse.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from core.connectors_sdk import Connector
from core.reserved import ReservedRegistry
from core.rules.expr import Expression, ExpressionError
from core.skills import SkillSpec

_TEMPLATE = re.compile(r"\{\{\s*(.+?)\s*\}\}")


class WorkflowLoadError(Exception):
    pass


@dataclass
class StepDef:
    id: str
    kind: str                                   # skill | connector | reserved | route_only
    needs: list[str] = field(default_factory=list)
    when: Expression | None = None
    args: dict[str, Any] = field(default_factory=dict)
    skill: str | None = None
    deterministic: bool = False
    connector: str | None = None
    action: str | None = None
    idempotency_key: str | None = None
    compensation: str | None = None
    schedule_at: str | None = None
    reserved_action: str | None = None
    question: str | None = None
    packet_from: list[str] = field(default_factory=list)
    decision_fields: dict[str, str] = field(default_factory=dict)
    export: dict[str, str] = field(default_factory=dict)
    invariants: list[dict[str, Any]] = field(default_factory=list)
    route_to_role: str | None = None
    sla_hours: float | None = None
    title: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowDef:
    name: str
    version: int
    description: str
    principal: str
    steps: list[StepDef]
    inputs: dict[str, str]
    triggers: dict[str, list[str]]
    budget_inr_per_run: float | None
    target_automation_rate: float | None
    service_line: str
    source_path: str
    raw: dict[str, Any]

    @property
    def ref(self) -> str:
        return f"{self.name}@v{self.version}"

    def step(self, step_id: str) -> StepDef:
        for s in self.steps:
            if s.id == step_id:
                return s
        raise KeyError(step_id)

    def ancestors(self, step_id: str) -> set[str]:
        seen: set[str] = set()
        stack = list(self.step(step_id).needs)
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(self.step(current).needs)
        return seen


# ── templating ────────────────────────────────────────────────────────────────

def template_expressions(value: Any) -> list[str]:
    """All ``{{ … }}`` expressions inside a (possibly nested) value."""
    if isinstance(value, str):
        return _TEMPLATE.findall(value)
    if isinstance(value, dict):
        return [e for v in value.values() for e in template_expressions(v)]
    if isinstance(value, list):
        return [e for v in value for e in template_expressions(v)]
    return []


def render(value: Any, scope: dict[str, Any]) -> Any:
    """Render templates. A string that is exactly one ``{{expr}}`` keeps the value's type."""
    if isinstance(value, str):
        whole = _TEMPLATE.fullmatch(value.strip())
        if whole:
            return Expression(whole.group(1)).evaluate(scope)
        return _TEMPLATE.sub(lambda m: str(Expression(m.group(1)).evaluate(scope)), value)
    if isinstance(value, dict):
        return {k: render(v, scope) for k, v in value.items()}
    if isinstance(value, list):
        return [render(v, scope) for v in value]
    return value


# ── parsing ───────────────────────────────────────────────────────────────────

def _parse_step(raw: dict[str, Any], where: str) -> StepDef:
    step_id = raw.get("id")
    if not step_id:
        raise WorkflowLoadError(f"{where}: a step has no id")
    if raw.get("reserved"):
        kind = "reserved"
    elif raw.get("route_only"):
        kind = "route_only"
    elif raw.get("connector"):
        kind = "connector"
    elif raw.get("skill"):
        kind = "skill"
    else:
        raise WorkflowLoadError(f"{where}: step '{step_id}' is not a skill, connector, reserved or route_only step")
    when = None
    if raw.get("when") is not None:
        try:
            when = Expression(raw["when"])
        except ExpressionError as exc:
            raise WorkflowLoadError(f"{where}: step '{step_id}' when: {exc}") from exc
    reserved_action = raw.get("action") if kind == "reserved" else None
    if kind == "route_only":
        reserved_action = raw.get("action")
    return StepDef(
        id=step_id,
        kind=kind,
        title=raw.get("title"),
        needs=list(raw.get("needs") or []),
        when=when,
        args=dict(raw.get("args") or {}),
        skill=raw.get("skill"),
        deterministic=bool(raw.get("deterministic", False)),
        connector=raw.get("connector"),
        action=raw.get("action") if kind == "connector" else None,
        idempotency_key=raw.get("idempotency_key"),
        compensation=raw.get("compensation"),
        schedule_at=raw.get("schedule_at"),
        reserved_action=reserved_action,
        question=raw.get("question"),
        packet_from=list(raw.get("packet_from") or []),
        decision_fields=dict(raw.get("decision_fields") or {}),
        export=dict(raw.get("export") or {}),
        invariants=list(raw.get("invariants") or []),
        route_to_role=raw.get("route_to_role"),
        sla_hours=raw.get("sla_hours"),
        raw=raw,
    )


def parse_workflow(raw: dict[str, Any], source_path: str = "<memory>") -> WorkflowDef:
    for key in ("workflow", "version", "steps"):
        if key not in raw:
            raise WorkflowLoadError(f"{source_path}: missing '{key}'")
    where = f"{source_path} ({raw['workflow']})"
    trigger = raw.get("trigger") or {}
    return WorkflowDef(
        name=raw["workflow"],
        version=int(raw["version"]),
        description=raw.get("description", ""),
        principal=raw.get("principal", f"agent:{raw['workflow']}"),
        steps=[_parse_step(s, where) for s in raw["steps"]],
        inputs=dict(raw.get("inputs") or {}),
        triggers={"events": list(trigger.get("events") or []), "intents": list(trigger.get("intents") or [])},
        budget_inr_per_run=(raw.get("metrics") or {}).get("budget_inr_per_run"),
        target_automation_rate=(raw.get("metrics") or {}).get("target_automation_rate"),
        service_line=raw.get("service_line", raw["workflow"]),
        source_path=source_path,
        raw=raw,
    )


def load_workflow_file(path: Path) -> WorkflowDef:
    return parse_workflow(yaml.safe_load(path.read_text()), str(path))


# ── validation (load time) ────────────────────────────────────────────────────

def validate_workflow(wf: WorkflowDef, *, skills: dict[str, SkillSpec], connectors: dict[str, Connector],
                      registry: ReservedRegistry) -> None:
    """Raise WorkflowLoadError on any invariant violation. Lint warnings live in Prativaad gate C."""
    where = f"{wf.source_path} ({wf.ref})"
    ids = [s.id for s in wf.steps]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise WorkflowLoadError(f"{where}: duplicate step ids {sorted(duplicates)}")
    keys_seen: dict[str, str] = {}

    for step in wf.steps:
        for need in step.needs:
            if need not in ids:
                raise WorkflowLoadError(f"{where}: step '{step.id}' needs unknown step '{need}'")
        for expr in template_expressions([step.args, step.idempotency_key, step.schedule_at, step.question]):
            try:
                Expression(expr)
            except ExpressionError as exc:
                raise WorkflowLoadError(f"{where}: step '{step.id}' template {{{{{expr}}}}}: {exc}") from exc

        if step.kind == "skill":
            spec = skills.get(step.skill or "")
            if spec is None:
                raise WorkflowLoadError(f"{where}: step '{step.id}' uses unknown skill '{step.skill}'")
            if step.deterministic and spec.kind == "model":
                # Invariant 6.
                raise WorkflowLoadError(f"{where}: step '{step.id}' is deterministic: true but skill '{spec.name}' calls a model")
            if step.raw.get("model_tier") and step.deterministic:
                raise WorkflowLoadError(f"{where}: step '{step.id}' declares model_tier on a deterministic step")

        if step.kind == "connector":
            conn = connectors.get(step.connector or "")
            if conn is None:
                raise WorkflowLoadError(f"{where}: step '{step.id}' uses unknown connector '{step.connector}'")
            spec = conn.manifest.actions.get(step.action or "")
            if spec is None:
                raise WorkflowLoadError(f"{where}: connector '{step.connector}' has no action '{step.action}'")
            full_action = f"{step.connector}.{step.action}"
            verb = registry.verb_of(full_action)
            if verb or full_action in registry.entries:
                # Invariant 3: an agent-run step can never carry a reserved verb.
                raise WorkflowLoadError(f"{where}: step '{step.id}' runs '{full_action}' as an agent — reserved verb '{verb or full_action}' cannot be granted")
            if spec.side_effect:
                key = step.idempotency_key
                if not key:
                    # Invariant 4.
                    raise WorkflowLoadError(f"{where}: side-effecting step '{step.id}' has no idempotency_key")
                if "{{" not in key:
                    raise WorkflowLoadError(f"{where}: idempotency_key for '{step.id}' must be templated per subject")
                if key in keys_seen:
                    raise WorkflowLoadError(f"{where}: idempotency_key for '{step.id}' duplicates '{keys_seen[key]}'")
                keys_seen[key] = step.id
            if step.compensation and step.compensation not in conn.manifest.actions:
                raise WorkflowLoadError(f"{where}: compensation '{step.compensation}' is not an action of {step.connector}")

        if step.kind == "reserved":
            if not step.reserved_action:
                raise WorkflowLoadError(f"{where}: reserved step '{step.id}' must name its action")
            if step.reserved_action not in registry.entries:
                raise WorkflowLoadError(f"{where}: reserved step '{step.id}' names '{step.reserved_action}', which the reserved registry does not list")

        if step.kind == "route_only":
            if not step.reserved_action or step.reserved_action not in registry.route_only:
                raise WorkflowLoadError(f"{where}: route_only step '{step.id}' must name a route_only_never_decide action")

    _check_acyclic(wf, where)


def _check_acyclic(wf: WorkflowDef, where: str) -> None:
    state: dict[str, int] = {}
    graph = {s.id: s.needs for s in wf.steps}

    def visit(node: str, trail: list[str]) -> None:
        if state.get(node) == 1:
            raise WorkflowLoadError(f"{where}: dependency cycle {' → '.join(trail + [node])}")
        if state.get(node) == 2:
            return
        state[node] = 1
        for need in graph[node]:
            visit(need, trail + [node])
        state[node] = 2

    for node in graph:
        visit(node, [])
