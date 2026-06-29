"""
apps/tasks/views/__init__.py
Saubere Exports
"""

from .dashboard import my_tasks
from .create import TaskCreateView, choose_task_type
from .delete import task_delete
# task_detail kommt aus detail (nicht hier importieren, um Zirkel zu vermeiden)

__all__ = [
    'my_tasks',
    'TaskCreateView',
    'choose_task_type',
    'task_delete',
]