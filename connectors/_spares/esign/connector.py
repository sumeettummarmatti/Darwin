"""Spare e-signature adapter."""

from typing import Any

from core.connectors_sdk import Connector


class Esign(Connector):
    def execute(self, action: str, args: dict[str, Any], idem_key: str) -> dict[str, Any]:
        return self.call("send_envelope", {**args, "reference": idem_key})


CONNECTOR = Esign
