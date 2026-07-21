"""
Employee views package.

Submodules:
- common: shared helpers (documents, recruitment prefill, formset save)
- crud: employee list, create, and update
- profile: self-service my-profile view
- workgroups: workgroup management for assisting admins
- locations: building, room, and phone number management

Do not remove any existing requirements from this package without explicit instruction.
"""

from .crud import EmployeeCreateView, EmployeeUpdateView, employee_list, phone_list
from .locations import (
    BuildingCreateView,
    BuildingDeleteView,
    BuildingUpdateView,
    LocationManagementView,
    PhoneNumberCreateView,
    PhoneNumberDeleteView,
    PhoneNumberUpdateView,
    RoomCreateView,
    RoomDeleteView,
    RoomUpdateView,
)
from .profile import MyProfileView
from .workgroups import (
    WorkgroupCreateView,
    WorkgroupDeleteView,
    WorkgroupListView,
    WorkgroupUpdateView,
)

__all__ = [
    'employee_list',
    'phone_list',
    'EmployeeCreateView',
    'EmployeeUpdateView',
    'MyProfileView',
    'WorkgroupListView',
    'WorkgroupCreateView',
    'WorkgroupUpdateView',
    'WorkgroupDeleteView',
    'LocationManagementView',
    'BuildingCreateView',
    'BuildingUpdateView',
    'BuildingDeleteView',
    'RoomCreateView',
    'RoomUpdateView',
    'RoomDeleteView',
    'PhoneNumberCreateView',
    'PhoneNumberUpdateView',
    'PhoneNumberDeleteView',
]