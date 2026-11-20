"""Invoked by the kernel's Devil's Advocate gate A, not by a workflow step."""


def run(ctx):
    return ctx.ask_model()
