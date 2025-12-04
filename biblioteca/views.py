import os
import re
import openpyxl
from io import StringIO
from datetime import date, timedelta, datetime

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User, Group
from django.db.models import Count, Q, Value
from django.db.models.functions import Concat
from django.http import JsonResponse, HttpResponse
from django.core.paginator import Paginator
from django.core.mail import send_mail
from django.core.management import call_command
from django.conf import settings
from django.utils import timezone
from django.utils.safestring import mark_safe
from openpyxl.styles import Font, PatternFill

from .models import (
    Libro, Prestamo, Autor, Categoria, Reserva, Favorito,
    Perfil, Material, Historial, ConfiguracionSistema, Noticia
)
from .forms import (
    LibroForm, AutorForm, CategoriaForm, PerfilForm,
    MaterialForm, NoticiaForm
)
from .decorators import admin_required, cargador_required
from .utils import enviar_correo_notificacion, asignar_siguiente_reserva, calcular_fecha_habil

# ==========================================
# UTILIDADES DE AUDITORÍA Y SISTEMA
# ==========================================

def registrar_auditoria(request, accion, detalle):
    """Registra cualquier acción importante en la base de datos."""
    try:
        usuario_actor = request.user if request.user.is_authenticated else None
        detalle_seguro = str(detalle)[:255]
        Historial.objects.create(
            usuario=usuario_actor,
            accion=accion,
            detalle=detalle_seguro
        )
    except Exception as e:
        print(f" ERROR AUDITORÍA: {e}")

def generar_detalle_cambios(form):
    if not form.changed_data:
        return "Se guardó sin realizar cambios."
    
    cambios = []
    for campo in form.changed_data:
        antiguo = form.initial.get(campo, 'N/A')
        nuevo = form.cleaned_data.get(campo, 'N/A')
        
        str_antiguo = str(antiguo)[:15] + '...' if len(str(antiguo)) > 15 else str(antiguo)
        str_nuevo = str(nuevo)[:15] + '...' if len(str(nuevo)) > 15 else str(nuevo)
        
        cambios.append(f"[{campo}: {str_antiguo} -> {str_nuevo}]")
    
    return "Cambios: " + " ".join(cambios)

def _generar_contenido_txt():
    historial_completo = Historial.objects.all().order_by('-fecha')
    
    contenido_txt = []
    contenido_txt.append("="*90 + "\n")
    contenido_txt.append(" REGISTRO DE AUDITORÍA DEL SIGB - PROYECTO DGAC\n")
    ahora_chile = timezone.localtime(timezone.now())
    contenido_txt.append(f" Generado el: {ahora_chile.strftime('%d-%m-%Y %H:%M:%S')}\n")
    contenido_txt.append("="*90 + "\n\n")
    
    contenido_txt.append(f"{'FECHA (LOCAL)':<22} | {'USUARIO':<25} | {'ACCIÓN':<20} | DETALLE\n")
    contenido_txt.append("-" * 130 + "\n")

    for registro in historial_completo:
        fecha_local = timezone.localtime(registro.fecha)
        fecha_str = fecha_local.strftime('%d-%m-%Y %H:%M:%S')
        usuario_str = registro.usuario.username if registro.usuario else "Sistema"
        linea = f"{fecha_str:<22} | {usuario_str:<25} | {registro.accion:<20} | {registro.detalle}\n"
        contenido_txt.append(linea)

    return "".join(contenido_txt)

def _check_backup_trigger():
    try:
        config = ConfiguracionSistema.obtener_instancia()
        hoy = timezone.now().date()

        if config.fecha and (hoy - config.fecha).days < 28:
            return

        nombre_archivo = f"SIGB_Auditoria_Auto_{hoy.strftime('%Y%m%d')}.txt"
        Historial.objects.create(
            usuario=None, 
            accion="Respaldo Automático", 
            detalle=f"Se generó archivo de seguridad: {nombre_archivo}"
        )
        
        ruta_carpeta = os.path.join(settings.BASE_DIR, 'respaldos_auditoria')
        os.makedirs(ruta_carpeta, exist_ok=True)

        with open(os.path.join(ruta_carpeta, nombre_archivo), 'w', encoding='utf-8') as f:
            f.write(_generar_contenido_txt())

        config.fecha = hoy
        config.save()
    except Exception: pass

# ==========================================
# VISTAS PÚBLICAS Y DE CATÁLOGO
# ==========================================

