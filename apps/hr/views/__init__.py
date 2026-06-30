"""
apps/hr/views/__init__.py
"""

from .employee import (
    employee_list,
    EmployeeCreateView,
    EmployeeUpdateView
)
from .ajax import (
    ajax_rooms_by_building,
    ajax_phonenumbers_by_room
)

__all__ = [
    'employee_list',
    'EmployeeCreateView',
    'EmployeeUpdateView',
    'ajax_rooms_by_building',
    'ajax_phonenumbers_by_room'
]

