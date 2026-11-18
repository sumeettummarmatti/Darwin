"""Email and directory adapter."""

from typing import Any

from core.connectors_sdk import Connector


class Directory(Connector):
    def execute(self, action: str, args: dict[str, Any], idem_key: str) -> dict[str, Any]:
        if action == "create_account":
            return self.call("create_account", {**args, "reference": idem_key})
        if action == "suspend_account":
            ref = args.get("employee_ref") or (args.get("data") or {}).get("email")
            return self.call("suspend_account", {"employee_ref": ref, "effective_at": args.get("effective_at"), "reference": idem_key})
        raise ValueError(f"unknown action {action}")


CONNECTOR = Directory
