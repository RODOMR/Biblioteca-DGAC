from functools import wraps
from django.contrib import messages
from django.shortcuts import redirect

def admin_required(view_func):
    @wraps(view_func)
    def wrapper_func(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, "Debes iniciar sesión para ver esta página.")
            return redirect('login')

        if request.user.is_superuser or request.user.groups.filter(name='Administrador').exists():
            return view_func(request, *args, **kwargs)
        else:
            messages.error(request, "No tienes permisos de Administrador para ver esta página.")
            return redirect('home')
    
    return wrapper_func

def cargador_required(view_func):
    @wraps(view_func)
    def wrapper_func(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, "Debes iniciar sesión para ver esta página.")
            return redirect('login')

        if request.user.is_superuser or request.user.groups.filter(name__in=['Administrador', 'Cargador']).exists():
            return view_func(request, *args, **kwargs)
        else:
            messages.error(request, "No tienes permisos de Cargador o Administrador para ver esta página.")
            return redirect('home')
    
    return wrapper_func