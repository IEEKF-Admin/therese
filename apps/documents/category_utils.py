"""Helpers for hierarchical document categories."""

from .models import DocumentCategory


def load_categories_by_id():
    return {
        category.pk: category
        for category in DocumentCategory.objects.select_related(
            'parent__parent__parent__parent'
        )
    }


def category_path(category, categories_by_id=None):
    parts = []
    current = category
    seen = set()
    while current is not None and current.pk not in seen:
        seen.add(current.pk)
        parts.append(current)
        if categories_by_id is not None:
            current = categories_by_id.get(current.parent_id)
        else:
            current = current.parent
    return list(reversed(parts))


def category_sort_key(category, categories_by_id=None):
    return tuple(
        part.name.lower()
        for part in category_path(category, categories_by_id=categories_by_id)
    )


def document_sort_key(document, categories_by_id=None):
    return category_sort_key(
        document.category,
        categories_by_id=categories_by_id,
    ) + (document.title.lower(),)


def category_breadcrumb(category, separator=' › '):
    return separator.join(part.name for part in category_path(category))


def get_descendant_ids(category):
    ids = set()
    stack = list(category.children.all())
    while stack:
        child = stack.pop()
        ids.add(child.pk)
        stack.extend(child.children.all())
    return ids


def build_category_tree_rows(categories):
    by_parent = {}
    for category in categories:
        by_parent.setdefault(category.parent_id, []).append(category)

    for children in by_parent.values():
        children.sort(key=lambda item: item.name.lower())

    def walk(parent_id=None, depth=0):
        rows = []
        for category in by_parent.get(parent_id, []):
            rows.append({'category': category, 'depth': depth})
            rows.extend(walk(category.pk, depth + 1))
        return rows

    return walk(None)


def build_document_list_sections(documents, categories_by_id=None):
    if categories_by_id is None:
        categories_by_id = load_categories_by_id()

    sections = []
    last_path_ids = None
    current_docs_section = None

    for document in sorted(
        documents,
        key=lambda doc: document_sort_key(doc, categories_by_id=categories_by_id),
    ):
        path = category_path(document.category, categories_by_id=categories_by_id)
        path_ids = tuple(part.pk for part in path)
        if path_ids != last_path_ids:
            for index, category in enumerate(path):
                sections.append({
                    'type': 'heading',
                    'level': index + 2,
                    'title': category.name,
                })
            current_docs_section = {'type': 'docs', 'documents': [document]}
            sections.append(current_docs_section)
            last_path_ids = path_ids
        else:
            current_docs_section['documents'].append(document)

    return sections