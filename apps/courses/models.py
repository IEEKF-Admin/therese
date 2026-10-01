from django.conf import settings
from django.db import models

from apps.core.models import BaseModel
from apps.hr.models import Employee, Workgroup


class Course(BaseModel):
    class Evidence(models.TextChoices):
        CERTIFICATE = 'certificate', 'Certificate (PDF)'
        CHECKBOX = 'checkbox', 'Checkbox'

    name = models.CharField(max_length=200, verbose_name='Name')
    description = models.TextField(blank=True, verbose_name='Description')
    interval_months = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Repeat every (months)',
        help_text='Empty = one-time course.',
    )
    evidence_type = models.CharField(
        max_length=20,
        choices=Evidence.choices,
        default=Evidence.CERTIFICATE,
        verbose_name='Evidence',
    )
    warn_weeks = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Warn weeks before due',
        help_text='Empty = no warning window.',
    )
    is_active = models.BooleanField(default=True, verbose_name='Active')
    all_institute = models.BooleanField(
        default=False,
        verbose_name='All institute',
        help_text='Required for non-external employees with a current contract.',
    )
    workgroups = models.ManyToManyField(
        Workgroup,
        blank=True,
        related_name='courses',
        verbose_name='Workgroups',
    )
    extra_employees = models.ManyToManyField(
        Employee,
        blank=True,
        related_name='extra_courses',
        verbose_name='Extra employees',
    )
    managers = models.ManyToManyField(
        Employee,
        through='CourseManager',
        related_name='managed_courses',
        blank=True,
        verbose_name='Managers',
    )

    class Meta:
        verbose_name = 'Course'
        verbose_name_plural = 'Courses'
        ordering = ['name']
        default_permissions = ()
        permissions = [
            (
                'view_institute_course_lists',
                'Can view course lists for all employees',
            ),
            (
                'view_workgroup_course_lists',
                'Can view course lists for own workgroups',
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def is_recurring(self):
        return bool(self.interval_months)


class CourseManager(BaseModel):
    class Scope(models.TextChoices):
        INSTITUTE = 'institute', 'Institute'
        WORKGROUP = 'workgroup', 'Own workgroups'

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='manager_links',
        verbose_name='Course',
    )
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='course_manager_links',
        verbose_name='Employee',
    )
    scope = models.CharField(
        max_length=20,
        choices=Scope.choices,
        default=Scope.WORKGROUP,
        verbose_name='Scope',
    )

    class Meta:
        verbose_name = 'Course manager'
        verbose_name_plural = 'Course managers'
        constraints = [
            models.UniqueConstraint(
                fields=['course', 'employee'],
                name='course_manager_course_employee_uniq',
            ),
        ]

    def __str__(self):
        return f'{self.employee} · {self.course} ({self.scope})'


def course_certificate_upload_to(instance, filename):
    return f'course_certificates/{instance.course_id}/{filename}'


class CourseCompletion(BaseModel):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='completions',
        verbose_name='Course',
    )
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='course_completions',
        verbose_name='Employee',
    )
    completed_on = models.DateField(verbose_name='Completed on')
    checked = models.BooleanField(default=False, verbose_name='Checked')
    certificate = models.FileField(
        upload_to=course_certificate_upload_to,
        blank=True,
        verbose_name='Certificate',
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recorded_course_completions',
        verbose_name='Recorded by',
    )

    class Meta:
        verbose_name = 'Course completion'
        verbose_name_plural = 'Course completions'
        ordering = ['-completed_on', '-pk']
        indexes = [
            models.Index(fields=['course', 'employee', '-completed_on']),
        ]

    def __str__(self):
        return f'{self.employee} · {self.course} · {self.completed_on}'
