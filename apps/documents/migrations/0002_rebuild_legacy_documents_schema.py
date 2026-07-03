"""Replace legacy documents tables with the Documents & SOPs schema.

Some databases still have tables from the old file-sharing documents app while
django_migrations marks 0001_initial as applied. This migration rebuilds the
schema only when the new tables are missing.
"""

from django.db import migrations


LEGACY_TABLES = (
    'documents_document_tags',
    'documents_documentshare',
    'documents_documenttag',
    'documents_userdocumentarchive',
    'documents_documentpublishpopupack',
    'documents_documentreadacknowledgement',
    'documents_documentactivitylog',
    'documents_documentattachment',
    'documents_document_target_groups',
    'documents_document_target_users',
    'documents_document_target_workgroups',
    'documents_document',
    'documents_documentversion',
    'documents_documentcategory',
)

MODELS_IN_ORDER = (
    'DocumentCategory',
    'Document',
    'DocumentVersion',
    'DocumentAttachment',
    'DocumentActivityLog',
    'DocumentReadAcknowledgement',
    'DocumentPublishPopupAck',
)


def _needs_rebuild(schema_editor):
    connection = schema_editor.connection
    tables = set(connection.introspection.table_names())
    return 'documents_documentpublishpopupack' not in tables


def rebuild_documents_schema(apps, schema_editor):
    if not _needs_rebuild(schema_editor):
        return

    connection = schema_editor.connection
    qn = connection.ops.quote_name

    if connection.vendor == 'sqlite':
        with connection.cursor() as cursor:
            cursor.execute('PRAGMA foreign_keys=OFF')

    existing = set(connection.introspection.table_names())
    for table in sorted(t for t in existing if t.startswith('documents_')):
        schema_editor.execute(f'DROP TABLE {qn(table)}')

    if connection.vendor == 'sqlite':
        with connection.cursor() as cursor:
            cursor.execute('PRAGMA foreign_keys=ON')

    document_model = apps.get_model('documents', 'Document')
    for model_name in MODELS_IN_ORDER:
        model = apps.get_model('documents', model_name)
        schema_editor.create_model(model)

    existing = set(connection.introspection.table_names())
    for field in document_model._meta.local_many_to_many:
        through = field.remote_field.through
        if through._meta.auto_created and through._meta.db_table not in existing:
            schema_editor.create_model(through)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(rebuild_documents_schema, noop_reverse),
    ]