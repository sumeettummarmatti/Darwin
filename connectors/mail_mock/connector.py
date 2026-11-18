"""Mail mock adapter: messages land in a captured outbox."""

from typing import Any

from core.connectors_sdk import Connector


class MailMock(Connector):
    def execute(self, action: str, args: dict[str, Any], idem_key: str) -> dict[str, Any]:
        if action == "send":
            return self.call("send", {**args, "reference": idem_key})
        raise ValueError(f"unknown action {action}")


CONNECTOR = MailMock