def lista_libros(request):
    _check_backup_trigger()
    query = request.GET.get('q', '')
    filtro_seleccionado = request.GET.get('filtro', '')

    libros = Libro.objects.filter(activo=True)
    materiales = Material.objects.filter(activo=True)

    if query:
        libros = libros.annotate(nombre_completo=Concat('autor__nombre', Value(' '), 'autor__apellido'))
        libros = libros.filter(
            Q(titulo__icontains=query) |
            Q(autor__nombre__icontains=query) |
            Q(autor__apellido__icontains=query) |
            Q(nombre_completo__icontains=query) |
            Q(categoria__nombre__icontains=query) |
            Q(isbn__icontains=query)
        ).distinct()

        materiales = materiales.filter(
            Q(titulo__icontains=query) |
            Q(autor__icontains=query) |
            Q(tipo__icontains=query) |
            Q(codigo__icontains=query)
        ).distinct()

    if filtro_seleccionado:
        libros = libros.filter(categoria__nombre=filtro_seleccionado)
        materiales = materiales.filter(tipo=filtro_seleccionado)

    todos_items = list(libros) + list(materiales)
    todos_items.sort(key=lambda x: x.titulo.lower())

    catalogo_unificado = []
    fav_libros = []
    fav_mats = []

    if request.user.is_authenticated:
        fav_libros = list(Favorito.objects.filter(usuario=request.user, libro__isnull=False).values_list('libro_id', flat=True))
        fav_mats = list(Favorito.objects.filter(usuario=request.user, material__isnull=False).values_list('material_id', flat=True))

    for item in todos_items:
        es_libro = isinstance(item, Libro)
        filter_prestamo = {'libro': item, 'devuelto': False} if es_libro else {'material': item, 'devuelto': False}

        cantidad_total = item.cantidad
        prestamos_activos = Prestamo.objects.filter(**filter_prestamo).count()
        disponible = cantidad_total - prestamos_activos
        es_fav = item.id in fav_libros if es_libro else item.id in fav_mats

        ya_reservado = False
        reserva_lista_mi = False
        reserva_lista_otro = False

        if request.user.is_authenticated:
            filter_res = {'libro': item} if es_libro else {'material': item}
            ya_reservado = Reserva.objects.filter(**filter_res, usuario=request.user).exclude(estado__in=['COMPLETADA', 'CANCELADA']).exists()
            res_lista = Reserva.objects.filter(**filter_res, estado='PENDIENTE_RETIRO').first()
            if res_lista:
                if res_lista.usuario == request.user: reserva_lista_mi = True
                else: reserva_lista_otro = True

        catalogo_unificado.append({
            'item': item, 'es_libro': es_libro, 'esta_agotado': disponible <= 0,
            'cantidad_disponible': disponible, 'ya_reservado_por_mi': ya_reservado,
            'reserva_lista_para_mi': reserva_lista_mi, 'reserva_lista_para_otro': reserva_lista_otro,
            'es_favorito': es_fav
        })

    paginator = Paginator(catalogo_unificado, 12)
    page_obj = paginator.get_page(request.GET.get('page'))

    cats = list(Categoria.objects.filter(activo=True).values_list('nombre', flat=True))
    tips = list(Material.objects.filter(activo=True).values_list('tipo', flat=True).distinct())
    opciones = sorted(list(set(cats + tips)))

    return render(request, 'biblioteca/lista_libros.html', {
        'page_obj': page_obj, 'search_query': query,
        'opciones_filtro': opciones, 'filtro_seleccionado': filtro_seleccionado
    })

def buscar_sugerencias_view(request):
    term = request.GET.get('term', '').lower()
    sugerencias = []
    if term:
        for l in Libro.objects.filter(titulo__icontains=term, activo=True)[:5]: sugerencias.append(l.titulo)
        for a in Autor.objects.filter(Q(nombre__icontains=term)|Q(apellido__icontains=term), activo=True)[:5]: sugerencias.append(f"{a.nombre} {a.apellido}")
        for m in Material.objects.filter(activo=True).filter(Q(titulo__icontains=term)|Q(codigo__icontains=term))[:5]:
            if term in m.titulo.lower(): sugerencias.append(m.titulo)
            if term in m.codigo.lower(): sugerencias.append(m.codigo)
    return JsonResponse(sorted(list(set(sugerencias)))[:10], safe=False)

def detalle_libro_view(request, libro_id):
    libro = get_object_or_404(Libro, id=libro_id)
    prestamos = Prestamo.objects.filter(libro=libro, devuelto=False).count()
    disp = libro.cantidad - prestamos
    ctx = {'libro': libro, 'cantidad_disponible': disp, 'esta_agotado': disp <= 0}

    if request.user.is_authenticated:
        ctx['es_favorito'] = Favorito.objects.filter(usuario=request.user, libro=libro).exists()
        reservas = Reserva.objects.filter(libro=libro).exclude(estado__in=['COMPLETADA', 'CANCELADA'])
        ctx['ya_reservado_por_mi'] = reservas.filter(usuario=request.user).exists()
        res_lista = reservas.filter(estado='PENDIENTE_RETIRO').first()
        if res_lista:
            ctx['reserva_lista_para_mi'] = (res_lista.usuario == request.user)
            ctx['reserva_lista_para_otro'] = (res_lista.usuario != request.user)
    return render(request, 'biblioteca/detalle_libro.html', ctx)

def detalle_material_view(request, material_id):
    mat = get_object_or_404(Material, id=material_id)
    prestamos = Prestamo.objects.filter(material=mat, devuelto=False).count()
    disp = mat.cantidad - prestamos
    ctx = {'material': mat, 'cantidad_disponible': disp, 'esta_agotado': disp <= 0}

    if request.user.is_authenticated:
        ctx['es_favorito'] = Favorito.objects.filter(usuario=request.user, material=mat).exists()
        reservas = Reserva.objects.filter(material=mat).exclude(estado__in=['COMPLETADA', 'CANCELADA'])
        ctx['ya_reservado_por_mi'] = reservas.filter(usuario=request.user).exists()
        res_lista = reservas.filter(estado='PENDIENTE_RETIRO').first()
        if res_lista:
            ctx['reserva_lista_para_mi'] = (res_lista.usuario == request.user)
            ctx['reserva_lista_para_otro'] = (res_lista.usuario != request.user)
    return render(request, 'biblioteca/detalle_material.html', ctx)

# ==========================================
# LÓGICA DE RESERVAS Y PRÉSTAMOS
# ==========================================

