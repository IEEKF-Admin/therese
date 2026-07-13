"""
apps/tasks/forms.py
Project: THERESE – Transparent HR Resource System Enhanced
"""
from django import forms
from django.forms.models import BaseInlineFormSet, inlineformset_factory
from .models import (
    PurchaseOrderTask,
    PurchaseItem,
    PersonnelReallocationTask,
    PersonnelContractExtensionTask,
    PersonnelRecruitmentTask,
    RecruitmentFundingAllocation,
    RecruitmentJob,
    LimitationReason,
    GenericTextTask,
    StandardPurchaseItem,
    PURCHASE_STATUSES,
    GENERIC_STATUSES,
    PERSONNEL_STATUSES,
    RECRUITMENT_STATUSES,
    RECRUITMENT_STATUS_ORDER,
)
from apps.finances.models import PayScale, WBSElement
from apps.hr.models import Employee, Gender
from apps.hr.document_utils import validate_personnel_document
from .recruitment_form_helpers import (
    add_limitation_reason_template_field,
    apply_recruitment_field_defaults,
    configure_recruitment_job_field,
    strip_limitation_reason_template,
    validate_recruitment_dynamic_rules,
)
from .recruitment_upload_cache import apply_stashed_uploads
from .utils import (
    procurement_approver_employees,
    personnel_approver_employees,
    is_personnel_coordinator,
    is_personnel_approver,
    get_recruitment_status_choices,
)


