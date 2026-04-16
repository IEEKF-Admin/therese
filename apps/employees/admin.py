from django.contrib import admin
from django import forms
from .models import PayScale, Employee
from apps.contracts.models import Contract
from apps.allocations.models import FundingAllocation


# ==================== Contract Inline ====================
class ContractForm(forms.ModelForm):
    class Meta:
        model = Contract
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        groups = PayScale.objects.values_list('pay_scale_group', flat=True).distinct().order_by('pay_scale_group')
        self.fields['pay_scale_group'].widget = forms.Select(
            choices=[('', '---------')] + [(g, g) for g in groups]
        )
        
        levels = PayScale.objects.values_list('experience_level', flat=True).distinct().order_by('experience_level')
        self.fields['experience_level'].widget = forms.Select(
            choices=[('', '---------')] + [(lvl, lvl) for lvl in levels]
        )


class ContractInline(admin.TabularInline):
    model = Contract
    form = ContractForm
    extra = 1
    show_change_link = True
    fields = ['pay_scale_group', 'experience_level', 'weekly_hours', 'valid_from', 'valid_until', 'comments']
    readonly_fields = ['is_current']


# ==================== FundingAllocation Inline ====================
class FundingAllocationInline(admin.TabularInline):
    model = FundingAllocation
    extra = 2
    show_change_link = True
    fields = ['psp_element', 'weekly_hours_allocated', 'start_date', 'end_date', 'comments']
    
    # Das ForeignKey-Feld 'employee' wird nicht angezeigt
    fk_name = 'employee'   # Wichtig: sagt Django, welches Feld der Parent-Link ist

    def save_formset(self, request, form, formset, change):
        """Mitarbeiter automatisch zuweisen"""
        instances = formset.save(commit=False)
        for instance in instances:
            if not instance.pk:  # Nur bei neuen Einträgen
                instance.employee = form.instance
            instance.save()
        formset.save_m2m()


# ==================== Employee Admin ====================
@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ['employee_number', 'first_name', 'last_name']
    search_fields = ['first_name', 'last_name', 'employee_number']
    
    inlines = [ContractInline, FundingAllocationInline]
