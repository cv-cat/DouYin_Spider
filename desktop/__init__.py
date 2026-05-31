"""Desktop client package for the AGENT acquisition tools."""

__all__ = ["AgentDesktopApp", "DesktopServices", "main", "run"]


def __getattr__(name):
    if name in __all__:
        from . import client

        return getattr(client, name)
    raise AttributeError(name)
