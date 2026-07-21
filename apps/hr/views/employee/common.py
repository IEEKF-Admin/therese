"""
Shared helpers for employee views.

Do not remove any existing requirements from this module without explicit instruction.
"""

from django.db import transaction

from ...document_utils import (
    copy_recruitment_documents_to_employee,
    get_document_blocks_for_template,
    process_document_uploads,
    user_can_manage_employee_documents,
)
from apps.tasks.models import PersonnelRecruitmentTask
from apps.tasks.utils import can_create_employee_from_recruitment


def employee_document_context(request, employee=None):
    can_upload = (
        user_can_manage_employee_documents(request.user, employee)
        if employee
        else request.user.has_perm('hr.manage_employee')
    )
    blocks = get_document_blocks_for_template(employee)
    for block in blocks:
        block['can_delete_any'] = request.user.has_perm('hr.manage_employee') or request.user.is_superuser
    return {
        'document_blocks': blocks,
        'can_upload_documents': can_upload,
    }


def _save_nested_on_contract(nested, saved_by_index, *, inactive_skip=True):
    """Save nested formsets keyed as (index, contract_form, formset)."""
    for index, cform, nested_fs in nested:
        if not hasattr(cform, 'cleaned_data') or not cform.cleaned_data:
            continue
        if cform.cleaned_data.get('DELETE'):
            continue
        contract = cform.instance
        if not contract.pk:
            contract = saved_by_index.get(index)
        if contract is None or not contract.pk:
            continue
        if inactive_skip and not contract.is_active:
            continue
        nested_fs.instance = contract
        instances = nested_fs.save(commit=False)
        for obj in instances:
            obj.contract = contract
            obj.employee = contract.employee
            if hasattr(obj, 'is_active') and not contract.is_active:
                obj.is_active = False
            obj.save()
        for obj in nested_fs.deleted_objects:
            obj.delete()
        nested_fs.save_m2m()


def save_employee_with_formsets(
    request,
    form,
    formsets,
    nested_funding=None,
    nested_salary=None,
):
    """
    Save employee + contract formset + nested FA/salary formsets + workgroups.

    ``formsets``: (contract_formset, workgroup_formset)
    ``nested_funding`` / ``nested_salary``: list of (index, contract_form, formset)
    """
    from apps.hr.views.employee_form_helpers import validate_active_contract_funding_totals

    contract_formset, workgroup_formset = formsets
    nested_funding = nested_funding or []
    nested_salary = nested_salary or []

    if not form.is_valid():
        return None, ['Please correct the employee fields.']

    if not contract_formset.is_valid():
        return None, ['Please correct errors in Contracts.']

    for _, _, fa_fs in nested_funding:
        if not fa_fs.is_valid():
            return None, ['Please correct errors in Funding Allocations.']

    for _, _, ss_fs in nested_salary:
        if not ss_fs.is_valid():
            return None, ['Please correct errors in Salary Supplements.']

    if not workgroup_formset.is_valid():
        return None, ['Please correct errors in Workgroup memberships.']

    pct_errors = validate_active_contract_funding_totals(contract_formset, nested_funding)
    if pct_errors:
        return None, pct_errors

    with transaction.atomic():
        employee = form.save()
        contract_formset.instance = employee
        contract_formset.save()

        saved_by_index = {}
        form_index = 0
        for cform in contract_formset.forms:
            if not hasattr(cform, 'cleaned_data') or not cform.cleaned_data:
                form_index += 1
                continue
            if cform.cleaned_data.get('DELETE'):
                form_index += 1
                continue
            saved_by_index[form_index] = cform.instance
            form_index += 1

        _save_nested_on_contract(nested_funding, saved_by_index, inactive_skip=True)
        _save_nested_on_contract(nested_salary, saved_by_index, inactive_skip=True)

        workgroup_formset.instance = employee
        workgroup_formset.save()

        uploader = getattr(request.user, 'employee', None)
        process_document_uploads(request, employee, uploaded_by=uploader)

    return employee, []


def get_recruitment_task(request):
    task_pk = request.GET.get('from_recruitment_task')
    if not task_pk:
        return None
    try:
        return PersonnelRecruitmentTask.objects.select_related('job').get(pk=task_pk)
    except PersonnelRecruitmentTask.DoesNotExist:
        return None


def recruitment_employee_initial(task):
    initial = {
        'prefix': task.prefix,
        'first_name': task.first_name,
        'last_name': task.last_name,
        'gender': task.gender,
        'date_of_birth': task.date_of_birth,
        'country_of_origin': task.country_of_origin,
        'place_of_birth': task.place_of_birth,
        'email_private': task.email_private,
        'private_phone_number': task.private_phone_number,
        'street': task.street,
        'house_number': task.house_number,
        'postal_code': task.postal_code,
        'city': task.city,
        'country': task.country,
    }
    if task.job_id:
        initial['job'] = task.job_id
    return initial


def recruitment_contract_initial(task):
    contract_data = {
        'valid_from': task.valid_from,
        'valid_until': task.valid_until,
        'is_active': True,
    }
    if task.pay_scale_group:
        contract_data['pay_scale_group'] = task.pay_scale_group
    elif task.job and task.job.pay_scale_group:
        contract_data['pay_scale_group'] = task.job.pay_scale_group
    if task.experience_level is not None:
        contract_data['experience_level'] = str(task.experience_level)
    elif task.job and task.job.experience_level is not None:
        contract_data['experience_level'] = str(task.job.experience_level)
    salary = task.get_estimated_monthly_salary()
    if salary is not None:
        contract_data['monthly_salary'] = salary
    if task.weekly_hours is not None:
        contract_data['weekly_hours'] = task.weekly_hours
    return contract_data


def finalize_recruitment_task(request, employee):
    task = get_recruitment_task(request)
    if not task or not can_create_employee_from_recruitment(request.user, task):
        return
    task.created_employee = employee
    task.status = 'recruitment_completed'
    task.save(update_fields=['created_employee', 'status'])
    uploader = getattr(request.user, 'employee', None)
    copy_recruitment_documents_to_employee(task, employee, uploaded_by=uploader)


def current_payscales_json():
    """Return current payscale map for template json_script (Python dict)."""
    from apps.finances.models import PayScale

    current = PayScale.get_current()
    payscale_data = {}
    for ps in current:
        group = ps.pay_scale_group
        if group not in payscale_data:
            payscale_data[group] = []
        payscale_data[group].append({
            'experience_level': ps.experience_level,
            'monthly_salary': str(ps.monthly_salary),
        })
    return payscale_data
