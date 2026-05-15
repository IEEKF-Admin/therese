"""
apps/hr/admin.py

Project: THERESE – Transparent HR Employee Resource Evaluation System Enhanced
"""

from django.contrib import admin
from django import forms
from .models import (
    Employee, Building, Room, PhoneNumber, Contract, 
    FundingAllocation, SalarySupplement, Workgroup
)
from apps.finances.models import PayScale, WBSElement


# ====================== Inlines ======================

class PhoneNumberInline(admin.TabularInline):
    model = PhoneNumber
    extra = 1


class ContractInline(admin.TabularInline):
    model = Contract
    extra = 1


class FundingAllocationInline(admin.TabularInline):
    model = FundingAllocation
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


# ====================== Employee Admin ======================

@admin.register(Employee)
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


@admin.register(Workgroup)
class WorkgroupAdmin(admin.ModelAdmin):
    list_display = ['short_name', 'long_name', 'pi', 'member_count']
    list_filter = ['pi']
    search_fields = ['short_name', 'long_name']
    filter_horizontal = ['members']

    def member_count(self, obj):
        return obj.members.count()
    member_count.short_description = 'Members'


# Weitere Register
admin.site.register(Building)
admin.site.register(Room)
admin.site.register(PhoneNumber)
admin.site.register(Contract)
admin.site.register(FundingAllocation)
admin.site.register(SalarySupplement)