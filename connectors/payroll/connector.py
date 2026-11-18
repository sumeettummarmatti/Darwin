"""Payroll adapter."""

from typing import Any

from core.connectors_sdk import Connector


class Payroll(Connector):
    def execute(self, action: str, args: dict[str, Any], idem_key: str) -> dict[str, Any]:
        if action == "setup_employee":
            return self.call("setup_employee", {**args, "reference": idem_key})
        if action == "prepare_settlement":
            return self.call("prepare_settlement", {**args, "reference": idem_key})
        if action == "deactivate":
            ref = args.get("employee_ref") or (args.get("data") or {}).get("employee_ref")
            return self.call("deactivate", {"employee_ref": ref, "reference": idem_key})
        raise ValueError(f"unknown action {action}")


CONNECTOR = Payroll
