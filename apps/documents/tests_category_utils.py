from django.test import TestCase

from apps.documents.category_utils import (
    build_category_tree_rows,
    build_document_list_sections,
    category_breadcrumb,
    document_sort_key,
)
from apps.documents.models import Document, DocumentCategory, DocumentVersion


class DocumentCategoryHierarchyTests(TestCase):
    def setUp(self):
        self.root_a = DocumentCategory.objects.create(name='SOPs')
        self.child_a1 = DocumentCategory.objects.create(name='Labor', parent=self.root_a)
        self.root_b = DocumentCategory.objects.create(name='Policies')

        self.doc_labor = Document.objects.create(title='Safety glasses', category=self.child_a1)
        self.doc_policy = Document.objects.create(title='Leave policy', category=self.root_b)
        version = DocumentVersion.objects.create(
            document=self.doc_labor,
            version_number=1,
            status=DocumentVersion.Status.PUBLISHED,
            content_html='<p>Lab</p>',
        )
        self.doc_labor.current_published_version = version
        self.doc_labor.save()
        policy_version = DocumentVersion.objects.create(
            document=self.doc_policy,
            version_number=1,
            status=DocumentVersion.Status.PUBLISHED,
            content_html='<p>Policy</p>',
        )
        self.doc_policy.current_published_version = policy_version
        self.doc_policy.save()

    def test_breadcrumb_shows_full_path(self):
        self.assertEqual(category_breadcrumb(self.child_a1), 'SOPs › Labor')

    def test_tree_rows_keep_parent_child_order(self):
        rows = build_category_tree_rows(
            DocumentCategory.objects.select_related('parent').all()
        )
        names = [row['category'].name for row in rows]
        self.assertEqual(names, ['Policies', 'SOPs', 'Labor'])

    def test_document_sections_emit_nested_headings(self):
        sections = build_document_list_sections([self.doc_labor, self.doc_policy])
        headings = [section['title'] for section in sections if section['type'] == 'heading']
        self.assertEqual(headings, ['Policies', 'SOPs', 'Labor'])

    def test_document_sort_key_orders_by_hierarchy(self):
        self.assertLess(
            document_sort_key(self.doc_policy),
            document_sort_key(self.doc_labor),
        )