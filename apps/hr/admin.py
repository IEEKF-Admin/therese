"""
apps/hr/admin.py

Project: THERESE – Transparent HR Employee Resource Evaluation System Enhanced
"""

from django.contrib import admin

from therese.admin import therese_admin

from .forms import ContractForm, FundingAllocationForm
from .models import (
    Building,
    Contract,
    Employee,
    EmployeeDocumentVersion,
    FundingAllocation,
    PhoneNumber,
    Room,
    SalarySupplement,
    Workgroup,
)


# = Inlines =


class ContractInline(admin.TabularInline):
    model = Contract
    form = ContractForm
    extra = 0
    fields = (
        'job_number',
        'plan_position_number',
        'pay_scale_group',
        'experience_level',
        'monthly_salary',
        'weekly_hours',
        'valid_from',
        'valid_until',
        'comments',
    )
    show_change_link = True


class FundingAllocationInline(admin.TabularInline):
    """
    Uses FundingAllocationForm so PSP elements and cost centers share one
    funding_source dropdown (matches the employee UI form).
    """

    model = FundingAllocation
    form = FundingAllocationForm
    extra = 0
    fields = (
        'funding_source',
        'weekly_hours_allocated',
        'start_date',
        'end_date',
        'comments',
    )
    show_change_link = True


class SalarySupplementInline(admin.TabularInline):
    model = SalarySupplement
    extra = 0
    fields = ('percentage', 'comment')


class WorkgroupMembershipInline(admin.TabularInline):
    model = Workgroup.members.through
    extra = 0
    verbose_name = 'Workgroup Membership'
    verbose_name_plural = 'Workgroup Memberships'
    autocomplete_fields = ['workgroup']


class EmployeeDocumentVersionInline(admin.TabularInline):
    model = EmployeeDocumentVersion
    fk_name = 'employee'
    extra = 0
    fields = ('document_type', 'file', 'original_filename', 'uploaded_by', 'created_at')
    readonly_fields = ('original_filename', 'created_at')
    autocomplete_fields = ('uploaded_by',)
    show_change_link = True


# = Employee Admin =


@admin.register(Employee, site=therese_admin)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = (
        'employee_number',
        'get_full_name',
        'gender',
        'email_professional',
        'job',
        'room',
        'cost_center',
        'user',
    )
    list_filter = ('gender', 'room__building', 'cost_center', 'job')
    search_fields = (
        'employee_number',
        'first_name',
        'last_name',
        'email_professional',
        'email_private',
        'user__username',
    )
    autocomplete_fields = ('user', 'room', 'job', 'cost_center')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        (
            'Identity',
            {
                'fields': (
                    'employee_number',
                    'user',
                    'prefix',
                    'first_name',
                    'last_name',
                    'gender',
                    'date_of_birth',
                    'country_of_origin',
                    'place_of_birth',
                ),
            },
        ),
        (
            'Contact',
            {
                'fields': (
                    'email_professional',
                    'email_private',
                    'google_account',
                    'private_phone_number',
                    'website',
                ),
            },
        ),
        (
            'Office',
            {
                'fields': ('room', 'phone_number'),
            },
        ),
        (
            'Address',
            {
                'fields': (
                    'street',
                    'house_number',
                    'postal_code',
                    'city',
                    'country',
                ),
            },
        ),
        (
            'Employment / Finance (legacy on employee)',
            {
                'classes': ('collapse',),
                'description': (
                    'Monthly salary for calculations comes from the current contract. '
                    'Employee.monthly_salary is legacy and optional.'
                ),
                'fields': ('job', 'cost_center', 'monthly_salary'),
            },
        ),
        (
            'Legacy files',
            {
                'classes': ('collapse',),
                'description': 'Prefer versioned documents below when possible.',
                'fields': ('scan_of_contract', 'profile_picture'),
            },
        ),
        (
            'Timestamps',
            {
                'classes': ('collapse',),
                'fields': ('created_at', 'updated_at'),
            },
        ),
    )

    inlines = [
        ContractInline,
        FundingAllocationInline,
        SalarySupplementInline,
        WorkgroupMembershipInline,
        EmployeeDocumentVersionInline,
    ]

    def get_full_name(self, obj):
        return obj.get_full_name()

    get_full_name.short_description = 'Name'


