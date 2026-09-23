from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.feedback.access import (
    user_can_edit_item,
    user_can_manage_feedback,
    user_can_use_feedback,
    user_employee,
)
from apps.feedback.forms import (
    FeedbackAdminForm,
    FeedbackCommentForm,
    FeedbackItemForm,
    FeedbackMergeForm,
)
from apps.feedback.models import FeedbackItem, FeedbackVote
from apps.feedback.services import add_comment, merge_items, toggle_vote


def _deny(request, message='This page is only available for users linked to an employee profile.'):
    messages.error(request, message)
    return redirect('tasks:my_tasks')


def _visible_items():
    return FeedbackItem.objects.filter(merged_into__isnull=True).select_related(
        'created_by',
    )


@login_required
def item_list(request):
    if not user_can_use_feedback(request.user):
        return _deny(request)

    qs = _visible_items().annotate(
        vote_count=Count('votes', distinct=True),
        comment_count=Count('comments', distinct=True),
    )

    kind = (request.GET.get('kind') or '').strip()
    if kind in dict(FeedbackItem.Kind.choices):
        qs = qs.filter(kind=kind)

    status = (request.GET.get('status') or '').strip()
    if status in dict(FeedbackItem.Status.choices):
        qs = qs.filter(status=status)
    elif status != 'all':
        qs = qs.exclude(status=FeedbackItem.Status.DONE)

    q = (request.GET.get('q') or '').strip()
    if q:
        qs = qs.filter(
            Q(title__icontains=q)
            | Q(description__icontains=q)
            | Q(page_url__icontains=q)
        )

    employee = user_employee(request.user)
    voted_ids = set()
    if employee is not None:
        voted_ids = set(
            FeedbackVote.objects.filter(
                employee=employee,
                item_id__in=qs.values_list('pk', flat=True),
            ).values_list('item_id', flat=True)
        )

    return render(request, 'feedback/item_list.html', {
        'items': qs,
        'kind_filter': kind,
        'status_filter': status or 'openish',
        'search_query': q,
        'voted_ids': voted_ids,
        'can_manage': user_can_manage_feedback(request.user),
        'can_create': employee is not None,
        'kind_choices': FeedbackItem.Kind.choices,
        'status_choices': FeedbackItem.Status.choices,
    })


@login_required
def item_create(request):
    employee = user_employee(request.user)
    if employee is None:
        return _deny(request, 'You need an employee profile to submit a report.')

    if request.method == 'POST':
        form = FeedbackItemForm(request.POST, request.FILES)
        if form.is_valid():
            item = form.save(commit=False)
            item.created_by = employee
            item.save()
            messages.success(request, 'Report submitted. Thank you.')
            return redirect('feedback:item_detail', pk=item.pk)
    else:
        form = FeedbackItemForm()

    return render(request, 'feedback/item_form.html', {
        'form': form,
        'title': 'New report',
        'is_create': True,
    })


def _get_item_or_canonical(pk):
    item = get_object_or_404(
        FeedbackItem.objects.select_related('created_by', 'merged_into'),
        pk=pk,
    )
    return item


@login_required
def item_detail(request, pk):
    if not user_can_use_feedback(request.user):
        return _deny(request)

    item = _get_item_or_canonical(pk)
    if item.merged_into_id:
        messages.info(
            request,
            f'This report was merged into #{item.merged_into_id}.',
        )
        return redirect('feedback:item_detail', pk=item.merged_into_id)

    employee = user_employee(request.user)
    can_manage = user_can_manage_feedback(request.user)
    can_edit = user_can_edit_item(request.user, item)
    has_voted = False
    if employee is not None:
        has_voted = FeedbackVote.objects.filter(item=item, employee=employee).exists()

    comments = item.comments.select_related('author').all()
    vote_count = item.votes.count()

    context = {
        'item': item,
        'comments': comments,
        'comment_form': FeedbackCommentForm(),
        'vote_count': vote_count,
        'has_voted': has_voted,
        'can_comment': employee is not None,
        'can_vote': employee is not None,
        'can_edit': can_edit,
        'can_manage': can_manage,
    }
    if can_manage:
        context['admin_form'] = FeedbackAdminForm(initial={
            'status': item.status,
            'target_date': item.target_date,
        })
        context['merge_form'] = FeedbackMergeForm(item=item)
    return render(request, 'feedback/item_detail.html', context)


