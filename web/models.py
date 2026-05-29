from dataclasses import dataclass


@dataclass(slots=True)
class AuthSessionRecord:
    scope: str
    cookie_str: str
    status: str
    updated_at: str
