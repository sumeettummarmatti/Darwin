"""Read-only adapter over the synthetic sourcing mock."""

from typing import Any

from core.connectors_sdk import Connector


class SourcingMock(Connector):
    def execute(self, action: str, args: dict[str, Any], idem_key: str) -> dict[str, Any]:
        if action in ("signals", "applicants"):
            return self.call(action, {"role": args["role"]})
        raise ValueError(f"unknown action {action}")


CONNECTOR = SourcingMock
