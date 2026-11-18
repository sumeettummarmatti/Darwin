"""Stand-in model for the welcome email."""


def respond(payload, tier):
    who = payload.get("subject.display_name", "there")
    return {
        "subject": f"Welcome to TBO, {who}",
        "body": (f"Hi {who},\n\nWe're delighted you're joining us as {payload.get('subject.role_title')} in "
                 f"{payload.get('subject.location')} on {payload.get('args.start_date')}. Your manager "
                 f"{payload.get('args.manager_name')} and your buddy {payload.get('args.buddy_name')} are looking "
                 "forward to meeting you. IT and Admin will send your day-one details separately.\n\nSee you soon,\nTBO People Team"),
        "confidence": 0.9,
    }
