from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User, Group
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Count
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

# --- IMPORTACIONES PARA LA INTELIGENCIA ---
from collections import Counter 
from .models import Libro, Material, Prestamo

def ensure_roles():
    for name in ["Administrador", "Cargador", "Lector"]:
        Group.objects.get_or_create(name=name)

# ==============================================================================
# MOTOR DE INTELIGENCIA (Algoritmo de Recomendación)
# ==============================================================================
def obtener_recomendaciones_inteligentes(user):
    """
    Analiza el historial del usuario para sugerir libros basado en su categoría favorita.
    """
    # 1. Si no está logueado, no hay historial que analizar
    if not user.is_authenticated:
        return []

    # 2. Obtener qué ha leído el usuario (Historial de Préstamos)
    prestamos_historial = Prestamo.objects.filter(usuario=user, libro__isnull=False)
    
    # Si es usuario nuevo (sin historial), retornamos lista vacía (se mostrará solo el ranking global)
    if not prestamos_historial.exists():
        return []

    # 3. Detectar Categoría Favorita (La Moda Estadística)
    # Extraemos los IDs de las categorías de los libros que leyó
    ids_categorias = [p.libro.categoria.id for p in prestamos_historial if p.libro.categoria]
    
    if not ids_categorias:
        return []
    
    # Counter nos dice cuál es el elemento más repetido [(id_categoria, cantidad_veces)]
    categoria_top_id = Counter(ids_categorias).most_common(1)[0][0]
    
    # 4. Obtener IDs de libros que YA leyó para no recomendarlos de nuevo
    libros_leidos_ids = prestamos_historial.values_list('libro_id', flat=True)

    # 5. Consulta Inteligente:
    # "Dame libros de su categoría favorita, que NO haya leído, ordenados por popularidad"
    recomendaciones = Libro.objects.filter(
        categoria_id=categoria_top_id,
        activo=True
    ).exclude(
        id__in=libros_leidos_ids
    ).annotate(
        popularidad=Count('prestamo')
    ).order_by('-popularidad')[:3] # Solo los Top 3

    return recomendaciones

def obtener_recomendaciones_inteligentes(user):
    """
    Analiza el historial del usuario para sugerir libros basado en su categoría favorita.
    """
    # 1. Si no está logueado, no hay historial que analizar
    if not user.is_authenticated:
        return []

    # 2. Obtener qué ha leído el usuario (Historial de Préstamos)
    prestamos_historial = Prestamo.objects.filter(usuario=user, libro__isnull=False)
    
    # Si es usuario nuevo (sin historial), retornamos lista vacía
    if not prestamos_historial.exists():
        return []

    # 3. Detectar Categoría Favorita (La Moda Estadística)
    ids_categorias = [p.libro.categoria.id for p in prestamos_historial if p.libro.categoria]
    
    if not ids_categorias:
        return []
    
    # Counter nos dice cuál es el elemento más repetido
    categoria_top_id = Counter(ids_categorias).most_common(1)[0][0]
    
    # 4. Obtener IDs de libros que YA leyó para no recomendarlos de nuevo
    libros_leidos_ids = prestamos_historial.values_list('libro_id', flat=True)

    # 5. Consulta Inteligente:
    recomendaciones = Libro.objects.filter(
        categoria_id=categoria_top_id,
        activo=True
    ).exclude(
        id__in=libros_leidos_ids
    ).annotate(
        popularidad=Count('prestamo')
    ).order_by('-popularidad')[:3] # Solo los Top 3

    return recomendaciones
# ==============================================================================
# VISTAS
# ==============================================================================

def home_view(request):
    """
    Vista de inicio: Muestra Ranking Global + Recomendaciones Personalizadas (IA).
    """
    # --- LÓGICA 1: RANKING GLOBAL (Lo que ya tenías) ---
    top_libros = Prestamo.objects.filter(libro__isnull=False).values('libro') \
        .annotate(total=Count('id')).order_by('-total')[:3]
    
    top_materiales = Prestamo.objects.filter(material__isnull=False).values('material') \
        .annotate(total=Count('id')).order_by('-total')[:3]

    ranking_global = []
    
    for item in top_libros:
        try:
            libro = Libro.objects.get(pk=item['libro'])
            ranking_global.append({'obj': libro, 'tipo': 'Libro', 'total': item['total'], 'es_libro': True})
        except Libro.DoesNotExist: 
            pass
        
    for item in top_materiales:
        try:
            material = Material.objects.get(pk=item['material'])
            ranking_global.append({'obj': material, 'tipo': 'Material', 'total': item['total'], 'es_libro': False})
        except Material.DoesNotExist: pass
    
    ranking_global.sort(key=lambda x: x['total'], reverse=True)
    destacados = ranking_global[:3]

    # --- LÓGICA 2: INTELIGENCIA ARTIFICIAL (NUEVO) ---
    # Llamamos a nuestra función predictiva
    mis_recomendados = obtener_recomendaciones_inteligentes(request.user)

    context = {
        'destacados': destacados,
        'recomendados': mis_recomendados  # <--- Enviamos esto al template
    }
    return render(request, "biblioteca/home.html", context)

def login_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form_username = request.POST.get("username", "").strip()
        form_password = request.POST.get("password", "")
        
        # Búsqueda insensible a mayúsculas/minúsculas
        user_obj = User.objects.filter(username__iexact=form_username).first()
        
        if user_obj:
            user = authenticate(request, username=user_obj.username, password=form_password)
            if user:
                login(request, user)
                nombre = user.first_name or user.username
                messages.success(request, f"Bienvenido {nombre}")
                return redirect("home")
        
        messages.error(request, "Usuario o contraseña incorrectos.")
    
    return render(request, "biblioteca/login.html")

def logout_view(request):
    logout(request)
    messages.success(request, "Sesión cerrada.")
    return redirect("login")

def register_view(request):
    ensure_roles()
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        f = request.POST.get("first_name", "").strip()
        l = request.POST.get("last_name", "").strip()
        e = request.POST.get("email", "").strip()
        p1 = request.POST.get("password", "")
        p2 = request.POST.get("password2", "")

        # 1. Validaciones básicas
        if not (f and l and e and p1):
            messages.error(request, "Por favor completa todos los datos.")
            return redirect("register")

        # 2. Validación de formato EMAIL
        try:
            validate_email(e)
        except ValidationError:
            messages.error(request, "El formato del correo electrónico no es válido.")
            return redirect("register")

        # 3. Validación de Duplicados
        if User.objects.filter(username=e).exists():
            messages.error(request, "Este correo electrónico ya está registrado.")
            return redirect("register")

        # 4. Coincidencia de contraseñas
        if p1 != p2:
            messages.error(request, "Las contraseñas no coinciden.")
            return redirect("register")

        # 5. Fortaleza de contraseña
        try:
            validate_password(p1)
        except ValidationError as err:
            messages.error(request, err.messages[0])
            return redirect("register")

        # 6. Crear Usuario
        try:
            user = User.objects.create_user(username=e, email=e, password=p1, first_name=f, last_name=l)
            # Asignar rol por defecto
            grupo_lector = Group.objects.get(name="Lector")
            user.groups.add(grupo_lector)
            
            messages.success(request, "Cuenta creada exitosamente. ¡Bienvenido!")
            return redirect("login")
        except Exception as ex:
            messages.error(request, f"Error interno al crear usuario: {ex}")
            return redirect("register")

    return render(request, "biblioteca/register.html")

def health_view(request):
    return JsonResponse({'status': 'ok'})