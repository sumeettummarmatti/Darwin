"""Asset allocation adapter, including the reads Prativaad needs to catch a duplicate laptop."""

from typing import Any

from core.connectors_sdk import Connector


class ItAssets(Connector):
    def execute(self, action: str, args: dict[str, Any], idem_key: str) -> dict[str, Any]:
        if action == "allocate":
            return self.call("allocate", {**args, "reference": idem_key})
        if action == "release":
            allocation_id = (args.get("original") or {}).get("allocation_id") or args.get("record_id")
            self.call("release", {"allocation_id": allocation_id})
            return {"released": allocation_id}
        if action == "recover":
            return self.call("recover", {**args, "reference": idem_key})
        raise ValueError(f"unknown action {action}")

    def read_back(self, action: str, args: dict[str, Any], idem_key: str) -> list[dict[str, Any]]:
        if action == "release":
            return [{"id": args.get("record_id"), "status": "closed", "data": {}}]
        return super().read_back(action, args, idem_key)

    def prior_effects(self, action: str, args: dict[str, Any], idem_key: str) -> list[dict[str, Any]]:
        if action != "allocate":
            return []
        found = self.call("allocations_for", {"holder_token": args["holder_token"]})["allocations"]
        return [a for a in found if a["status"] == "open" and a.get("reference") != idem_key]

    def is_effect_closed(self, record: dict[str, Any]) -> tuple[bool, str]:
        returns = self.call("returns_for", {"allocation_id": record["id"]})["returns"]
        if returns:
            r = returns[0]["data"]
            serial = record["data"].get("serial")
            return True, f"return ledger shows {serial} returned on {r.get('returned_on')} (allocation {record['id']} was never closed)"
        return False, f"allocation {record['id']} is open and no return is recorded"

    def query(self, name: str, args: dict[str, Any]) -> Any:
        if name == "allocations_for":
            return self.call("allocations_for", args)["allocations"]
        return super().query(name, args)


CONNECTOR = ItAssets
