{% extends "admin/base_site.html" %}

{% block title %}Anmelden - THERESE{% endblock %}

{% block content %}
<div class="module">
    <h1>Anmelden</h1>

    <form method="post" action="{% url 'admin:login' %}">
        {% csrf_token %}
        {{ form.as_p }}
        
        <input type="hidden" name="next" value="{{ next|default:'/tasks/' }}">
        
        <button type="submit" class="button">Anmelden</button>
    </form>
</div>
{% endblock %}