"""Leave balance from the system of record — no model needed to read a number."""


def run(ctx):
    balances = ctx.input("subject.leave_balance") or {}
    parts = [f"{v:g} {k}" for k, v in sorted(balances.items())]
    return {
        "answer": "Your current balance: " + (", ".join(parts) if parts else "no leave on record") + ".",
        "citations": [{"source": "system_of_record", "field": "leave_balance"}],
    }