@admin.register(Workgroup, site=therese_admin)
class WorkgroupAdmin(admin.ModelAdmin):
    list_display = ['short_name', 'long_name', 'pi', 'member_count']
    list_filter = ['pi']
    search_fields = ['short_name', 'long_name']
    filter_horizontal = ['members']
    autocomplete_fields = ['pi']

    def member_count(self, obj):
        return obj.members.count()

    member_count.short_description = 'Members'


@admin.register(Building, site=therese_admin)
class BuildingAdmin(admin.ModelAdmin):
    list_display = ('number', 'name', 'address')
    search_fields = ('number', 'name', 'address')


@admin.register(Room, site=therese_admin)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('room_number', 'building', 'colloquial_name')
    list_filter = ('building',)
    search_fields = ('room_number', 'colloquial_name', 'building__number', 'building__name')
    autocomplete_fields = ('building',)


@admin.register(PhoneNumber, site=therese_admin)
class PhoneNumberAdmin(admin.ModelAdmin):
    list_display = ('phone_number', 'room')
    search_fields = ('phone_number', 'room__room_number')
    autocomplete_fields = ('room',)


@admin.register(Contract, site=therese_admin)
class ContractAdmin(admin.ModelAdmin):
    form = ContractForm
    list_display = (
        'employee',
        'job_number',
        'plan_position_number',
        'pay_scale_group',
        'experience_level',
        'monthly_salary',
        'weekly_hours',
        'valid_from',
        'valid_until',
    )
    list_filter = ('pay_scale_group',)
    search_fields = (
        'employee__employee_number',
        'employee__first_name',
        'employee__last_name',
        'job_number',
        'plan_position_number',
    )
    autocomplete_fields = ('employee',)
    fields = (
        'employee',
        'job_number',
        'plan_position_number',
        'pay_scale_group',
        'experience_level',
        'monthly_salary',
        'weekly_hours',
        'valid_from',
        'valid_until',
        'comments',
    )


@admin.register(FundingAllocation, site=therese_admin)
class FundingAllocationAdmin(admin.ModelAdmin):
    form = FundingAllocationForm
    list_display = (
        'employee',
        'funding_target_label',
        'weekly_hours_allocated',
        'start_date',
        'end_date',
    )
    list_filter = ('start_date',)
    search_fields = (
        'employee__employee_number',
        'employee__first_name',
        'employee__last_name',
        'wbs_element__wbs_code',
        'cost_center__cost_center',
    )
    autocomplete_fields = ('employee',)
    fields = (
        'employee',
        'funding_source',
        'weekly_hours_allocated',
        'start_date',
        'end_date',
        'comments',
    )

    @admin.display(description='PSP / Cost Center')
    def funding_target_label(self, obj):
        return obj.funding_target_label


@admin.register(SalarySupplement, site=therese_admin)
class SalarySupplementAdmin(admin.ModelAdmin):
    list_display = ('employee', 'percentage', 'comment')
    search_fields = (
        'employee__employee_number',
        'employee__first_name',
        'employee__last_name',
    )
    autocomplete_fields = ('employee',)


@admin.register(EmployeeDocumentVersion, site=therese_admin)
class EmployeeDocumentVersionAdmin(admin.ModelAdmin):
    list_display = (
        'employee',
        'document_type',
        'original_filename',
        'uploaded_by',
        'created_at',
    )
    list_filter = ('document_type',)
    search_fields = (
        'employee__employee_number',
        'employee__first_name',
        'employee__last_name',
        'original_filename',
    )
    autocomplete_fields = ('employee', 'uploaded_by')
    readonly_fields = ('original_filename', 'created_at', 'updated_at')
