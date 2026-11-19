"""Model router and cost meter.

Every model call in the platform goes through ``Router.complete``:

* tier comes from the skill manifest (tier 1 is the default model tier);
* escalation happens only on a **measured** trigger — the skill's declared
  ``escalate_when`` expression over the structured output, or a schema
  violation after one retry — and the reason is recorded;
* if escalation is exhausted, the call returns ``needs_human`` (low confidence
  is treated exactly like a reserved decision);
* every call is metered in INR and written to ``model_calls`` (the payload
  viewer) and the audit chain;
* a run that would exceed its budget downgrades, then hands to a human.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from core.audit import AuditChain, AuditEntry
from core.clock import Clock, new_id
from core.db import Store, dumps
from core.pii import MinimisedPayload
from core.router.adapters import ProviderConfig, build_adapter
from core.skills import SkillSpec


@dataclass
class CallContext:
    run_id: str | None
    step_id: str | None
    actor: str
    on_behalf_of: str | None
    budget_remaining_inr: float | None
    max_tier: int
    source_record: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelResult:
    output: dict[str, Any]
    tier: int
    model: str
    tokens_in: int
    tokens_out: int
    inr: float
    calls: int
    escalations: list[str]
    needs_human: bool = False
    reason: str = ""


def parse_json_object(text: str) -> Any:
    """Real models sometimes wrap JSON in prose or ``` fences. Take the outermost object;
    anything else is a schema violation, handled by the retry-then-escalate path."""
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


class RoutingConfig:
    def __init__(self, path: Path):
        self.path = path
        self.raw = yaml.safe_load(path.read_text())
        self.active_profile = os.environ.get("SETU_MODEL_PROFILE") or self._default_profile()

    def _default_profile(self) -> str:
        """A Groq key in the environment (or .env) selects the groq profile; otherwise the simulator."""
        if os.environ.get("GROQ_API_KEY") and "groq" in self.raw["profiles"]:
            return "groq"
        return self.raw.get("active_profile", "sim")

    def set_profile(self, name: str) -> None:
        if name not in self.raw["profiles"]:
            raise ValueError(f"unknown profile {name}")
        self.active_profile = name

    def provider(self, tier: int) -> ProviderConfig:
        spec = self.raw["profiles"][self.active_profile][f"tier{tier}"]
        expanded = {k: os.path.expandvars(v) if isinstance(v, str) else v for k, v in spec.items()}
        return ProviderConfig(tier=tier, **expanded)

    @property
    def max_tier(self) -> int:
        return int(self.raw.get("max_tier_per_workflow", 2))

    def profiles(self) -> dict[str, Any]:
        return self.raw["profiles"]


class Router:
    def __init__(self, store: Store, clock: Clock, audit: AuditChain, config: RoutingConfig):
        self.store = store
        self.clock = clock
        self.audit = audit
        self.config = config

    def complete(self, skill: SkillSpec, minimised: MinimisedPayload, ctx: CallContext,
                 extra_instructions: str = "") -> ModelResult:
        assert skill.kind == "model" and skill.model_tier, "only model skills reach the router"
        tier = skill.model_tier
        ceiling = min(skill.escalate_to_tier or tier, ctx.max_tier, self.config.max_tier)
        escalations: list[str] = []
        totals = {"in": 0, "out": 0, "inr": 0.0, "calls": 0}
        retried_schema = False
        reason_for_this_call = "default tier from skill manifest"
        system = (skill.prompt_text or "") + (("\n\n" + extra_instructions) if extra_instructions else "")
        user = json.dumps(minimised.payload, sort_keys=True, default=str)

        while True:
            provider = self.config.provider(tier)
            # Budget guard: estimate this call from the input size before spending.
            estimate = (len(system) + len(user)) / 4 / 1e6 * provider.inr_per_m_in * 2
            if ctx.budget_remaining_inr is not None and totals["inr"] + estimate > ctx.budget_remaining_inr:
                if tier > 1:
                    escalations.append(f"budget: downgraded tier {tier}→{tier - 1}")
                    tier -= 1
                    continue
                return self._finish(skill, {}, tier, provider, totals, escalations, True, "budget exhausted — handed to a human")

            adapter = build_adapter(provider)
            raw = adapter.complete(system, user, skill.simulate)
            inr = raw.tokens_in / 1e6 * provider.inr_per_m_in + raw.tokens_out / 1e6 * provider.inr_per_m_out
            totals["in"] += raw.tokens_in
            totals["out"] += raw.tokens_out
            totals["inr"] += inr
            totals["calls"] += 1
            try:
                output = parse_json_object(raw.text)
            except json.JSONDecodeError:
                output = None
            problems = skill.validate_output(output) if output is not None else ["response is not JSON"]
            self._record(skill, ctx, provider, minimised, user, output if output is not None else raw.text, raw, inr, reason_for_this_call, problems)

            if problems:
                if not retried_schema:
                    retried_schema = True
                    reason_for_this_call = f"retry after schema violation: {problems}"
                    continue
                if tier < ceiling:
                    escalations.append(f"schema violation after 1 retry → tier {tier + 1}")
                    reason_for_this_call = escalations[-1]
                    tier += 1
                    retried_schema = False
                    continue
                return self._finish(skill, {}, tier, provider, totals, escalations, True,
                                    f"structured output invalid after retry at max tier: {problems}")

            trigger = self._escalation_trigger(skill, output)
            if trigger:
                if tier < ceiling:
                    escalations.append(f"{trigger} → tier {tier + 1}")
                    reason_for_this_call = f"measured trigger: {trigger}"
                    tier += 1
                    continue
                return self._finish(skill, output, tier, provider, totals, escalations, True,
                                    f"{trigger} at the highest permitted tier — low confidence is treated like a reserved decision")
            return self._finish(skill, output, tier, provider, totals, escalations, False, "")

    def _escalation_trigger(self, skill: SkillSpec, output: dict[str, Any]) -> str | None:
        if skill.escalate_when is None:
            return None
        try:
            fired = bool(skill.escalate_when.evaluate(output))
        except Exception as exc:  # a trigger referencing a missing field fails safe: escalate
            return f"escalate_when could not be evaluated ({exc})"
        if not fired:
            return None
        shown = {n: output.get(n) for n in skill.escalate_when.names() if n in output}
        return f"escalate_when '{skill.escalate_when.source}' fired {shown}"

    def _finish(self, skill: SkillSpec, output: dict[str, Any], tier: int, provider: ProviderConfig,
                totals: dict[str, Any], escalations: list[str], needs_human: bool, reason: str) -> ModelResult:
        return ModelResult(
            output=output, tier=tier, model=provider.label, tokens_in=totals["in"], tokens_out=totals["out"],
            inr=totals["inr"], calls=totals["calls"], escalations=escalations, needs_human=needs_human, reason=reason,
        )

    def _record(self, skill: SkillSpec, ctx: CallContext, provider: ProviderConfig, minimised: MinimisedPayload,
                user: str, response: Any, raw: Any, inr: float, reason: str, problems: list[str]) -> None:
        call_id = new_id("mc")
        with self.store.tx() as conn:
            conn.execute(
                "INSERT INTO model_calls (id, run_id, step_id, skill, tier, provider, model, region, prompt_version, "
                "source_record, outbound_payload, stripped_fields, response, tokens_in, tokens_out, inr, escalation_reason, at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (call_id, ctx.run_id, ctx.step_id, skill.ref, provider.tier, provider.adapter, provider.model, provider.region,
                 skill.prompt_version, dumps(ctx.source_record), user, dumps(minimised.stripped), dumps(response),
                 raw.tokens_in, raw.tokens_out, inr, reason, self.clock.now_iso()),
            )
        self.audit.append(AuditEntry(
            actor=ctx.actor, on_behalf_of=ctx.on_behalf_of, action=f"model.{skill.name}", kind="model",
            outcome="schema_violation" if problems else "ok", run_id=ctx.run_id, step_id=ctx.step_id,
            inputs={"declared_fields": sorted(minimised.payload.keys()), "stripped": len(minimised.stripped)},
            prompt_version=f"{skill.name}/v{skill.prompt_version}", model_id=provider.label, tier=provider.tier,
            tokens_in=raw.tokens_in, tokens_out=raw.tokens_out, inr=inr, latency_ms=raw.latency_ms,
            detail={"model_call_id": call_id, "route_reason": reason, "problems": problems,
                    "reasoning": (response or {}).get("reasoning") if isinstance(response, dict) else None},
        ))
