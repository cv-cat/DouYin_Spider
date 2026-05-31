from types import SimpleNamespace

import desktop.client as client


class DummyEntry:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class DummyText:
    def __init__(self, value):
        self.value = value

    def get(self, start, end):
        return self.value


class DummyStatus:
    def __init__(self):
        self.value = ""

    def set(self, value):
        self.value = value


class DummySessionService:
    def __init__(self):
        self.saved = []

    def save_cookie(self, scope, cookie_str, status="unknown"):
        self.saved.append((scope, cookie_str, status))


def test_private_cookie_save_uses_session_service(monkeypatch):
    shown = []
    session_service = DummySessionService()
    app = client.AgentDesktopApp.__new__(client.AgentDesktopApp)
    app.services = SimpleNamespace(session_service=session_service)
    app.private_cookie_scope = DummyEntry("douyin")
    app.private_cookie_text = DummyText("sid_guard=abc; uid_tt=def")
    app._status_var = DummyStatus()
    monkeypatch.setattr(client.messagebox, "showinfo", lambda title, message: shown.append((title, message)))

    app._save_private_cookie()

    assert session_service.saved == [("douyin", "sid_guard=abc; uid_tt=def", "desktop-manual")]
    assert app._status_var.value == "Cookie 已保存：douyin"
    assert shown == [("Cookie", "已保存 douyin Cookie")]
