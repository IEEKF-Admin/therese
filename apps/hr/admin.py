"""
apps/hr/admin.py

Project: THERESE – Transparent HR Employee Resource Evaluation System Enhanced
"""

from django.contrib import admin
from django import forms
from therese.admin import therese_admin
from .models import (
    Employee, Building, Room, PhoneNumber, Contract,
    FundingAllocation, SalarySupplement, Workgroup,
    EmployeeDocumentVersion,
)
from apps.finances.models import PayScale
from .forms import FundingAllocationForm


# = Inlines =

class PhoneNumberInline(admin.TabularInline):
    model = PhoneNumber
    extra = 1


class ContractInline(admin.TabularInline):
    model = Contract
    extra = 1
    fields = [
        'job_number', 'plan_position_number', 'pay_scale_group', 'experience_level',
        'monthly_salary', 'weekly_hours', 'valid_from', 'valid_until', 'comments',
    ]
    readonly_fields = []


class FundingAllocationInline(admin.TabularInline):
    model = FundingAllocation
    form = FundingAllocationForm
    extra = 1


class SalarySupplementInline(admin.TabularInline):
    model = SalarySupplement
    extra = 1


class WorkgroupMembershipInline(admin.TabularInline):
    model = Workgroup.members.through
    extra = 1
    verbose_name = "Workgroup Membership"
    verbose_name_plural = "Workgroup Memberships"
    autocomplete_fields = ['workgroup']


# = Employee Admin =

@admin.register(Employee, site=therese_admin)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('employee_number', 'get_full_name', 'gender', 'email_professional', 
                   'room', 'cost_center')
    list_filter = ('gender', 'room__building', 'cost_center')
    search_fields = ('employee_number', 'first_name', 'last_name', 'email_professional')

    inlines = [
        ContractInline,
        FundingAllocationInline,
        SalarySupplementInline,
        WorkgroupMembershipInline,      # ← Jetzt funktioniert es
    ]


@admin.register(Workgroup, site=therese_admin)
class WorkgroupAdmin(admin.ModelAdmin):
    list_display = ['short_name', 'long_name', 'pi', 'member_count']
    list_filter = ['pi']
    search_fields = ['short_name', 'long_name']
    filter_horizontal = ['members']

    def member_count(self, obj):
        return obj.members.count()
    member_count.short_description = 'Members'


# Weitere Register
therese_admin.register(Building)
therese_admin.register(Room)
therese_admin.register(PhoneNumber)
therese_admin.register(Contract)
therese_admin.register(FundingAllocation)
therese_admin.register(SalarySupplement)
therese_admin.register(EmployeeDocumentVersion)