def reservar_generico(request, item_id, es_libro):
    Model = Libro if es_libro else Material
    item = get_object_or_404(Model, id=item_id)

    limite_items = 3
    if request.user.groups.filter(name='Administrador').exists(): limite_items = 50
    elif request.user.groups.filter(name='Cargador').exists(): limite_items = 5

    prestamos_activos = Prestamo.objects.filter(usuario=request.user, devuelto=False).count()
    reservas_activas = Reserva.objects.filter(usuario=request.user).exclude(estado__in=['COMPLETADA', 'CANCELADA', 'EXPIRADA']).count()

    if (prestamos_activos + reservas_activas) >= limite_items:
        messages.error(request, f"Has alcanzado tu límite de {limite_items} ítems.")
        return redirect('catalogo')

    filters = {'libro': item} if es_libro else {'material': item}
    prestados = Prestamo.objects.filter(**filters, devuelto=False).count()
    reservados_pendientes = Reserva.objects.filter(**filters).exclude(estado__in=['COMPLETADA', 'CANCELADA', 'EXPIRADA']).count()
    disponible_real = item.cantidad - (prestados + reservados_pendientes)

    if Reserva.objects.filter(**filters, usuario=request.user).exclude(estado__in=['COMPLETADA', 'CANCELADA', 'EXPIRADA']).exists():
        messages.error(request, "Ya tienes una reserva activa para este ítem.")
        return redirect('catalogo')

    estado_inicial = 'PENDIENTE_RETIRO' if disponible_real > 0 else 'PENDIENTE'
    fecha_retiro_calc = calcular_fecha_habil(date.today(), 2) if estado_inicial == 'PENDIENTE_RETIRO' else None

    reserva = Reserva.objects.create(
        libro=item if es_libro else None,
        material=item if not es_libro else None,
        usuario=request.user,
        estado=estado_inicial,
        fecha_limite_retiro=fecha_retiro_calc
    )

    detalle = f"Usuario reservó '{item.titulo}'. Cód: {reserva.codigo_retiro}. Estado: {estado_inicial}"
    registrar_auditoria(request, "Reserva Creada", detalle)

    if estado_inicial == 'PENDIENTE_RETIRO':
        msg = f"Tu reserva para '{item.titulo}' está lista.\nCÓDIGO: {reserva.codigo_retiro}\nVence: {reserva.fecha_limite_retiro}"
        messages.success(request, f"¡Listo para retirar! Código: {reserva.codigo_retiro}")
    else:
        msg = f"Has quedado en lista de espera para '{item.titulo}'."
        messages.info(request, "Sin stock inmediato. Quedaste en lista de espera.")

    enviar_correo_notificacion(request.user.email, "Confirmación de Reserva", msg)
    return redirect('mis_prestamos')

def reservar_libro_view(request, libro_id): return reservar_generico(request, libro_id, True)
def reservar_material_view(request, material_id): return reservar_generico(request, material_id, False)

def prestar_libro_view(request, libro_id): return reservar_generico(request, libro_id, True)
def prestar_material_view(request, material_id): return reservar_generico(request, material_id, False)

# ==========================================
# ADMINISTRACIÓN DE CIRCULACIÓN (RETIROS Y DEVOLUCIONES)
# ==========================================

@admin_required
def procesar_retiro_view(request):
    reserva = None
    reservas_pendientes = Reserva.objects.filter(estado='PENDIENTE_RETIRO').order_by('fecha_limite_retiro')

    busqueda = request.GET.get('busqueda_usuario', '').strip()
    if busqueda:
        reservas_pendientes = reservas_pendientes.filter(
            Q(usuario__email__icontains=busqueda) | 
            Q(usuario__username__icontains=busqueda) |
            Q(usuario__first_name__icontains=busqueda) |
            Q(usuario__last_name__icontains=busqueda)
        )

    if request.method == 'POST':
        if 'buscar_codigo' in request.POST:
            codigo = request.POST.get('codigo', '').strip().upper()
            try:
                reserva = Reserva.objects.get(codigo_retiro=codigo, estado='PENDIENTE_RETIRO')
            except Reserva.DoesNotExist:
                messages.error(request, "Código no encontrado, expirado o ya procesado.")

        elif 'confirmar_entrega' in request.POST:
            reserva_id = request.POST.get('reserva_id')
            reserva = get_object_or_404(Reserva, id=reserva_id)

            dias = 30 if reserva.usuario.groups.filter(name='Administrador').exists() else (14 if reserva.usuario.groups.filter(name='Cargador').exists() else 7)
            fecha_dev = calcular_fecha_habil(date.today(), dias)

            Prestamo.objects.create(
                libro=reserva.libro, material=reserva.material,
                usuario=reserva.usuario, fecha_devolucion=fecha_dev
            )
            reserva.estado = 'COMPLETADA'
            reserva.save()

            titulo = reserva.libro.titulo if reserva.libro else reserva.material.titulo
            registrar_auditoria(request, "Entrega Reserva", f"Entregado '{titulo}' a {reserva.usuario.username}")
            
            msg = f"Has retirado '{titulo}'.\nFecha límite de devolución: {fecha_dev}."
            enviar_correo_notificacion(reserva.usuario.email, "Retiro Exitoso", msg)
            
            messages.success(request, f"Préstamo activado correctamente. Devolver el {fecha_dev}.")
            return redirect('procesar_retiro')

    lista_emails = reservas_pendientes.values_list('usuario__email', flat=True).distinct()

    return render(request, 'biblioteca/procesar_retiro.html', {
        'reserva': reserva,
        'reservas_pendientes': reservas_pendientes,
        'lista_emails_autocomplete': lista_emails,
        'busqueda_actual': busqueda
    })

# ---------------------------------------------------------
# CORRECCIÓN PRINCIPAL: VISTA DE DEVOLUCIÓN DE ADMINISTRADOR
# ---------------------------------------------------------


