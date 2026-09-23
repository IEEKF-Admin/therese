from django.db import transaction

from apps.feedback.models import FeedbackComment, FeedbackVote


@transaction.atomic
def merge_items(source, target, *, actor=None):
    """Absorb ``source`` into ``target``. Comments and +1s move to the target."""
    if source.pk == target.pk:
        raise ValueError('Cannot merge a report into itself.')
    if source.merged_into_id:
        raise ValueError('This report is already merged.')
    if target.merged_into_id:
        raise ValueError('The selected report is itself merged into another.')
    if source.kind != target.kind:
        raise ValueError('Reports must be the same type to merge.')

    existing_voters = set(
        FeedbackVote.objects.filter(item=target).values_list('employee_id', flat=True)
    )
    for vote in list(FeedbackVote.objects.filter(item=source)):
        if vote.employee_id in existing_voters:
            vote.delete()
        else:
            vote.item = target
            vote.save(update_fields=['item', 'updated_at'])
            existing_voters.add(vote.employee_id)

    FeedbackComment.objects.filter(item=source).update(item=target)

    if not target.screenshot and source.screenshot:
        target.screenshot = source.screenshot
        target.save(update_fields=['screenshot', 'updated_at'])

    note = f'Merged report #{source.pk}: {source.title}'
    if actor is not None:
        FeedbackComment.objects.create(item=target, author=actor, body=note)

    source.merged_into = target
    source.save(update_fields=['merged_into', 'updated_at'])
    return target


def toggle_vote(item, employee):
    vote, created = FeedbackVote.objects.get_or_create(item=item, employee=employee)
    if not created:
        vote.delete()
        return False
    return True


def add_comment(item, employee, body):
    return FeedbackComment.objects.create(
        item=item,
        author=employee,
        body=body,
    )
