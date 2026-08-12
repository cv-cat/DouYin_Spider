"""依赖提供者:全局单例。main.py 在启动前调用 init_deps()。"""
from webapp.backend.eventbus import event_bus

_account_manager = None
_task_manager = None
_live_service = None
_message_service = None


def init_deps():
    global _account_manager, _task_manager, _live_service, _message_service
    if _account_manager is None:
        from webapp.backend.accounts.manager import AccountManager
        _account_manager = AccountManager()
    if _task_manager is None:
        from webapp.backend.tasks.manager import TaskManager
        _task_manager = TaskManager()
    if _live_service is None:
        from webapp.backend.services.live import LiveService
        _live_service = LiveService()
    if _message_service is None:
        from webapp.backend.services.message import MessageService
        _message_service = MessageService()
    return _account_manager, _task_manager, _live_service, _message_service, event_bus


def get_account_manager():
    return _account_manager


def get_task_manager():
    return _task_manager


def get_live_service():
    return _live_service


def get_message_service():
    return _message_service


def get_event_bus():
    return event_bus
