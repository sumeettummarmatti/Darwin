"""Property: for any sequence of failures and any number of retries, one key ⇒ one side effect."""

import tempfile
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.kernel import Kernel
from core.types import Principal, ProposedAction
from tools.seed import seed

_KERNEL = None


def _kernel():
    global _KERNEL
    if _KERNEL is None:
        d = Path(tempfile.mkdtemp())
        _KERNEL = Kernel(d / "setu.db", d / "mocks.db")
        seed(_KERNEL)
    return _KERNEL


chaos = st.lists(st.sampled_from(["ok", "error_500", "timeout_after_commit", "ack_no_commit"]), min_size=0, max_size=6)


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(failures=chaos, retries=st.integers(min_value=1, max_value=12), n=st.integers(min_value=0, max_value=10**9))
def test_n_retries_one_side_effect(failures, retries, n):
    k = _kernel()
    key = f"prop:{n}:{len(failures)}:{retries}:v1"
    agent = Principal(id="agent:prop", kind="agent", on_behalf_of=k.principal("USR-103"))
    k.breaker.record_success("it.ticketing")
    for _ in range(retries + len(failures)):
        mode = failures.pop(0) if failures else "ok"
        if mode != "ok":
            k.mocks.set_chaos("tickets", mode, 1)
        k.executor.submit(ProposedAction(action="it.ticketing.open_ticket", args={"queue": "q", "title": key}, idem_key=key,
                                         connector="it.ticketing", connector_action="open_ticket"), agent, None)
        k.mocks.clear_chaos("tickets")
        k.breaker.record_success("it.ticketing")
    assert len(k.mocks.by_reference("tickets", key)) <= 1
    # After enough clean retries it must have landed exactly once.
    k.executor.submit(ProposedAction(action="it.ticketing.open_ticket", args={"queue": "q", "title": key}, idem_key=key,
                                     connector="it.ticketing", connector_action="open_ticket"), agent, None)
    assert len(k.mocks.by_reference("tickets", key)) == 1
