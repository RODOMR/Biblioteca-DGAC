from django import template
from django.contrib.auth.models import Group

register = template.Library()

@register.filter(name='tiene_grupo')
def tiene_grupo(user, group_name):
    """
    Uso en template: {% if request.user|tiene_grupo:"Administrador" %}
    Devuelve True si el usuario pertenece al grupo indicado.
    """
    if user.is_superuser:
        return True
    try:
        group = Group.objects.get(name=group_name)
        return group in user.groups.all()
    except Group.DoesNotExist:
        return False