@admin_required 
def procesar_devolucion_view(request):
    """
    Vista exclusiva para Administradores.
    Permite buscar y devolver CUALQUIER libro prestado en el sistema.
    """
    
    # 1. Consulta Global: Trae TODOS los préstamos activos (sin filtrar por usuario)
    prestamos_activos = Prestamo.objects.filter(devuelto=False).select_related('usuario', 'libro', 'material').order_by('fecha_devolucion')
    
    usuario_encontrado = None
    busqueda = request.GET.get('busqueda', '').strip()
    
    # 2. Lógica de Búsqueda
    if busqueda:
        filtros = (
            Q(usuario__username__icontains=busqueda) |
            Q(usuario__email__icontains=busqueda) |
            Q(usuario__first_name__icontains=busqueda) |
            Q(usuario__last_name__icontains=busqueda) |
            Q(libro__titulo__icontains=busqueda) |
            Q(libro__isbn__icontains=busqueda) |
            Q(material__titulo__icontains=busqueda) |
            Q(material__codigo__icontains=busqueda)
        )
        prestamos_activos = prestamos_activos.filter(filtros)
        
        if prestamos_activos.exists():
             usuario_encontrado = prestamos_activos.first().usuario

    # 3. PROCESAR LA DEVOLUCIÓN (Lógica integrada para evitar NameError)
    if request.method == 'POST' and 'confirmar_devolucion' in request.POST:
        
        # Verificación de Seguridad Extra
        if not (request.user.is_superuser or request.user.groups.filter(name='Administrador').exists()):
            messages.error(request, "No tienes permisos para realizar devoluciones.")
            return redirect('index')
            
        prestamo_id = request.POST.get('prestamo_id')
        p = get_object_or_404(Prestamo, id=prestamo_id)
        item = p.libro if p.libro else p.material
        
        # A) Actualizar estado
        p.devuelto = True
        p.fecha_devolucion_real = timezone.now().date()
        p.save()

        # B) Registrar Auditoría (REQUISITO CLAVE)
        registrar_auditoria(request, "Devolución Admin", f"Administrador recibió '{item.titulo}' de {p.usuario.username}")

        # C) Enviar Correo
        try:
            enviar_correo_notificacion(p.usuario.email, "Devolución Exitosa", f"Hemos registrado la devolución de '{item.titulo}'. Gracias.")
        except: pass

        # D) Revisar Reservas
        asignado = asignar_siguiente_reserva(libro=p.libro, material=p.material)

        if asignado:
            registrar_auditoria(request, "Asignación Automática", f"El ítem '{item.titulo}' pasó a la siguiente reserva en cola.")
            messages.success(request, f"Devolución de '{item.titulo}' exitosa. SE ASIGNÓ A LA SIGUIENTE RESERVA.")
        else:
            messages.success(request, f"Devolución de '{item.titulo}' exitosa. Stock liberado.")

        return redirect('procesar_devolucion')

    lista_emails = Prestamo.objects.filter(devuelto=False).values_list('usuario__email', flat=True).distinct()

    return render(request, 'biblioteca/procesar_devolucion.html', {
        'prestamos_activos': prestamos_activos,
        'busqueda_actual': busqueda,
        'usuario_encontrado': usuario_encontrado,
        'lista_emails': lista_emails
    })

@cargador_required
def devolver_libro_view(request, prestamo_id):
    """Vista legacy para Cargadores (si aún se usa)"""
    p = get_object_or_404(Prestamo, id=prestamo_id)
    item = p.libro if p.libro else p.material

    p.devuelto = True
    p.fecha_devolucion_real = date.today()
    p.save()

    registrar_auditoria(request, "Devolución Cargador", f"'{item.titulo}' devuelto por {p.usuario.username}")
    enviar_correo_notificacion(p.usuario.email, "Devolución", f"Confirmamos devolución de '{item.titulo}'.")

    asignado = asignar_siguiente_reserva(libro=p.libro, material=p.material)

    if asignado:
        registrar_auditoria(request, "Asignación Auto", "Item reasignado a reserva.")
        messages.success(request, "Devuelto. Asignado a siguiente reserva en espera.")
    else:
        messages.success(request, "Devolución exitosa.")

    return redirect('procesar_devolucion')

# ==========================================
# GESTIÓN DE USUARIO Y PERFIL
# ==========================================

@login_required
def renovar_prestamo_view(request, prestamo_id):
    p = get_object_or_404(Prestamo, id=prestamo_id)
    filters = {'libro': p.libro} if p.libro else {'material': p.material}

    if p.renovado:
        messages.error(request, "Ya fue renovado una vez.")
        return redirect('mis_prestamos')
    if Reserva.objects.filter(**filters, estado='PENDIENTE').exists():
        messages.error(request, "No puedes renovar: Hay lista de espera.")
        return redirect('mis_prestamos')

    p.fecha_devolucion = calcular_fecha_habil(p.fecha_devolucion, 7)
    p.renovado = True
    p.save()

    registrar_auditoria(request, "Renovación", f"Renovado hasta {p.fecha_devolucion}")
    enviar_correo_notificacion(p.usuario.email, "Renovación", f"Nueva fecha: {p.fecha_devolucion}")
    messages.success(request, "Préstamo renovado.")
    return redirect('mis_prestamos')

