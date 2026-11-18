"""IT ticketing adapter. Thin by design: map action → mock operation, pass the key as the client reference."""

from typing import Any

from core.connectors_sdk import Connector


class ItTicketing(Connector):
    def execute(self, action: str, args: dict[str, Any], idem_key: str) -> dict[str, Any]:
        if action == "open_ticket":
            return self.call("open_ticket", {**args, "reference": idem_key})
        if action == "close_ticket":
            ticket_id = (args.get("original") or {}).get("ticket_id") or args.get("ticket_id")
            self.call("update_ticket", {"ticket_id": ticket_id, "status": "closed"})
            return self.call("comment", {"ticket_id": ticket_id, "text": "Closed by compensation", "reference": idem_key})
        if action == "comment":
            return self.call("comment", {**args, "reference": idem_key})
        raise ValueError(f"unknown action {action}")


CONNECTOR = ItTicketing
