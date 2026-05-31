import importlib.util
from pathlib import Path
import sys


def _load_build_services():
    bootstrap_path = Path(__file__).resolve().parents[2] / "desktop" / "bootstrap.py"
    spec = importlib.util.spec_from_file_location("desktop_bootstrap", bootstrap_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_services


def test_build_services_does_not_require_web_app(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "web.app", None)
    build_services = _load_build_services()
    services = build_services({"DB_PATH": tmp_path / "desktop.sqlite3"})

    assert services.app is None
    assert services.agent is not None
    assert services.session is not None
    assert services.live is not None
    assert services.im is not None
    assert services.agent.get_video_config()
    assert callable(services.agent.queue_video_collect)
    assert callable(services.agent.list_private_targets)


def test_agent_service_exposes_desktop_operation_surface(tmp_path):
    build_services = _load_build_services()
    services = build_services({"DB_PATH": tmp_path / "desktop.sqlite3"})
    agent = services.agent

    required_methods = {
        "video": [
            "list_videos",
            "get_video_config",
            "save_video_config",
            "start_video_collect",
            "stop_video_collect",
            "clear_videos",
            "export_videos",
        ],
        "comments": [
            "list_comments",
            "get_comment_config",
            "save_comment_config",
            "start_comment_monitor",
            "stop_comment_monitor",
            "clear_comments",
            "export_comments",
        ],
        "live": [
            "list_live_rooms",
            "get_live_config",
            "save_live_config",
            "start_live_monitor",
            "stop_live_monitor",
            "clear_live_rooms",
            "export_live_rooms",
        ],
        "groups": [
            "list_group_messages",
            "get_group_config",
            "save_group_config",
            "start_group_monitor",
            "stop_group_monitor",
            "clear_group_messages",
            "export_group_messages",
        ],
        "private": [
            "list_private_targets",
            "get_private_config",
            "save_private_config",
            "start_private_send",
            "stop_private_send",
            "clear_private_targets",
            "export_private_targets",
        ],
    }

    missing = [
        f"{area}.{method}"
        for area, methods in required_methods.items()
        for method in methods
        if not callable(getattr(agent, method, None))
    ]
    assert missing == []
