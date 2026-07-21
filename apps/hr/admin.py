"""
apps/hr/admin.py

Project: THERESE – Transparent HR Employee Resource Evaluation System Enhanced
"""

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html, format_html_join

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
    ordering = ('valid_from', 'valid_until', 'pk')
    fields = (
        'job_number',
        'pay_scale_group',
        'experience_level',
        'monthly_salary',
        'weekly_hours',
        'valid_from',
        'valid_until',
        'is_active',
        'comments',
    )
    show_change_link = True


class FundingAllocationInline(admin.TabularInline):
    """
    Uses FundingAllocationForm so PSP elements and cost centers share one
    funding_source dropdown (matches the employee UI form).
    Parent: Contract (not Employee).
    """

    model = FundingAllocation
    form = FundingAllocationForm
    extra = 0
    ordering = ('start_date', 'end_date', 'pk')
    fk_name = 'contract'
    fields = (
        'funding_source',
        'workhours_percentage',
        'plan_position_number',
        'start_date',
        'end_date',
        'is_active',
        'comments',
    )
    show_change_link = True


class SalarySupplementInline(admin.TabularInline):
    model = SalarySupplement
    extra = 0
    fk_name = 'contract'
    fields = ('percentage', 'fixed_amount', 'comment')


class WorkgroupMembershipInline(admin.TabularInline):
    model = Workgroup.members.through
    extra = 0
    verbose_name = 'Workgroup Membership'
    verbose_name_plural = 'Workgroup Memberships'
    autocomplete_fields = ['workgroup']


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
    readonly_fields = ('created_at', 'updated_at', 'document_versions_display')

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
            'Document versions',
            {
                'description': (
                    'Versioned documents are managed in the HR employee form or under '
                    'Employee Document Versions. They are listed here read-only so the '
                    'employee save form is not blocked by file formset management fields.'
                ),
                'fields': ('document_versions_display',),
            },
        ),
        (
            'Legacy files',
            {
                'classes': ('collapse',),
                'description': 'Prefer versioned documents when possible.',
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

    # No EmployeeDocumentVersion TabularInline: file formsets + empty management
    # forms are brittle in admin and produced "missing TOTAL_FORMS" save errors.
    inlines = [
        ContractInline,
        WorkgroupMembershipInline,
    ]

    def get_full_name(self, obj):
        return obj.get_full_name()

    get_full_name.short_description = 'Name'

    @admin.display(description='Document versions')
    def document_versions_display(self, obj):
        if not obj or not obj.pk:
            return 'Save the employee first, then upload documents in the HR form.'

        versions = list(
            obj.document_versions.select_related('uploaded_by').order_by('-created_at')[:40]
        )
        changelist_url = reverse('admin:hr_employeedocumentversion_changelist')
        add_url = reverse('admin:hr_employeedocumentversion_add')

        if not versions:
            return format_html(
                '<p>No document versions yet. '
                '<a href="{}?employee__id__exact={}">Open document list</a> · '
                '<a href="{}">Add document version</a></p>',
                changelist_url,
                obj.pk,
                add_url,
            )

        rows = format_html_join(
            '',
            '<li><a href="{}">{}</a> — {} <span style="color:#64748b;">({})</span></li>',
            (
                (
                    reverse('admin:hr_employeedocumentversion_change', args=[v.pk]),
                    v.get_document_type_display(),
                    v.original_filename,
                    v.created_at.strftime('%d.%m.%Y %H:%M') if v.created_at else '—',
                )
                for v in versions
            ),
        )
        return format_html(
            '<ul style="margin:0 0 0.5rem 1.1rem;">{}</ul>'
            '<p><a href="{}?employee__id__exact={}">All versions</a> · '
            '<a href="{}">Add document version</a></p>',
            rows,
            changelist_url,
            obj.pk,
            add_url,
        )


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
        'pay_scale_group',
        'experience_level',
        'monthly_salary',
        'weekly_hours',
        'valid_from',
        'valid_until',
        'is_active',
    )
    list_filter = ('pay_scale_group', 'is_active')
    search_fields = (
        'employee__employee_number',
        'employee__first_name',
        'employee__last_name',
        'job_number',
    )
    autocomplete_fields = ('employee',)
    fields = (
        'employee',
        'job_number',
        'pay_scale_group',
        'experience_level',
        'monthly_salary',
        'weekly_hours',
        'valid_from',
        'valid_until',
        'is_active',
        'comments',
    )
    inlines = [FundingAllocationInline, SalarySupplementInline]


@admin.register(FundingAllocation, site=therese_admin)
class FundingAllocationAdmin(admin.ModelAdmin):
    form = FundingAllocationForm
    list_display = (
        'employee',
        'contract',
        'funding_target_label',
        'workhours_percentage',
        'plan_position_number',
        'start_date',
        'end_date',
        'is_active',
        'import_completed',
    )
    list_filter = ('start_date', 'is_active', 'import_completed')
    search_fields = (
        'employee__employee_number',
        'employee__first_name',
        'employee__last_name',
        'wbs_element__wbs_code',
        'cost_center__cost_center',
        'plan_position_number',
    )
    autocomplete_fields = ('employee', 'contract')
    fields = (
        'contract',
        'employee',
        'funding_source',
        'workhours_percentage',
        'plan_position_number',
        'start_date',
        'end_date',
        'is_active',
        'comments',
        'import_completed',
    )

    @admin.display(description='PSP / Cost Center')
    def funding_target_label(self, obj):
        return obj.funding_target_label


@admin.register(SalarySupplement, site=therese_admin)
class SalarySupplementAdmin(admin.ModelAdmin):
    list_display = ('employee', 'contract', 'percentage', 'fixed_amount', 'comment')
    search_fields = (
        'employee__employee_number',
        'employee__first_name',
        'employee__last_name',
    )
    autocomplete_fields = ('employee', 'contract')
    fields = ('contract', 'employee', 'percentage', 'fixed_amount', 'comment')


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
