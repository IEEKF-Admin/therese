"""Audience matching for documents (same rules as Login Popup Settings)."""


def document_has_audience_restrictions(document):
    if not document.pk:
        return False
    return (
        document.target_users.exists()
        or document.target_workgroups.exists()
        or document.target_groups.exists()
    )


def user_matches_document_audience(user, document):
    if not document_has_audience_restrictions(document):
        return True

    checks = []
    if document.target_users.exists():
        checks.append(document.target_users.filter(pk=user.pk).exists())
    if document.target_workgroups.exists():
        employee = getattr(user, 'employee', None)
        checks.append(
            employee is not None
            and document.target_workgroups.filter(members=employee).exists()
        )
    if document.target_groups.exists():
        user_group_ids = set(user.groups.values_list('pk', flat=True))
        target_group_ids = set(document.target_groups.values_list('pk', flat=True))
        checks.append(bool(user_group_ids & target_group_ids))

    if not checks:
        return user.has_perm('documents.view_document')

    if document.audience_match_mode == 'and':
        return all(checks)
    return any(checks)