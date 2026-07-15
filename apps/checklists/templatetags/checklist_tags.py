from django import template

register = template.Library()


def _resp(responses, node_pk):
    if not responses:
        return None
    return responses.get(node_pk)


@register.filter
def get_response_obj(responses, node_pk):
    return _resp(responses, node_pk)


@register.filter
def get_response_text(responses, node_pk):
    r = _resp(responses, node_pk)
    return r.value_text if r else ''


@register.filter
def get_response_bool(responses, node_pk):
    r = _resp(responses, node_pk)
    return bool(r and r.value_bool)


@register.filter
def get_response_choice(responses, node_pk):
    r = _resp(responses, node_pk)
    return r.value_choice if r else ''


@register.filter
def get_response_na(responses, node_pk):
    r = _resp(responses, node_pk)
    return bool(r and r.not_applicable)
