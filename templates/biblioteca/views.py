from django.shortcuts import render

# Create your views here.
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User, Group
from django.shortcuts import ren
def, redirect

def ensure_roles():
    """Crea los grupos base si no existen."""
    for name in ["Administrador", "Cargador", "Lector"]:
        Group.objects.get_or_create(name=name)

def home_view(request):
    """Home simple para /"""
    return render(request, "biblioteca/home.html")

def login_view(request):
    """Login por email (usa username=email)."""
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            messages.success(request, f"Bienvenido {user.first_name or user.username}")
            return redirect("home")
        messages.error(request, "Usuario o contraseña incorrectos.")
    return render(request, "biblioteca/login.html")

def logout_view(request):
    """Cierra sesión y vuelve al login."""
    logout(request)
    messages.success(request, "Sesión cerrada.")
    return redirect("login")

def register_view(request):
    """
    Registro: nombre, apellido, email, contraseña.
    Crea el usuario con username=email y lo asigna al grupo 'Lector'.
    """
    ensure_roles()
    if request.method == "POST":
        first = request.POST.get("first_name", "").strip()
        last = request.POST.get("last_name", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        password2 = request.POST.get("password2", "")

        if not (first and last and email and password and password2):
            messages.error(request, "Todos los campos son obligatorios.")
            return redirect("register")
        if password != password2:
            messages.error(request, "Las contraseñas no coinciden.")
            return redirect("register")
        if User.objects.filter(username=email).exists():
            messages.error(request, "Ya existe una cuenta con ese email.")
            return redirect("register")

        user = User.objects.create_user(
            username=email, email=email, password=password,
            first_name=first, last_name=last
        )
        lector, _ = Group.objects.get_or_create(name="Lector")
        user.groups.add(lector)

        messages.success(request, "Cuenta creada. Ya puedes iniciar sesión.")
        return redirect("login")

    return render(request, "biblioteca/register.html")
