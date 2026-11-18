"""Spare calendar adapter, pre-registered so a surprise requirement does not cost 20 minutes."""

from typing import Any

from core.connectors_sdk import Connector


class Calendar(Connector):
    def execute(self, action: str, args: dict[str, Any], idem_key: str) -> dict[str, Any]:
        return self.call("create_event", {**args, "reference": idem_key})


CONNECTOR = Calendar
