"""Profile validation and guard helpers for labeling/verification actions."""

import re

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PROFILE_REQUIRED_MESSAGE = "Name and a valid email are required before labeling or verification."


def profile_name_email(profile):
    profile = profile or {}
    name = str(profile.get("name") or "").strip()
    email = str(profile.get("email") or "").strip()
    return name, email


def is_valid_email(email):
    return bool(_EMAIL_RE.match((email or "").strip()))


def is_profile_complete(profile):
    name, email = profile_name_email(profile)
    return bool(name) and is_valid_email(email)


def profile_actor(profile):
    name, email = profile_name_email(profile)
    if not name or not email:
        return None
    return f"{name} <{email}>"


def require_complete_profile(profile):
    if is_profile_complete(profile):
        return
    raise ValueError(_PROFILE_REQUIRED_MESSAGE)