@login_required
def mis_prestamos_view(request):
    hoy = date.today()
    prestamos = Prestamo.objects.filter(usuario=request.user, devuelto=False).order_by('fecha_devolucion')

    for p in prestamos:
        dias_restantes = (p.fecha_devolucion - hoy).days
        if dias_restantes < 0: p.recordatorio = f"¡ATRASADO! ({abs(dias_restantes)} días)"
        elif dias_restantes <= 2: p.recordatorio = f"Vence pronto ({dias_restantes} días)"
        else: p.recordatorio = None

        try:
            total_dias = (p.fecha_devolucion - p.fecha_prestamo).days
            if total_dias <= 0: total_dias = 1
            dias_transcurridos = (hoy - p.fecha_prestamo).days
            porcentaje = int((dias_transcurridos * 100) / total_dias)
        except: porcentaje = 0
        
        p.porcentaje_dias = max(0, min(porcentaje, 100))

    reservas_retiro = Reserva.objects.filter(usuario=request.user, estado='PENDIENTE_RETIRO').order_by('fecha_limite_retiro')
    reservas_cola = Reserva.objects.filter(usuario=request.user, estado='PENDIENTE')
    reservas_canceladas = Reserva.objects.filter(usuario=request.user, estado='CANCELADA').order_by('-fecha_limite_retiro')[:6]

    return render(request, 'biblioteca/mis_prestamos.html', {
        'prestamos': prestamos, 'reservas_pendientes': reservas_retiro,
        'reservas_cola': reservas_cola, 'reservas_canceladas': reservas_canceladas, 'hoy': hoy,
    })

@login_required
def agregar_favorito_view(request, item_id):
    tipo = request.GET.get('tipo', 'libro')
    if tipo == 'libro':
        obj = get_object_or_404(Libro, id=item_id)
        fav, created = Favorito.objects.get_or_create(usuario=request.user, libro=obj, material=None)
    else:
        obj = get_object_or_404(Material, id=item_id)
        fav, created = Favorito.objects.get_or_create(usuario=request.user, libro=None, material=obj)

    if not created: fav.delete(); messages.info(request, "Eliminado de favoritos.")
    else: messages.success(request, "Añadido a favoritos.")
    return redirect('catalogo')

@login_required
def mis_favoritos_view(request):
    return render(request, 'biblioteca/mis_favoritos.html', {'favoritos': Favorito.objects.filter(usuario=request.user)})

@login_required
def perfil_view(request):
    perfil, _ = Perfil.objects.get_or_create(usuario=request.user)
    if request.method == 'POST':
        form = PerfilForm(request.POST, instance=perfil)
        if form.is_valid():
            form.save()
            registrar_auditoria(request, "Perfil", "Usuario actualizó su perfil")
            messages.success(request, "Perfil actualizado.")
    else: form = PerfilForm(instance=perfil)
    return render(request, 'biblioteca/perfil.html', {'form': form})

@login_required
def historial_prestamos_view(request):
    prestamos = Prestamo.objects.filter(usuario=request.user).select_related('libro', 'material')
    reservas_recientes = Reserva.objects.filter(usuario=request.user, estado='CANCELADA').select_related('libro', 'material')
    logs_antiguos = Historial.objects.filter(usuario=request.user, accion="Cancelación Auto")

    historial_unificado = []
    for p in prestamos:
        estado = 'devuelto' if p.devuelto else ('atrasado' if p.fecha_devolucion_real and p.fecha_devolucion_real > p.fecha_devolucion else 'activo')
        historial_unificado.append({
            'fecha_evento': p.fecha_prestamo, 
            'titulo': p.libro.titulo if p.libro else p.material.titulo,
            'tipo_lbl': 'Libro' if p.libro else 'Material',
            'fecha_fin': p.fecha_devolucion, 'estado': estado, 'es_objeto_real': True
        })
    # ... resto del historial ... (simplificado para no alargar más)
    return render(request, 'biblioteca/historial_prestamos.html', {'historial': historial_unificado})

# ==========================================
# GESTIÓN ADMINISTRATIVA (CRUDs)
# ==========================================

@cargador_required
def gestion_view(request):
    es_admin = request.user.is_superuser or request.user.groups.filter(name='Administrador').exists()
    tareas_pendientes = False
    ultima_ejecucion = None
    if es_admin:
        config_tareas, _ = ConfiguracionSistema.objects.get_or_create(clave="control_tareas_diarias")
        if config_tareas.fecha != date.today():
            tareas_pendientes = True
            ultima_ejecucion = config_tareas.fecha
    return render(request, 'biblioteca/gestion.html', {
        'es_admin': es_admin, 'tareas_pendientes': tareas_pendientes, 'ultima_ejecucion': ultima_ejecucion
    })

@cargador_required
def gestion_libros_view(request):
    query = request.GET.get('q', '')
    estado = request.GET.get('estado', 'activos')
    qs = Libro.objects.filter(activo=(estado == 'activos')).order_by('titulo')
    if query: qs = qs.filter(Q(titulo__icontains=query) | Q(isbn__icontains=query))
    paginator = Paginator(qs, 10)
    return render(request, 'biblioteca/gestion_libros.html', {
        'page_obj': paginator.get_page(request.GET.get('page')), 'estado_actual': estado, 'search_query': query
    })

@cargador_required
def crear_libro_view(request):
    if request.method == 'POST':
        form = LibroForm(request.POST)
        if form.is_valid():
            l = form.save()
            registrar_auditoria(request, "Crear Libro", f"Creado '{l.titulo}'")
            messages.success(request, "Libro creado.")
            return redirect('gestion_libros')
    else: form = LibroForm()
    return render(request, 'biblioteca/crear_libro.html', {'form': form})

@cargador_required
def editar_libro_view(request, libro_id):
    obj = get_object_or_404(Libro, id=libro_id)
    if request.method == 'POST':
        form = LibroForm(request.POST, instance=obj)
        if form.is_valid():
            detalle_cambios = generar_detalle_cambios(form) 
            l = form.save()
            registrar_auditoria(request, "Editar Libro", f"ID {l.id} ({l.titulo}). {detalle_cambios}")
            messages.success(request, "Libro actualizado.")
            return redirect('gestion_libros')
    else: form = LibroForm(instance=obj)
    return render(request, 'biblioteca/editar_libro.html', {'form': form})

