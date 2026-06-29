# apps/accounts/signals.py
"""
Signals for accounts app.
Do not remove any existing requirements.
"""

from django.dispatch import receiver
# from django.contrib.auth.signals import user_logged_in   # ← auskommentiert / entfernt


# === WICHTIG: Dieses Signal wurde entfernt, weil es das Flag zu früh gesetzt hat ===
# Wir setzen password_changed jetzt NUR in der ForcePasswordChangeView (nach erfolgreichem Ändern)