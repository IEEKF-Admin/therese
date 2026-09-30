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

from .accounts import employee_accounts
from .accounts_bulk import employee_accounts_bulk
from .accounts_import import (
    employee_accounts_import_calendar,
    employee_accounts_import_sympa,
    employee_accounts_import_websites,
)
from .wordpress import wordpress_publish, wordpress_unpublish
from .crud import (
    EmployeeCreateView,
    EmployeeUpdateView,
    MinimalEmployeeCreateView,
    contract_hard_delete,
    employee_list,
    employee_reset_password,
    funding_hard_delete,
    phone_list,
)
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
    RoomStorageItemCreateView,
    RoomStorageItemDeleteView,
    RoomStorageItemUpdateView,
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
    'employee_accounts',
    'employee_accounts_bulk',
    'employee_accounts_import_calendar',
    'employee_accounts_import_websites',
    'employee_accounts_import_sympa',
    'wordpress_publish',
    'wordpress_unpublish',
    'employee_reset_password',
    'contract_hard_delete',
    'funding_hard_delete',
    'phone_list',
    'EmployeeCreateView',
    'MinimalEmployeeCreateView',
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
    'RoomStorageItemCreateView',
    'RoomStorageItemUpdateView',
    'RoomStorageItemDeleteView',
]