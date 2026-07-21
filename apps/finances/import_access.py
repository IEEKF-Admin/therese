"""Access helpers for finance data imports and their upload history."""

from __future__ import annotations

from apps.core.models import DataImportLog


def user_can_import_third_party_funding(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.has_perm('finances.import_third_party_funding_report')


def user_can_import_pay_scale(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.has_perm('finances.import_pay_scale')


def user_can_run_any_tracked_import(user) -> bool:
    """True if the user may run any import that writes to DataImportLog."""
    return user_can_import_third_party_funding(user) or user_can_import_pay_scale(user)


def user_can_view_import_history(user) -> bool:
    """
    Anyone who may perform a tracked import may also view import history
    (filtered to the kinds they are allowed to run).
    """
    return user_can_run_any_tracked_import(user)


def import_history_kinds_for_user(user) -> list[str]:
    """DataImportLog.kind values the user may see in history."""
    if not user or not user.is_authenticated:
        return []
    if user.is_superuser:
        return [
            DataImportLog.Kind.THIRD_PARTY_FUNDING_REPORT,
            DataImportLog.Kind.PAY_SCALE,
        ]
    kinds = []
    if user.has_perm('finances.import_third_party_funding_report'):
        kinds.append(DataImportLog.Kind.THIRD_PARTY_FUNDING_REPORT)
    if user.has_perm('finances.import_pay_scale'):
        kinds.append(DataImportLog.Kind.PAY_SCALE)
    return kinds
