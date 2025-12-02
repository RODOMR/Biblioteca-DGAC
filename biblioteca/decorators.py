#
# Archivo: biblioteca/decorators.py
#
from django.contrib import messages
from django.shortcuts import redirect

def admin_required(view_func):
    """
    Comprueba si el usuario es 'Administrador' O un 'Superusuario'.
    """
    def wrapper_func(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, "Debes iniciar sesión para ver esta página.")
            return redirect('login')

        # Un superusuario siempre es un admin.
        if request.user.is_superuser or request.user.groups.filter(name='Administrador').exists():
            return view_func(request, *args, **kwargs)
        else:
            messages.error(request, "No tienes permisos de Administrador para ver esta página.")
            return redirect('home')
    
    return wrapper_func

def cargador_required(view_func):
    """
    Comprueba si el usuario es 'Cargador', 'Administrador' O 'Superusuario'.
    """
    def wrapper_func(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, "Debes iniciar sesión para ver esta página.")
            return redirect('login')

        # Un superusuario o admin también es un cargador.
        if request.user.is_superuser or \
           request.user.groups.filter(name='Administrador').exists() or \
           request.user.groups.filter(name='Cargador').exists():
            return view_func(request, *args, **kwargs)
        else:
            messages.error(request, "No tienes permisos de Cargador o Administrador para ver esta página.")
            return redirect('home')
    
    return wrapper_func