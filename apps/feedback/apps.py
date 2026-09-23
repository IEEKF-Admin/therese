from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _assign_feedback_permissions(sender, **kwargs):
    try:
        from apps.accounts.permissions import assign_permissions_to_groups
        assign_permissions_to_groups()
    except Exception:
        pass


class FeedbackConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.feedback'
    label = 'feedback'
    verbose_name = 'Bugs & Features'

    def ready(self):
        post_migrate.connect(_assign_feedback_permissions, sender=self)