@login_required
def item_edit(request, pk):
    item = _get_item_or_canonical(pk)
    if item.merged_into_id:
        return redirect('feedback:item_detail', pk=item.merged_into_id)
    if not user_can_edit_item(request.user, item):
        return _deny(request, "You don't have permission to edit this report.")

    if request.method == 'POST':
        form = FeedbackItemForm(request.POST, request.FILES, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, 'Report updated.')
            return redirect('feedback:item_detail', pk=item.pk)
    else:
        form = FeedbackItemForm(instance=item)

    return render(request, 'feedback/item_form.html', {
        'form': form,
        'item': item,
        'title': f'Edit #{item.pk}',
        'is_create': False,
    })


@login_required
@require_POST
def item_vote(request, pk):
    employee = user_employee(request.user)
    if employee is None:
        return _deny(request, 'You need an employee profile to vote.')
    item = _get_item_or_canonical(pk)
    if item.merged_into_id:
        item = item.merged_into
    added = toggle_vote(item, employee)
    if added:
        messages.success(request, 'Added your +1.')
    else:
        messages.success(request, 'Removed your +1.')
    return redirect('feedback:item_detail', pk=item.pk)


@login_required
@require_POST
def item_comment(request, pk):
    employee = user_employee(request.user)
    if employee is None:
        return _deny(request, 'You need an employee profile to comment.')
    item = _get_item_or_canonical(pk)
    if item.merged_into_id:
        item = item.merged_into
    form = FeedbackCommentForm(request.POST)
    if form.is_valid():
        add_comment(item, employee, form.cleaned_data['body'])
        messages.success(request, 'Comment added.')
    else:
        messages.error(request, 'Please enter a comment.')
    return redirect('feedback:item_detail', pk=item.pk)


@login_required
@require_POST
def item_admin(request, pk):
    if not user_can_manage_feedback(request.user):
        return _deny(request, "You don't have permission to manage this report.")
    item = _get_item_or_canonical(pk)
    if item.merged_into_id:
        return redirect('feedback:item_detail', pk=item.merged_into_id)
    form = FeedbackAdminForm(request.POST)
    if form.is_valid():
        item.status = form.cleaned_data['status']
        item.target_date = form.cleaned_data.get('target_date')
        item.save(update_fields=['status', 'target_date', 'updated_at'])
        messages.success(request, 'Status saved.')
    else:
        messages.error(request, 'Please correct the status or target date.')
    return redirect('feedback:item_detail', pk=item.pk)


@login_required
@require_POST
def item_delete(request, pk):
    if not user_can_manage_feedback(request.user):
        return _deny(request, "You don't have permission to delete this report.")
    item = _get_item_or_canonical(pk)
    if item.merged_into_id:
        return redirect('feedback:item_detail', pk=item.merged_into_id)
    title = item.title
    item.merged_sources.all().delete()
    item.delete()
    messages.success(request, f'Deleted “{title}”.')
    return redirect('feedback:item_list')


@login_required
@require_POST
def item_merge(request, pk):
    if not user_can_manage_feedback(request.user):
        return _deny(request, "You don't have permission to merge reports.")
    item = _get_item_or_canonical(pk)
    if item.merged_into_id:
        return redirect('feedback:item_detail', pk=item.merged_into_id)
    form = FeedbackMergeForm(request.POST, item=item)
    if not form.is_valid():
        messages.error(request, 'Please select a report to merge into.')
        return redirect('feedback:item_detail', pk=item.pk)
    target = form.cleaned_data['target']
    try:
        merge_items(item, target, actor=user_employee(request.user))
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('feedback:item_detail', pk=item.pk)
    messages.success(request, f'Merged #{item.pk} into #{target.pk}.')
    return redirect('feedback:item_detail', pk=target.pk)