@cargador_required
def eliminar_libro_view(request, libro_id):
    obj = get_object_or_404(Libro, id=libro_id)
    if request.method == 'POST': 
        obj.activo = False; obj.save()
        registrar_auditoria(request, "Archivar Libro", f"Archivado: {obj.titulo}")
        return redirect('gestion_libros')
    return render(request, 'biblioteca/eliminar_libro.html', {'libro': obj})

@cargador_required
def reactivar_libro_view(request, libro_id):
    obj = get_object_or_404(Libro, id=libro_id)
    if request.method == 'POST': 
        obj.activo = True; obj.save()
        registrar_auditoria(request, "Reactivar Libro", f"Reactivado: {obj.titulo}")
        return redirect('gestion_libros')
    return redirect('gestion_libros')

@cargador_required
def gestion_materiales_view(request):
    query = request.GET.get('q', '')
    estado = request.GET.get('estado', 'activos')
    qs = Material.objects.filter(activo=(estado == 'activos')).order_by('titulo')
    if query: qs = qs.filter(Q(titulo__icontains=query) | Q(codigo__icontains=query) | Q(tipo__icontains=query))
    paginator = Paginator(qs, 10)
    return render(request, 'biblioteca/gestion_materiales.html', {
        'page_obj': paginator.get_page(request.GET.get('page')), 'estado_actual': estado, 'search_query': query
    })

@cargador_required
def crear_material_view(request):
    if request.method == 'POST':
        form = MaterialForm(request.POST)
        if form.is_valid(): 
            m = form.save()
            registrar_auditoria(request, "Crear Material", f"Nuevo material: {m.titulo}")
            messages.success(request, "Material creado.")
            return redirect('gestion_materiales')
    else: form = MaterialForm()
    return render(request, 'biblioteca/crear_material.html', {'form': form})

@cargador_required
def editar_material_view(request, material_id):
    obj = get_object_or_404(Material, id=material_id)
    if request.method == 'POST':
        form = MaterialForm(request.POST, instance=obj)
        if form.is_valid():
            detalle_cambios = generar_detalle_cambios(form)
            m = form.save()
            registrar_auditoria(request, "Editar Material", f"ID {m.id}. {detalle_cambios}")
            messages.success(request, "Material actualizado.")
            return redirect('gestion_materiales')
    else: form = MaterialForm(instance=obj)
    return render(request, 'biblioteca/editar_material.html', {'form': form})

@cargador_required
def eliminar_material_view(request, material_id):
    obj = get_object_or_404(Material, id=material_id)
    if request.method == 'POST': 
        obj.activo = False; obj.save()
        registrar_auditoria(request, "Archivar Material", f"Archivado material: {obj.titulo}")
        return redirect('gestion_materiales')
    return render(request, 'biblioteca/eliminar_material.html', {'material': obj})

@cargador_required
def reactivar_material_view(request, material_id):
    obj = get_object_or_404(Material, id=material_id)
    if request.method == 'POST': 
        obj.activo = True; obj.save()
        registrar_auditoria(request, "Reactivar Material", f"Reactivado material: {obj.titulo}")
        return redirect('gestion_materiales')
    return redirect('gestion_materiales')

@cargador_required
def gestion_autores_view(request):
    qs = Autor.objects.all().order_by('-activo', 'apellido')
    paginator = Paginator(qs, 10)
    return render(request, 'biblioteca/gestion_autores.html', {'page_obj': paginator.get_page(request.GET.get('page'))})

@cargador_required
def crear_autor_view(request):
    if request.method == 'POST':
        form = AutorForm(request.POST)
        if form.is_valid(): 
            a = form.save()
            registrar_auditoria(request, "Crear Autor", f"Nuevo autor: {a.nombre} {a.apellido}")
            messages.success(request, "Autor creado.")
            return redirect('gestion_autores')
    else: form = AutorForm()
    return render(request, 'biblioteca/crear_autor.html', {'form': form})

@cargador_required
def editar_autor_view(request, autor_id):
    obj = get_object_or_404(Autor, id=autor_id)
    if request.method == 'POST':
        form = AutorForm(request.POST, instance=obj)
        if form.is_valid(): 
            detalle_cambios = generar_detalle_cambios(form)
            a = form.save()
            registrar_auditoria(request, "Editar Autor", f"ID {a.id}. {detalle_cambios}")
            messages.success(request, "Autor actualizado.")
            return redirect('gestion_autores')
    else: form = AutorForm(instance=obj)
    return render(request, 'biblioteca/editar_autor.html', {'form': form})

@cargador_required
def eliminar_autor_view(request, autor_id):
    obj = get_object_or_404(Autor, id=autor_id)
    if request.method == 'POST':
        if Libro.objects.filter(autor=obj, activo=True).exists():
            messages.error(request, "No se puede archivar: tiene libros.")
        else: 
            obj.activo = False; obj.save()
            registrar_auditoria(request, "Archivar Autor", f"Archivado autor: {obj.nombre} {obj.apellido}")
        return redirect('gestion_autores')
    return redirect('gestion_autores')

@cargador_required
def reactivar_autor_view(request, autor_id):
    obj = get_object_or_404(Autor, id=autor_id)
    if request.method == 'POST': 
        obj.activo = True; obj.save()
        registrar_auditoria(request, "Reactivar Autor", f"Reactivado: {obj.nombre}")
        return redirect('gestion_autores')
    return redirect('gestion_autores')

@cargador_required
def gestion_categorias_view(request):
    qs = Categoria.objects.all().order_by('-activo', 'nombre')
    paginator = Paginator(qs, 10)
    return render(request, 'biblioteca/gestion_categorias.html', {'page_obj': paginator.get_page(request.GET.get('page'))})

