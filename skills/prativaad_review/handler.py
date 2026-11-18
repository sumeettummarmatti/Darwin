"""Invoked by the kernel's Prativaad gate A, not by a workflow step."""


def run(ctx):
    return ctx.ask_model()
