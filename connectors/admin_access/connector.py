"""Access-card adapter."""

from typing import Any

from core.connectors_sdk import Connector


class AdminAccess(Connector):
    def execute(self, action: str, args: dict[str, Any], idem_key: str) -> dict[str, Any]:
        if action == "issue_card":
            return self.call("issue_card", {**args, "reference": idem_key})
        if action == "revoke_card":
            holder = args.get("holder_token") or (args.get("data") or {}).get("holder_token")
            return self.call("revoke_card", {"holder_token": holder, "effective_at": args.get("effective_at"), "reference": idem_key})
        raise ValueError(f"unknown action {action}")

    def prior_effects(self, action: str, args: dict[str, Any], idem_key: str) -> list[dict[str, Any]]:
        if action != "issue_card":
            return []
        cards = self.call("cards_for", {"holder_token": args["holder_token"]})["cards"]
        return [c for c in cards if c["status"] == "active" and c.get("reference") != idem_key]

    def is_effect_closed(self, record: dict[str, Any]) -> tuple[bool, str]:
        return record["status"] != "active", f"card {record['id']} is {record['status']}"


CONNECTOR = AdminAccess