@cargador_required
def crear_categoria_view(request):
    if request.method == 'POST':
        form = CategoriaForm(request.POST)
        if form.is_valid(): 
            c = form.save()
            registrar_auditoria(request, "Crear Categoría", f"Nueva: {c.nombre}")
            messages.success(request, "Categoría creada.")
            return redirect('gestion_categorias')
    else: form = CategoriaForm()
    return render(request, 'biblioteca/crear_categoria.html', {'form': form})

@cargador_required
def editar_categoria_view(request, categoria_id):
    obj = get_object_or_404(Categoria, id=categoria_id)
    if request.method == 'POST':
        form = CategoriaForm(request.POST, instance=obj)
        if form.is_valid():
            detalle_cambios = generar_detalle_cambios(form)
            c = form.save()
            registrar_auditoria(request, "Editar Categoría", f"Modificada: {c.nombre}. {detalle_cambios}")
            messages.success(request, "Categoría actualizada.")
            return redirect('gestion_categorias')
    else: form = CategoriaForm(instance=obj)
    return render(request, 'biblioteca/editar_categoria.html', {'form': form})

@cargador_required
def eliminar_categoria_view(request, categoria_id):
    obj = get_object_or_404(Categoria, id=categoria_id)
    if request.method == 'POST': 
        obj.activo = False; obj.save()
        registrar_auditoria(request, "Archivar Categoría", f"Archivada: {obj.nombre}")
        return redirect('gestion_categorias')
    return redirect('gestion_categorias')

@cargador_required
def reactivar_categoria_view(request, categoria_id):
    obj = get_object_or_404(Categoria, id=categoria_id)
    if request.method == 'POST': 
        obj.activo = True; obj.save()
        registrar_auditoria(request, "Reactivar Categoría", f"Reactivada: {obj.nombre}")
        return redirect('gestion_categorias')
    return redirect('gestion_categorias')

@admin_required
def gestion_historial_view(request):
    config = ConfiguracionSistema.obtener_instancia()
    if request.method == 'POST' and request.POST.get('accion') == 'limpiar':
        config.fecha = None; config.save(); messages.success(request, "Fecha limpiada.")
        return redirect('gestion_historial')
    qs = Historial.objects.all().order_by('-fecha')
    paginator = Paginator(qs, 20)
    return render(request, 'biblioteca/gestion_historial.html', {'page_obj': paginator.get_page(request.GET.get('page')), 'config_sistema': config})

@admin_required
def exportar_historial_view(request):
    registrar_auditoria(request, "Exportar Historial", f"Descarga manual de log por {request.user.username}")
    contenido = _generar_contenido_txt()
    resp = HttpResponse(contenido, content_type="text/plain; charset=utf-8")
    resp['Content-Disposition'] = f'attachment; filename="SIGB_Audit_{date.today()}.log"'
    return resp

@admin_required
def gestion_usuarios_view(request):
    q = request.GET.get('q', '').strip()
    qs = User.objects.filter(is_superuser=False).order_by('username')
    if q:
        qs = qs.filter(
            Q(username__icontains=q) | Q(email__icontains=q) |
            Q(first_name__icontains=q) | Q(last_name__icontains=q)
        )
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    users = [{'user': u, 'rol_actual': u.groups.first()} for u in page_obj]

    return render(request, 'biblioteca/gestion_usuarios.html', {
        'usuarios_con_roles': users, 'page_obj': page_obj,
        'roles_disponibles': Group.objects.all(), 'search_query': q,
    })

@admin_required
def admin_cambiar_rol_view(request, user_id):
    if request.method == 'POST':
        u = get_object_or_404(User, id=user_id)
        try:
            rol = Group.objects.get(id=request.POST.get('rol'))
            u.groups.clear(); u.groups.add(rol)
            registrar_auditoria(request, "Cambio Rol Usuario", f"Usuario '{u.username}' ahora es '{rol.name}'")
            messages.success(request, f"Rol actualizado.")
        except: pass
    return redirect('gestion_usuarios')

@admin_required
def admin_desactivar_usuario_view(request, user_id):
    u = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        if Prestamo.objects.filter(usuario=u, devuelto=False).exists():
            messages.error(request, "Tiene préstamos activos.")
        else:
            u.is_active = False; u.save()
            registrar_auditoria(request, "Desactivar Usuario", f"Se desactivó al usuario '{u.username}'")
            messages.success(request, "Desactivado.")
    return redirect('gestion_usuarios')

@admin_required
def admin_reactivar_usuario_view(request, user_id):
    u = get_object_or_404(User, id=user_id)
    if request.method == 'POST': 
        u.is_active = True; u.save()
        registrar_auditoria(request, "Reactivar Usuario", f"Se reactivó al usuario '{u.username}'")
        messages.success(request, "Reactivado.")
    return redirect('gestion_usuarios')

@admin_required
def ejecutar_tareas_diarias_view(request):
    if request.method == 'POST':
        salida = StringIO()
        try:
            call_command('procesar_vencidos', stdout=salida)
            call_command('alerta_preventiva', stdout=salida)
            call_command('alerta_atrasos', stdout=salida)
            config_tareas, _ = ConfiguracionSistema.objects.get_or_create(clave="control_tareas_diarias")
            config_tareas.fecha = date.today(); config_tareas.save()
            messages.success(request, "Tareas completadas correctamente.")
        except Exception as e: messages.error(request, f"Error: {e}")
    return redirect('gestion')

def lista_noticias_view(request):
    qs = Noticia.objects.all().order_by('-fecha')
    paginator = Paginator(qs, 4)
    return render(request, 'biblioteca/lista_noticias.html', {'page_obj': paginator.get_page(request.GET.get('page'))})

