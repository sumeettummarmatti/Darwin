"""ID legibility check. Low confidence is not 'proceed carefully' — the router hands it to a human."""


def run(ctx):
    return ctx.ask_model()