class PurchaseOrderTaskForm(forms.ModelForm):
    """
    Formular für Purchase Orders mit Radio-Buttons für Status.
    """
    class Meta:
        model = PurchaseOrderTask
        fields = ['supplier', 'wbs_element', 'priority', 'assignee', 'status', 'comment', 'at_beleg_nummer']
        widgets = {
            'comment': forms.Textarea(attrs={'rows': 4}),
            'status': forms.RadioSelect(attrs={'class': 'status-radio'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.is_creation = kwargs.pop('is_creation', False)
        super().__init__(*args, **kwargs)

        # ====== Supplier ======
        if 'supplier' in self.fields:
            if not self.is_creation and self.user and self.user.has_perm('tasks.view_all_purchase_orders'):
                self.fields['supplier'].widget = forms.HiddenInput()
                if self.instance and self.instance.pk:
                    self.fields['supplier'].initial = self.instance.supplier
                self.fields['supplier'].required = True
            else:
                self.fields['supplier'].widget.attrs.update({'class': 'form-control'})
                if self.is_creation:
                    self.fields['supplier'].required = True

        # ====== Priority & Comment (creation rules) ======
        if 'priority' in self.fields:
            self.fields['priority'].required = False
            self.fields['priority'].widget.attrs.update({'class': 'form-control'})

        if 'comment' in self.fields:
            self.fields['comment'].required = False

        # ====== Assignee ======
        if 'assignee' in self.fields:
            # Users without full PO access should not see the Assignee dropdown
            if self.user and (
                not self.user.has_perm('tasks.view_all_purchase_orders') and
                not self.user.has_perm('tasks.change_wbs_on_purchase_order')
            ):
                self.fields['assignee'].widget = forms.HiddenInput()
                self.fields['assignee'].required = False
                if self.is_creation:
                    self.fields['assignee'].initial = None  # bleibt unassigned, bis Coordinator/Approver es setzt

            else:
                # Coordinators wählen Assignee aus Procurement Approvers
                self.fields['assignee'].queryset = procurement_approver_employees()
                self.fields['assignee'].widget.attrs.update({'class': 'form-control'})
                self.fields['assignee'].empty_label = "— Select assignee —"
                if self.is_creation:
                    self.fields['assignee'].required = True

        # ====== AT - Beleg Nummer ======
        if 'at_beleg_nummer' in self.fields:
            if self.is_creation:
                self.fields['at_beleg_nummer'].widget = forms.HiddenInput()
                self.fields['at_beleg_nummer'].required = False
            elif self.user and not (
                self.user.has_perm('tasks.view_all_purchase_orders') or
                self.user.has_perm('tasks.manage_standard_order')
            ):
                self.fields['at_beleg_nummer'].widget = forms.HiddenInput()
                self.fields['at_beleg_nummer'].required = False
            else:
                self.fields['at_beleg_nummer'].widget.attrs.update({'class': 'form-control'})

        # ====== Status ======
        if 'status' in self.fields:
            self.fields['status'].choices = PURCHASE_STATUSES

            if self.is_creation:
                self.fields['status'].widget = forms.HiddenInput()
                self.fields['status'].initial = 'not_yet_processed'
                self.fields['status'].required = True
                if self.data:
                    self.data = self.data.copy()
                    self.data['status'] = 'not_yet_processed'
            # else: Radio Buttons bleiben (wird im Template manuell gerendert)

        # ====== WBS Element ======
        if 'wbs_element' in self.fields:
            self.fields['wbs_element'].queryset = WBSElement.objects.active().filter(
                wbs_code__regex=r'.*-\d+\.\d+\.1$'
            ).order_by('wbs_code')
            self.fields['wbs_element'].empty_label = "---------"

            if not self.is_creation and self.user and self.user.has_perm('tasks.view_all_purchase_orders'):
                # Users with view all permission can change WBS
                pass
            elif self.is_creation:
                self.fields['wbs_element'].widget = forms.HiddenInput()
                self.fields['wbs_element'].required = False

    def clean(self):
        cleaned_data = super().clean()
        wbs_element = cleaned_data.get('wbs_element')

        if (
            not self.is_creation
            and self.user
            and self.user.has_perm('tasks.view_all_purchase_orders')
        ):
            if not wbs_element:
                self.add_error('wbs_element', "WBS Element is required for users with full purchase order access.")

        return cleaned_data


# = Weitere Formulare =
class PurchaseItemForm(forms.ModelForm):
    class Meta:
        model = PurchaseItem
        fields = ['product_name', 'product_description', 'link_to_product', 'order_number', 'unit_price', 'quantity']
        widgets = {
            'product_description': forms.Textarea(attrs={'rows': 2}),
            'link_to_product': forms.URLInput(attrs={'placeholder': 'https://...'}),
            'order_number': forms.TextInput(attrs={'placeholder': 'z.B. 4711'}),
            'quantity': forms.NumberInput(attrs={'min': 1, 'step': 1}),
        }

    OPTIONAL_FIELDS = {'product_description'}
    INTERNAL_FIELDS = {'id', 'purchase_task', 'DELETE'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.empty_permitted = True
        for field_name, field in self.fields.items():
            if field_name in self.INTERNAL_FIELDS:
                field.required = False
            else:
                field.required = field_name not in self.OPTIONAL_FIELDS
            if field_name == 'order_number':
                field.widget.attrs['placeholder'] = 'z.B. 4711'
            if field_name == 'quantity':
                field.widget.attrs['min'] = 1
                field.widget.attrs['step'] = 1

    def _is_empty_row(self, cleaned_data=None):
        if cleaned_data is not None:
            if not cleaned_data:
                return True
            for field_name, value in cleaned_data.items():
                if field_name in self.OPTIONAL_FIELDS or field_name in self.INTERNAL_FIELDS:
                    continue
                if value not in (None, ''):
                    return False
            return True

        if not self.is_bound:
            return False
        for field_name in self.fields:
            if field_name in self.OPTIONAL_FIELDS or field_name in self.INTERNAL_FIELDS:
                continue
            if self.data.get(self.add_prefix(field_name), '') not in ('', None):
                return False
        return True

    def full_clean(self):
        if self._is_empty_row():
            self.cleaned_data = {}
            self._errors = {}
            return
        super().full_clean()

    def clean(self):
        cleaned_data = super().clean()
        if self._is_empty_row(cleaned_data):
            return cleaned_data
        for field_name in self.fields:
            if field_name in self.OPTIONAL_FIELDS or field_name in self.INTERNAL_FIELDS:
                continue
            if cleaned_data.get(field_name) in (None, ''):
                self.add_error(field_name, 'This field is required.')
        return cleaned_data


class BasePurchaseItemFormSet(BaseInlineFormSet):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for form in self.forms:
            form.empty_permitted = True

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        active_forms = [
            form for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get('DELETE', False)
            and not form._is_empty_row(form.cleaned_data)
        ]
        if not active_forms:
            raise forms.ValidationError('At least one purchase item is required.')


def _configure_gender_field(form, required=True):
    """Match the Gender dropdown used on the Employee form."""
    form.fields['gender'] = forms.ChoiceField(
        label=Employee._meta.get_field('gender').verbose_name,
        choices=Gender.choices,
        required=required,
        widget=forms.Select(attrs={'class': 'form-control'}),
    )


def _configure_personnel_assignee_field(form):
    """Assignee nur für Personnel Coordinators sichtbar; Kandidaten = Personnel Approvers."""
    if 'assignee' not in form.fields:
        return

    form.fields['assignee'].queryset = personnel_approver_employees()
    form.fields['assignee'].empty_label = "— Select assignee —"

    is_coordinator = (
        form.user
        and (form.user.is_superuser or form.user.has_perm('tasks.view_all_personnel_tasks'))
    )
    if is_coordinator:
        form.fields['assignee'].widget.attrs.update({'class': 'form-control'})
    else:
        form.fields['assignee'].widget = forms.HiddenInput()
        form.fields['assignee'].required = False


class PersonnelReallocationTaskForm(forms.ModelForm):
    """
    Form for Personnel Reallocation tasks.
    No title (auto-generated), no assignee/priority/due_date at creation time.
    The entire "Assignment & Priority" card is omitted in the template.
    Comment/Notes gets full width.
    """
    class Meta:
        model = PersonnelReallocationTask
        fields = ['employee', 'target_wbs', 'valid_from', 'valid_until',
                  'plan_position_number', 'assignee', 'status', 'comment']
        widgets = {
            'comment': forms.Textarea(attrs={'rows': 6, 'placeholder': 'Add any additional notes or context for this reallocation...'}),
            'valid_from': forms.DateInput(attrs={
                'type': 'text',
                'class': 'form-control date-picker',
                'placeholder': 'TT.MM.JJJJ'
            }),
            'valid_until': forms.DateInput(attrs={
                'type': 'text',
                'class': 'form-control date-picker',
                'placeholder': 'TT.MM.JJJJ'
            }),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.is_creation = kwargs.pop('is_creation', False)
        super().__init__(*args, **kwargs)

        # Status is always hidden for personnel tasks (set at creation)
        if 'status' in self.fields:
            self.fields['status'].choices = PERSONNEL_STATUSES
            if self.is_creation:
                self.fields['status'].widget = forms.HiddenInput()
                self.fields['status'].initial = 'not_yet_processed'
                self.fields['status'].required = True
                if self.data:
                    self.data = self.data.copy()
                    self.data['status'] = 'not_yet_processed'

        # Style inputs
        for field_name in ['employee', 'target_wbs', 'plan_position_number']:
            if field_name in self.fields:
                self.fields[field_name].widget.attrs.update({'class': 'form-control'})
                self.fields[field_name].required = True

        for field_name in ['valid_from', 'valid_until']:
            if field_name in self.fields:
                self.fields[field_name].widget.attrs.update({'class': 'form-control'})

        if 'comment' in self.fields:
            self.fields['comment'].widget.attrs.update({'class': 'form-control'})

        # Employee dropdown (all employees)
        if 'employee' in self.fields:
            self.fields['employee'].queryset = Employee.objects.order_by('last_name', 'first_name')
            self.fields['employee'].empty_label = "— Select employee —"

        # Target WBS (reasonable WBS elements)
        if 'target_wbs' in self.fields:
            self.fields['target_wbs'].queryset = WBSElement.objects.active().order_by('wbs_code')
            self.fields['target_wbs'].empty_label = "— Select target WBS —"

        _configure_personnel_assignee_field(self)


class PersonnelContractExtensionTaskForm(forms.ModelForm):
    """
    Form for Personnel Contract Extension tasks.
    No title (auto-generated), no assignee/priority/due_date at creation time.
    The entire "Assignment & Priority" card is omitted in the template.
    Comment/Notes gets full width.
    """
    class Meta:
        model = PersonnelContractExtensionTask
        fields = ['employee', 'plan_position_number', 'valid_from', 'valid_until',
                  'is_limited', 'limitation_reason', 'assignee', 'status', 'comment']
        widgets = {
            'comment': forms.Textarea(attrs={'rows': 6, 'placeholder': 'Add any additional notes or context for this contract extension...'}),
            'valid_from': forms.DateInput(attrs={
                'type': 'text',
                'class': 'form-control date-picker',
                'placeholder': 'TT.MM.JJJJ'
            }),
            'valid_until': forms.DateInput(attrs={
                'type': 'text',
                'class': 'form-control date-picker',
                'placeholder': 'TT.MM.JJJJ'
            }),
            'limitation_reason': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.is_creation = kwargs.pop('is_creation', False)
        super().__init__(*args, **kwargs)

        # Status is always hidden for personnel tasks (set at creation)
        if 'status' in self.fields:
            self.fields['status'].choices = PERSONNEL_STATUSES
            if self.is_creation:
                self.fields['status'].widget = forms.HiddenInput()
                self.fields['status'].initial = 'not_yet_processed'
                self.fields['status'].required = True
                if self.data:
                    self.data = self.data.copy()
                    self.data['status'] = 'not_yet_processed'

        # Style inputs
        for field_name in ['employee', 'plan_position_number']:
            if field_name in self.fields:
                self.fields[field_name].widget.attrs.update({'class': 'form-control'})
                self.fields[field_name].required = True

        if 'valid_from' in self.fields:
            self.fields['valid_from'].widget.attrs.update({'class': 'form-control'})

        if 'comment' in self.fields:
            self.fields['comment'].widget.attrs.update({'class': 'form-control'})

        if 'limitation_reason' in self.fields:
            self.fields['limitation_reason'].widget.attrs.update({'class': 'form-control'})

        # Employee dropdown (all employees)
        if 'employee' in self.fields:
            self.fields['employee'].queryset = Employee.objects.order_by('last_name', 'first_name')
            self.fields['employee'].empty_label = "— Select employee —"

        # is_limited default True for new limited contracts
        if 'is_limited' in self.fields and self.is_creation:
            self.fields['is_limited'].initial = True
            self.fields['is_limited'].label = ""  # label rendered manually in template for nicer checkbox UX
        if 'status' in self.fields:
            self.fields['status'].choices = PERSONNEL_STATUSES
            if self.is_creation:
                self.fields['status'].widget = forms.HiddenInput()
                self.fields['status'].initial = 'not_yet_processed'
                self.fields['status'].required = True

        # Styling
        for fname in ['plan_position_number', 'priority', 'assignee', 'employee']:
            if fname in self.fields:
                self.fields[fname].widget.attrs.update({'class': 'form-control'})

        for fname in ['valid_from', 'due_date', 'comment', 'limitation_reason']:
            if fname in self.fields:
                self.fields[fname].widget.attrs.update({'class': 'form-control'})

        if 'employee' in self.fields:
            self.fields['employee'].queryset = Employee.objects.order_by('last_name', 'first_name')

        _configure_personnel_assignee_field(self)
        add_limitation_reason_template_field(self, include_all_reasons=True)

        if 'limitation_reason' in self.fields:
            self.fields['limitation_reason'].widget = forms.Textarea(attrs={
                'class': 'form-control limitation-reason-text',
                'rows': 3,
                'data-limitation-text': 'true',
            })


class RecruitmentFundingAllocationForm(forms.ModelForm):
    class Meta:
        model = RecruitmentFundingAllocation
        fields = ['wbs_element', 'weekly_hours_allocated']
        widgets = {
            'weekly_hours_allocated': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['wbs_element'].queryset = WBSElement.objects.active().order_by('wbs_code')
        self.fields['wbs_element'].empty_label = '— Select WBS —'
        self.fields['wbs_element'].widget.attrs.update({'class': 'form-control'})
        self.fields['wbs_element'].required = True
        self.fields['weekly_hours_allocated'].required = True
        self.empty_permitted = True

    def _is_empty_row(self, cleaned_data=None):
        if cleaned_data is not None:
            if not cleaned_data:
                return True
            return (
                not cleaned_data.get('wbs_element')
                and cleaned_data.get('weekly_hours_allocated') in (None, '')
            )
        if not self.is_bound:
            return not (self.instance and self.instance.pk)
        wbs = self.data.get(self.add_prefix('wbs_element'), '').strip()
        hours = self.data.get(self.add_prefix('weekly_hours_allocated'), '').strip()
        return not wbs and not hours

    def clean(self):
        cleaned_data = super().clean()
        if self._is_empty_row(cleaned_data):
            if cleaned_data is not None:
                cleaned_data['DELETE'] = True
            return cleaned_data
        if not cleaned_data.get('wbs_element'):
            self.add_error('wbs_element', 'WBS Element is required.')
        if cleaned_data.get('weekly_hours_allocated') in (None, ''):
            self.add_error('weekly_hours_allocated', 'Weekly working hours are required.')
        return cleaned_data


class BaseRecruitmentFundingFormSet(BaseInlineFormSet):
    def __init__(self, *args, job=None, contract_dates=None, is_creation=True, **kwargs):
        self.job = job
        self.contract_dates = contract_dates or {}
        self.is_creation = is_creation
        super().__init__(*args, **kwargs)

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        from .recruitment_form_helpers import validate_funding_allocations_required

        validate_funding_allocations_required(
            self,
            self.job,
            self.contract_dates,
            is_creation=self.is_creation,
        )


RecruitmentFundingFormSet = inlineformset_factory(
    PersonnelRecruitmentTask,
    RecruitmentFundingAllocation,
    form=RecruitmentFundingAllocationForm,
    formset=BaseRecruitmentFundingFormSet,
    extra=1,
    can_delete=True,
    min_num=0,
    validate_min=False,
)


class PersonnelRecruitmentTaskForm(forms.ModelForm):
    class Meta:
        model = PersonnelRecruitmentTask
        fields = [
            'prefix', 'first_name', 'last_name', 'gender', 'date_of_birth',
            'country_of_origin', 'place_of_birth', 'email_private',
            'private_phone_number', 'street', 'house_number', 'postal_code',
            'city', 'country', 'job', 'plan_position_number',
            'valid_from', 'valid_until', 'limitation_reason',
            'cv_file', 'latest_degree_certificate_file',
            'assignee', 'status', 'comment',
        ]
        widgets = {
            'comment': forms.Textarea(attrs={'rows': 6}),
            'valid_from': forms.DateInput(attrs={
                'type': 'text',
                'class': 'form-control date-picker',
                'placeholder': 'TT.MM.JJJJ',
                'data-contract-date': 'true',
            }),
            'valid_until': forms.DateInput(attrs={
                'type': 'text',
                'class': 'form-control date-picker',
                'placeholder': 'TT.MM.JJJJ',
                'data-contract-date': 'true',
            }),
            'date_of_birth': forms.DateInput(attrs={
                'type': 'text',
                'class': 'form-control date-picker',
                'placeholder': 'TT.MM.JJJJ',
            }),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.is_creation = kwargs.pop('is_creation', False)
        self.stashed_uploads = kwargs.pop('stashed_uploads', None) or {}
        super().__init__(*args, **kwargs)

        configure_recruitment_job_field(self)
        apply_recruitment_field_defaults(self, is_creation=self.is_creation)

        for field_name, field in self.fields.items():
            if field_name not in ('status', 'gender', 'job'):
                field.widget.attrs.setdefault('class', 'form-control')
            if field_name not in ('status', 'assignee', 'job'):
                field.widget.attrs.setdefault('data-recruitment-field', field_name)

        _configure_gender_field(self, required=False)

        if 'status' in self.fields:
            if self.is_creation:
                self.fields['status'].choices = RECRUITMENT_STATUSES
                self.fields['status'].widget = forms.HiddenInput()
                self.fields['status'].initial = 'not_yet_processed'
                self.fields['status'].required = True
                if self.data:
                    self.data = self.data.copy()
                    self.data['status'] = 'not_yet_processed'
            elif self.instance and self.instance.pk:
                allowed = get_recruitment_status_choices(self.user, self.instance)
                self.fields['status'].choices = allowed or RECRUITMENT_STATUSES
                can_change_status = (
                    self.user
                    and (
                        self.user.is_superuser
                        or is_personnel_coordinator(self.user)
                        or (
                            is_personnel_approver(self.user)
                            and getattr(self.user, 'employee', None) == self.instance.assignee
                        )
                    )
                )
                if not can_change_status:
                    self.fields['status'].widget = forms.HiddenInput()

        for file_field in ('cv_file', 'latest_degree_certificate_file'):
            if file_field in self.fields:
                self.fields[file_field].widget.attrs['data-recruitment-field'] = file_field

        job_id = None
        if self.data.get('job'):
            job_id = self.data.get('job')
        elif self.instance and self.instance.job_id:
            job_id = self.instance.job_id
        add_limitation_reason_template_field(
            self,
            job_id=job_id if not self.is_creation else None,
            include_all_reasons=self.is_creation,
        )

        _configure_personnel_assignee_field(self)

    def clean(self):
        cleaned_data = super().clean()
        apply_stashed_uploads(cleaned_data, self.stashed_uploads)
        strip_limitation_reason_template(cleaned_data)
        validate_recruitment_dynamic_rules(
            self,
            cleaned_data,
            is_creation=self.is_creation,
            files=getattr(self, 'files', None),
        )

        new_status = cleaned_data.get('status')
        if (
            new_status
            and self.instance
            and self.instance.pk
            and self.user
            and is_personnel_approver(self.user)
            and not is_personnel_coordinator(self.user)
            and getattr(self.user, 'employee', None) == self.instance.assignee
        ):
            try:
                current_index = RECRUITMENT_STATUS_ORDER.index(self.instance.status)
                new_index = RECRUITMENT_STATUS_ORDER.index(new_status)
            except ValueError:
                pass
            else:
                if new_index <= current_index:
                    self.add_error('status', 'Approvers may only move the status forward.')

        return cleaned_data


class RecruitmentJobForm(forms.ModelForm):
    class Meta:
        model = RecruitmentJob
        fields = ['name', 'pay_scale_group', 'experience_level', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': 'Job name',
            'pay_scale_group': 'Pay scale group',
            'experience_level': 'Experience level',
            'is_active': 'Active',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current = PayScale.get_current()
        groups = (
            current.values_list('pay_scale_group', flat=True)
            .distinct()
            .order_by('pay_scale_group')
        )
        pay_scale_choices = [('', '— Select pay scale group —')] + [(g, g) for g in groups]
        level_choices = [('', '— Select group first —')] + [(str(i), str(i)) for i in range(1, 7)]

        self.fields['pay_scale_group'] = forms.ChoiceField(
            choices=pay_scale_choices,
            required=False,
            widget=forms.Select(attrs={'class': 'form-control', 'id': 'job-pay-scale-group'}),
        )
        self.fields['experience_level'] = forms.ChoiceField(
            choices=level_choices,
            required=False,
            widget=forms.Select(attrs={'class': 'form-control', 'id': 'job-experience-level'}),
        )
        if self.instance and self.instance.pk:
            if self.instance.pay_scale_group:
                self.fields['pay_scale_group'].initial = self.instance.pay_scale_group
            if self.instance.experience_level is not None:
                self.fields['experience_level'].initial = str(self.instance.experience_level)

    def clean_experience_level(self):
        value = self.cleaned_data.get('experience_level')
        if value in (None, ''):
            return None
        return int(value)


class LimitationReasonForm(forms.ModelForm):
    class Meta:
        model = LimitationReason
        fields = ['title', 'text', 'applies_to_all_jobs', 'jobs', 'is_active']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'text': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'applies_to_all_jobs': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'jobs': forms.SelectMultiple(attrs={'class': 'form-control', 'size': 8}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'title': 'Title',
            'text': 'Limitation reason text',
            'applies_to_all_jobs': 'Applies to all jobs',
            'jobs': 'Associated jobs',
            'is_active': 'Active',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['jobs'].queryset = RecruitmentJob.objects.filter(is_active=True).order_by('name')
        self.fields['jobs'].required = False


class GenericTextTaskForm(forms.ModelForm):
    """
    Form for General Requests (generic_text tasks).
    Keeps Recipient (addressed to) and removes Assignee (we use Recipient instead).
    """
    class Meta:
        model = GenericTextTask
        fields = ['title', 'recipient', 'priority', 'due_date', 'status', 'comment']
        widgets = {
            'comment': forms.Textarea(attrs={
                'rows': 12,
                'placeholder': 'Describe your request in detail...',
                'style': 'min-height: 200px;'
            }),
            'due_date': forms.DateInput(attrs={
                'type': 'text',
                'class': 'form-control date-picker',
                'placeholder': 'TT.MM.JJJJ'
            }),
            'status': forms.RadioSelect(attrs={'class': 'status-radio'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.is_creation = kwargs.pop('is_creation', False)
        super().__init__(*args, **kwargs)

        # Status handling for generic tasks (new English statuses)
        if 'status' in self.fields:
            self.fields['status'].choices = GENERIC_STATUSES

            if self.is_creation:
                self.fields['status'].widget = forms.HiddenInput()
                self.fields['status'].initial = 'seen'
                self.fields['status'].required = True
                if self.data:
                    self.data = self.data.copy()
                    self.data['status'] = 'seen'

        # Style fields
        for field_name in ['title', 'priority', 'recipient']:
            if field_name in self.fields:
                self.fields[field_name].widget.attrs.update({'class': 'form-control'})

        if 'due_date' in self.fields:
            self.fields['due_date'].widget.attrs.update({'class': 'form-control'})

        if 'comment' in self.fields:
            self.fields['comment'].widget.attrs.update({'class': 'form-control'})

        if 'recipient' in self.fields:
            self.fields['recipient'].queryset = Employee.objects.order_by('last_name', 'first_name')
            self.fields['recipient'].empty_label = "— Please select a recipient —"
            self.fields['recipient'].required = True

            # Custom label without employee number (Personnelnummer)
            def recipient_label_from_instance(employee):
                prefix = f"{employee.prefix} " if employee.prefix else ""
                return f"{prefix}{employee.first_name} {employee.last_name}"

            self.fields['recipient'].label_from_instance = recipient_label_from_instance


# 
# Standard Purchase Items (Catalog)
# 

from django.core.exceptions import ValidationError
from PIL import Image as PILImage
import io

MAX_STANDARD_IMAGE_SIZE_MB = 5
THUMBNAIL_SIZE = (120, 120)


class StandardPurchaseItemForm(forms.ModelForm):
    """Form for creating/editing StandardPurchaseItem with optional image upload."""

    image = forms.FileField(
        label="Product Image (optional)",
        required=False,
        widget=forms.ClearableFileInput(attrs={'class': 'form-control'}),
        help_text=f"Max {MAX_STANDARD_IMAGE_SIZE_MB} MB. Will be shown as small thumbnail in selection lists."
    )

    class Meta:
        model = StandardPurchaseItem
        fields = [
            'supplier', 'product_name', 'product_description',
            'link_to_product', 'order_number', 'unit_price'
        ]
        widgets = {
            'product_description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'link_to_product': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            if field != 'image' and hasattr(self.fields[field].widget, 'attrs'):
                self.fields[field].widget.attrs.setdefault('class', 'form-control')

        # Make some fields required for usability
        self.fields['supplier'].required = True
        self.fields['product_name'].required = True
        self.fields['unit_price'].required = True

    def clean_image(self):
        uploaded_file = self.cleaned_data.get('image')
        if not uploaded_file:
            return None

        # Size check
        max_bytes = MAX_STANDARD_IMAGE_SIZE_MB * 1024 * 1024
        if uploaded_file.size > max_bytes:
            raise ValidationError(f"Image too large. Maximum allowed size is {MAX_STANDARD_IMAGE_SIZE_MB} MB.")

        # Basic image validation + thumbnail generation
        try:
            img = PILImage.open(uploaded_file)
            img.verify()  # Check it's a valid image
            uploaded_file.seek(0)  # Reset after verify

            # Create thumbnail
            img = PILImage.open(uploaded_file)
            img.thumbnail(THUMBNAIL_SIZE, PILImage.LANCZOS)

            # Convert to RGB if necessary (for PNG with alpha etc.)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            thumb_io = io.BytesIO()
            img.save(thumb_io, format='JPEG', quality=85, optimize=True)
            thumb_io.seek(0)

            self.cleaned_data['thumbnail_data'] = thumb_io.getvalue()
            self.cleaned_data['image_content_type'] = uploaded_file.content_type or 'image/jpeg'

            # Reset original file pointer for later reading
            uploaded_file.seek(0)
            return uploaded_file

        except Exception as e:
            raise ValidationError(f"Invalid image file: {str(e)}")

    def save(self, commit=True):
        instance = super().save(commit=False)

        uploaded_file = self.cleaned_data.get('image')
        if uploaded_file:
            instance.image = uploaded_file.read()
            instance.image_filename = uploaded_file.name
            instance.image_content_type = self.cleaned_data.get('image_content_type', 'image/jpeg')
            instance.thumbnail = self.cleaned_data.get('thumbnail_data')

        if commit:
            instance.save()
        return instance

