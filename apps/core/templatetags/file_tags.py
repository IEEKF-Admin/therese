from django import template

from apps.core.file_service import ThereseFileService

register = template.Library()


@register.filter
def file_display_name(file_field):
    """
    Return the original upload filename for a FileField/FieldFile, falling back
    to the storage basename. Storage paths may be UUID-renamed when too long.
    """
    if not file_field:
        return ''
    name = getattr(file_field, 'name', None) or str(file_field)
    return ThereseFileService.display_name(name)
