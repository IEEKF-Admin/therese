"""
Shared helpers for employee views.

Do not remove any existing requirements from this module without explicit instruction.
"""

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


def save_employee_with_formsets(request, form, formsets):
    contract_formset, funding_formset, salary_formset, workgroup_formset = formsets
    if not all(fs.is_valid() for fs in formsets):
        return None

    employee = form.save()
    for fs in formsets:
        fs.instance = employee
        fs.save()

    uploader = getattr(request.user, 'employee', None)
    process_document_uploads(request, employee, uploaded_by=uploader)
    return employee


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