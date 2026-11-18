"""Exit decision packet. The model writes prose around rule-computed values; the human decides."""


def run(ctx):
    return ctx.ask_model()
