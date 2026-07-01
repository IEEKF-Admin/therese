# apps/accounts/signals.py
"""
Signals for accounts app.
Do not remove any existing requirements.
"""

from django.dispatch import receiver


from django.db.models.signals import post_save


# from django.contrib.auth.signals import user_logged_in   # ← auskommentiert / entfernt


# === WICHTIG: Dieses Signal wurde entfernt, weil es das Flag zu frÃ¼h gesetzt hat ===

# Wir setzen password_changed jetzt NUR in der ForcePasswordChangeView (nach erfolgreichem Ã„ndern)

# Wir setzen password_changed jetzt NUR in der ForcePasswordChangeView (nach erfolgreichem Ã„ndern)


@receiver(post_save, sender="accounts.CustomUser")
def ensure_superuser_is_staff(sender, instance, created, **kwargs):
    """
    Make sure that any superuser (is_superuser=True) also has is_staff=True.
    This guarantees that users created with `createsuperuser` (or manually
    marked as superuser) can always access the Django admin, even on fresh
    installations where the staff flag might not have been explicitly set.
    """
    if instance.is_superuser and not instance.is_staff:
        instance.is_staff = True
        # Use update_fields to avoid infinite recursion / unnecessary full save
        instance.save(update_fields=["is_staff"])



