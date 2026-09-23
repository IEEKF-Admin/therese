"""Bug reports and feature suggestions from employees."""

from django.core.validators import FileExtensionValidator
from django.db import models

from apps.core.models import BaseModel

SCREENSHOT_EXTENSIONS = ['jpg', 'jpeg', 'png', 'gif', 'webp']


class FeedbackItem(BaseModel):
    class Kind(models.TextChoices):
        BUG = 'bug', 'Bug'
        FEATURE = 'feature', 'Feature'

    class Status(models.TextChoices):
        OPEN = 'open', 'Open'
        PLANNED = 'planned', 'Will be done'
        DONE = 'done', 'Done'

    kind = models.CharField(
        max_length=16,
        choices=Kind.choices,
        verbose_name='Type',
    )
    title = models.CharField(max_length=200, verbose_name='Title')
    description = models.TextField(verbose_name='Description')
    page_url = models.CharField(
        max_length=500,
        blank=True,
        verbose_name='Page URL',
        help_text='URL or path of the page the report refers to.',
    )
    screenshot = models.FileField(
        upload_to='feedback/screenshots/%Y/%m/',
        blank=True,
        null=True,
        max_length=255,
        verbose_name='Screenshot',
        validators=[FileExtensionValidator(allowed_extensions=SCREENSHOT_EXTENSIONS)],
    )
    created_by = models.ForeignKey(
        'hr.Employee',
        on_delete=models.PROTECT,
        related_name='feedback_items',
        verbose_name='Reported by',
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.OPEN,
        db_index=True,
        verbose_name='Status',
    )
    target_date = models.DateField(
        null=True,
        blank=True,
        verbose_name='Target date',
    )
    merged_into = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='merged_sources',
        verbose_name='Merged into',
    )

    class Meta:
        verbose_name = 'Bug or feature'
        verbose_name_plural = 'Bugs & Features'
        ordering = ['-created_at', '-pk']
        permissions = [
            ('manage_feedback', 'Can manage bugs and features'),
        ]

    def __str__(self):
        return f'#{self.pk} {self.title}'

    @property
    def is_merged(self):
        return self.merged_into_id is not None


class FeedbackVote(BaseModel):
    item = models.ForeignKey(
        FeedbackItem,
        on_delete=models.CASCADE,
        related_name='votes',
        verbose_name='Report',
    )
    employee = models.ForeignKey(
        'hr.Employee',
        on_delete=models.CASCADE,
        related_name='feedback_votes',
        verbose_name='Employee',
    )

    class Meta:
        verbose_name = 'Feedback vote'
        verbose_name_plural = 'Feedback votes'
        constraints = [
            models.UniqueConstraint(
                fields=['item', 'employee'],
                name='feedback_vote_item_employee_uniq',
            ),
        ]

    def __str__(self):
        return f'{self.employee_id} → {self.item_id}'


class FeedbackComment(BaseModel):
    item = models.ForeignKey(
        FeedbackItem,
        on_delete=models.CASCADE,
        related_name='comments',
        verbose_name='Report',
    )
    author = models.ForeignKey(
        'hr.Employee',
        on_delete=models.PROTECT,
        related_name='feedback_comments',
        verbose_name='Author',
    )
    body = models.TextField(verbose_name='Comment')

    class Meta:
        verbose_name = 'Feedback comment'
        verbose_name_plural = 'Feedback comments'
        ordering = ['created_at', 'pk']

    def __str__(self):
        return f'Comment on #{self.item_id}'