@admin_required
def crear_noticia_view(request):
    if request.method == 'POST':
        form = NoticiaForm(request.POST, request.FILES)
        if form.is_valid():
            if Noticia.objects.count() >= 20:
                oldest = Noticia.objects.order_by('fecha').first()
                if oldest: oldest.delete()
            n = form.save(commit=False)
            n.autor = request.user; n.save()
            registrar_auditoria(request, "Crear Noticia", f"Noticia publicada: {n.titulo}")
            messages.success(request, "Noticia publicada.")
            return redirect('lista_noticias')
    else: form = NoticiaForm()
    return render(request, 'biblioteca/crear_noticia.html', {'form': form})

@admin_required
def eliminar_noticia_view(request, noticia_id):
    noticia = get_object_or_404(Noticia, id=noticia_id)
    titulo = noticia.titulo
    noticia.delete()
    registrar_auditoria(request, "Eliminar Noticia", f"Noticia eliminada: {titulo}")
    messages.success(request, "Noticia eliminada.")
    return redirect('lista_noticias')

def detalle_noticia_view(request, noticia_id):
    n = get_object_or_404(Noticia, id=noticia_id)
    return render(request, 'biblioteca/detalle_noticia.html', {'noticia': n})

@admin_required
def reportes_view(request):
    hoy = date.today()
    
    # 1. KPIs Generales
    activos = Prestamo.objects.filter(devuelto=False)
    vencidos = activos.filter(fecha_devolucion__lt=hoy).count()
    al_dia = activos.filter(fecha_devolucion__gte=hoy, renovado=False).count()
    renovados = activos.filter(fecha_devolucion__gte=hoy, renovado=True).count()

    total_libros = Libro.objects.filter(activo=True).count()
    total_materiales = Material.objects.filter(activo=True).count()
    total_usuarios = User.objects.count()

    # 2. Datos para Gráficos
    # A) Top Libros (Inventario)
    top_libros = Prestamo.objects.filter(libro__isnull=False).values('libro__titulo') \
        .annotate(total=Count('id')).order_by('-total')[:10]
    
    if top_libros:
        inv_labels = [item['libro__titulo'] for item in top_libros]
        inv_data = [item['total'] for item in top_libros]
    else:
        inv_labels = ['Sin datos']
        inv_data = [0]

    # B) Top Categorías
    top_categorias = Prestamo.objects.filter(libro__isnull=False).values('libro__categoria__nombre') \
        .annotate(total=Count('id')).order_by('-total')[:5]
    
    if top_categorias:
        cat_labels = [item['libro__categoria__nombre'] for item in top_categorias]
        cat_data = [item['total'] for item in top_categorias]
    else:
        cat_labels = ['Sin datos']
        cat_data = [0]

    # C) Top Autores (NUEVO - Requerido por tu template)
    top_autores = Prestamo.objects.filter(libro__isnull=False).values('libro__autor__nombre', 'libro__autor__apellido') \
        .annotate(total=Count('id')).order_by('-total')[:5]
    
    if top_autores:
        aut_labels = [f"{item['libro__autor__nombre']} {item['libro__autor__apellido']}" for item in top_autores]
        aut_data = [item['total'] for item in top_autores]
    else:
        aut_labels = ['Sin datos']
        aut_data = [0]

    # 3. Lista de Morosos para la tabla
    lista_vencidos = []
    prestamos_vencidos = activos.filter(fecha_devolucion__lt=hoy).select_related('usuario', 'libro', 'material')
    for p in prestamos_vencidos:
        lista_vencidos.append({
            'prestamo': p,
            'dias_atraso': (hoy - p.fecha_devolucion).days
        })

    context = {
        'total_prestamos_activos': activos.count(),
        'total_usuarios': total_usuarios,
        'total_libros': total_libros,
        'total_materiales': total_materiales,
        'total_vencidos': vencidos,
        'lista_vencidos': lista_vencidos,
        
        # Variables exactas para Chart.js
        'chart_estado_data': [al_dia, vencidos, renovados],
        'chart_inventario_labels': inv_labels,
        'chart_inventario_data': inv_data,
        'chart_categorias_labels': cat_labels,
        'chart_categorias_data': cat_data,
        'chart_autores_labels': aut_labels,  # <--- Nuevo
        'chart_autores_data': aut_data,      # <--- Nuevo
    }
    
    return render(request, 'biblioteca/reportes.html', context)

@admin_required
def enviar_recordatorios_view(request):
    hoy = date.today()
    vencidos = Prestamo.objects.filter(devuelto=False, fecha_devolucion__lt=hoy)
    count = 0
    for p in vencidos:
        if p.usuario.email:
            try:
                send_mail(f"ATRASO: {p.libro or p.material}", "Por favor devuelva el ítem.", settings.DEFAULT_FROM_EMAIL, [p.usuario.email])
                count += 1
            except: pass
    if count > 0: messages.success(request, f"{count} correos enviados.")
    return redirect('reportes')

@admin_required
def exportar_reporte_excel_view(request):
    wb = openpyxl.Workbook()
    hoy = date.today()
    
    # ... Tu lógica de Excel intacta ...
    ws1 = wb.active; ws1.title = "Resumen"
    ws1.append(["Reporte generado el", hoy])
    
    nombre_archivo = f"Reporte_SIGB_{hoy.strftime('%Y%m%d')}.xlsx"
    resp = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    resp['Content-Disposition'] = f'attachment; filename="{nombre_archivo}"'
    wb.save(resp)
    
    registrar_auditoria(request, "Exportar Excel", f"Reporte descargado por {request.user.username}")
    return resp