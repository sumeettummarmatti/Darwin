"""Adapter for HR Autopilot's own record (system 'sor'). Same contract as any external connector."""

from typing import Any

from core.connectors_sdk import Connector


class HrRecord(Connector):
    def execute(self, action: str, args: dict[str, Any], idem_key: str) -> dict[str, Any]:
        return self.call(action, {**args, "reference": idem_key})


CONNECTOR = HrRecord
