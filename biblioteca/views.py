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

# Importación de Modelos y Formularios Locales
from .models import (
    Libro, Prestamo, Autor, Categoria, Reserva, Favorito,
    Perfil, Material, Historial, ConfiguracionSistema, Noticia
)
from .forms import (
    LibroForm, AutorForm, CategoriaForm, PerfilForm,
    MaterialForm, NoticiaForm
)
from .decorators import admin_required, cargador_required
from .utils import enviar_correo_notificacion, asignar_siguiente_reserva

# ==============================================================================
# 1. UTILIDADES INTERNAS (AUDITORÍA Y RESPALDOS)
# ==============================================================================

def registrar_auditoria(request, accion, detalle):
    """Registra una acción en la base de datos de historial."""
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
    """
    Compara los datos iniciales con los nuevos y genera un texto de resumen.
    Detecta QUÉ campos cambiaron específicamente.
    """
    if not form.changed_data:
        return "Se guardó sin realizar cambios."
    
    cambios = []
    for campo in form.changed_data:
        # Obtenemos el valor antiguo (initial) y el nuevo (cleaned_data)
        antiguo = form.initial.get(campo, 'N/A')
        nuevo = form.cleaned_data.get(campo, 'N/A')
        
        # Convertimos a string y cortamos si es muy largo (para que quepa en la BD)
        str_antiguo = str(antiguo)[:15] + '...' if len(str(antiguo)) > 15 else str(antiguo)
        str_nuevo = str(nuevo)[:15] + '...' if len(str(nuevo)) > 15 else str(nuevo)
        
        cambios.append(f"[{campo}: {str_antiguo} -> {str_nuevo}]")
    
    return "Cambios: " + " ".join(cambios)

def _generar_contenido_txt():
    """Genera el texto plano para el archivo de log."""
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
    """Verifica si han pasado 28 días para generar un respaldo automático."""
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

# ==============================================================================
# 2. CATÁLOGO PÚBLICO (OPAC) Y BÚSQUEDA
# ==============================================================================

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

# ==============================================================================
# 3. VISTAS DE DETALLE
# ==============================================================================

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

# ==============================================================================
# 4. CIRCULACIÓN (RESERVAS, PRÉSTAMOS, DEVOLUCIONES)
# ==============================================================================

@login_required
def reservar_generico(request, item_id, es_libro):
    Model = Libro if es_libro else Material
    item = get_object_or_404(Model, id=item_id)

    filters = {'libro': item} if es_libro else {'material': item}
    prestados = Prestamo.objects.filter(**filters, devuelto=False).count()
    disponible = item.cantidad - prestados

    if Reserva.objects.filter(**filters, usuario=request.user).exclude(estado__in=['COMPLETADA', 'CANCELADA']).exists():
        messages.error(request, "Ya tienes una reserva activa para este ítem.")
        return redirect('catalogo')

    estado_inicial = 'PENDIENTE_RETIRO' if disponible > 0 else 'PENDIENTE'

    reserva = Reserva.objects.create(
        libro=item if es_libro else None,
        material=item if not es_libro else None,
        usuario=request.user,
        estado=estado_inicial
    )

    tipo_accion = "Reserva Lista" if estado_inicial == 'PENDIENTE_RETIRO' else "Reserva en Cola"
    detalle = f"Usuario reservó '{item.titulo}'. Cód: {reserva.codigo_retiro}. Estado: {estado_inicial}"
    registrar_auditoria(request, tipo_accion, detalle)

    if estado_inicial == 'PENDIENTE_RETIRO':
        msg = f"Tu reserva para '{item.titulo}' está lista.\nCÓDIGO: {reserva.codigo_retiro}\nVence: {reserva.fecha_limite_retiro}"
        messages.success(request, f"¡Listo para retirar! Tu código es: {reserva.codigo_retiro}")
    else:
        msg = f"Has quedado en lista de espera para '{item.titulo}'."
        messages.info(request, "Sin stock inmediato. Quedaste en lista de espera.")

    enviar_correo_notificacion(request.user.email, "Confirmación de Reserva", msg)
    return redirect('mis_prestamos')

def reservar_libro_view(request, libro_id): return reservar_generico(request, libro_id, True)
def reservar_material_view(request, material_id): return reservar_generico(request, material_id, False)
def prestar_libro_view(request, libro_id): return reservar_generico(request, libro_id, True)
def prestar_material_view(request, material_id): return reservar_generico(request, material_id, False)

@admin_required
def procesar_retiro_view(request):
    reserva = None
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
            fecha_dev = date.today() + timedelta(days=dias)

            Prestamo.objects.create(
                libro=reserva.libro, material=reserva.material,
                usuario=reserva.usuario, fecha_devolucion=fecha_dev
            )
            reserva.estado = 'COMPLETADA'
            reserva.save()

            titulo = reserva.libro.titulo if reserva.libro else reserva.material.titulo
            msg = f"Has retirado '{titulo}'.\nFecha límite de devolución: {fecha_dev}."
            enviar_correo_notificacion(reserva.usuario.email, "Retiro Exitoso", msg)
            registrar_auditoria(request, "Entrega Reserva", f"Entregado '{titulo}' a {reserva.usuario.username}")
            messages.success(request, f"Préstamo activado correctamente. Devolver el {fecha_dev}.")
            return redirect('procesar_retiro')

    return render(request, 'biblioteca/procesar_retiro.html', {'reserva': reserva})

@login_required
def devolver_libro_view(request, prestamo_id):
    p = get_object_or_404(Prestamo, id=prestamo_id)
    item = p.libro if p.libro else p.material

    p.devuelto = True
    p.fecha_devolucion_real = date.today()
    p.save()

    registrar_auditoria(request, "Devolución", f"'{item.titulo}' devuelto por {p.usuario.username}")
    enviar_correo_notificacion(p.usuario.email, "Devolución", f"Confirmamos devolución de '{item.titulo}'.")

    asignado = asignar_siguiente_reserva(libro=p.libro, material=p.material)

    if asignado:
        registrar_auditoria(request, "Asignación Auto", "El ítem devuelto fue reasignado automáticamente a la siguiente reserva.")
        messages.success(request, "Devuelto. Asignado a siguiente reserva en espera.")
    else:
        messages.success(request, "Devolución exitosa.")

    return redirect('mis_prestamos')

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

    p.fecha_devolucion += timedelta(days=7)
    p.renovado = True
    p.save()

    registrar_auditoria(request, "Renovación", f"Renovado hasta {p.fecha_devolucion}")
    enviar_correo_notificacion(p.usuario.email, "Renovación", f"Nueva fecha: {p.fecha_devolucion}")
    messages.success(request, "Préstamo renovado.")
    return redirect('mis_prestamos')

@login_required
def mis_prestamos_view(request):
    hoy = date.today()

    # Préstamos activos del usuario
    prestamos = Prestamo.objects.filter(
        usuario=request.user,
        devuelto=False
    ).order_by('fecha_devolucion')

    for p in prestamos:
        # ----------------------------
        # 1) Mensaje de recordatorio
        # ----------------------------
        dias_restantes = (p.fecha_devolucion - hoy).days

        if dias_restantes < 0:
            p.recordatorio = f"¡ATRASADO! ({abs(dias_restantes)} días)"
        elif dias_restantes <= 2:
            p.recordatorio = f"Vence pronto ({dias_restantes} días)"
        else:
            p.recordatorio = None

        # --------------------------------------
        # 2) Porcentaje de días del préstamo
        # --------------------------------------
        try:
            total_dias = (p.fecha_devolucion - p.fecha_prestamo).days
            if total_dias <= 0:
                total_dias = 1  # para evitar divisiones por cero o negativas

            dias_transcurridos = (hoy - p.fecha_prestamo).days
            porcentaje = int((dias_transcurridos * 100) / total_dias)
        except Exception:
            porcentaje = 0

        # Forzamos el porcentaje entre 0 y 100
        if porcentaje < 0:
            porcentaje = 0
        if porcentaje > 100:
            porcentaje = 100

        # Atributo dinámico que usamos en el template
        p.porcentaje_dias = porcentaje

    # Reservas listas, en cola y canceladas (como ya lo tenías)
    reservas_retiro = Reserva.objects.filter(
        usuario=request.user,
        estado='PENDIENTE_RETIRO'
    ).order_by('fecha_limite_retiro')

    reservas_cola = Reserva.objects.filter(
        usuario=request.user,
        estado='PENDIENTE'
    )

    reservas_canceladas = Reserva.objects.filter(
        usuario=request.user,
        estado='CANCELADA'
    ).order_by('-fecha_limite_retiro')[:6]

    # ⚠️ IMPORTANTE: siempre devolver un HttpResponse
    return render(request, 'biblioteca/mis_prestamos.html', {
        'prestamos': prestamos,
        'reservas_pendientes': reservas_retiro,
        'reservas_cola': reservas_cola,
        'reservas_canceladas': reservas_canceladas,
        'hoy': hoy,
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
        if form.is_valid(): form.save(); messages.success(request, "Perfil actualizado.")
    else: form = PerfilForm(instance=perfil)
    return render(request, 'biblioteca/perfil.html', {'form': form})

@login_required
def historial_prestamos_view(request):
    prestamos = Prestamo.objects.filter(usuario=request.user).select_related('libro', 'material')
    reservas_recientes = Reserva.objects.filter(usuario=request.user, estado='CANCELADA').select_related('libro', 'material')
    logs_antiguos = Historial.objects.filter(usuario=request.user, accion="Cancelación Auto")

    historial_unificado = []
    for p in prestamos:
        estado = 'activo'
        if p.devuelto: estado = 'devuelto'
        elif p.fecha_devolucion_real and p.fecha_devolucion_real > p.fecha_devolucion: estado = 'atrasado'
        
        historial_unificado.append({
            'fecha_evento': p.fecha_prestamo, 
            'titulo': p.libro.titulo if p.libro else p.material.titulo,
            'tipo_lbl': 'Libro' if p.libro else 'Material',
            'fecha_fin': p.fecha_devolucion,
            'estado': estado, 'es_objeto_real': True
        })

    for r in reservas_recientes:
        historial_unificado.append({
            'fecha_evento': r.fecha_reserva.date(),
            'titulo': r.libro.titulo if r.libro else r.material.titulo,
            'tipo_lbl': 'Libro' if r.libro else 'Material',
            'fecha_fin': r.fecha_limite_retiro,
            'estado': 'cancelado', 'es_objeto_real': True
        })

    for log in logs_antiguos:
        texto = log.detalle
        titulo_extraido = "Ítem desconocido"
        if "'" in texto:
            try: titulo_extraido = texto.split("'")[1]
            except: pass
        historial_unificado.append({
            'fecha_evento': log.fecha.date(),
            'titulo': titulo_extraido, 'tipo_lbl': 'Histórico',
            'fecha_fin': log.fecha.date(), 'estado': 'cancelado_antiguo', 'es_objeto_real': False
        })

    historial_unificado.sort(key=lambda x: x['fecha_evento'], reverse=True)
    return render(request, 'biblioteca/historial_prestamos.html', {'historial': historial_unificado})

# ==============================================================================
# 5. GESTIÓN ADMINISTRATIVA (CON AUDITORÍA DETALLADA)
# ==============================================================================

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

# --- LIBROS ---

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
            # --- MAGIA DE AUDITORÍA DETALLADA ---
            detalle_cambios = generar_detalle_cambios(form) 
            l = form.save()
            registrar_auditoria(request, "Editar Libro", f"ID {l.id} ({l.titulo}). {detalle_cambios}")
            # ------------------------------------
            messages.success(request, "Libro actualizado.")
            return redirect('gestion_libros')
    else: form = LibroForm(instance=obj)
    return render(request, 'biblioteca/editar_libro.html', {'form': form})

@cargador_required
def eliminar_libro_view(request, libro_id):
    obj = get_object_or_404(Libro, id=libro_id)
    if request.method == 'POST': 
        obj.activo = False
        obj.save()
        registrar_auditoria(request, "Archivar Libro", f"Archivado: {obj.titulo}")
        return redirect('gestion_libros')
    return render(request, 'biblioteca/eliminar_libro.html', {'libro': obj})

@cargador_required
def reactivar_libro_view(request, libro_id):
    obj = get_object_or_404(Libro, id=libro_id)
    if request.method == 'POST': 
        obj.activo = True
        obj.save()
        registrar_auditoria(request, "Reactivar Libro", f"Reactivado: {obj.titulo}")
        return redirect('gestion_libros')
    return redirect('gestion_libros')

# --- MATERIALES ---

@cargador_required
def gestion_materiales_view(request):
    query = request.GET.get('q', '')
    estado = request.GET.get('estado', 'activos')
    qs = Material.objects.filter(activo=(estado == 'activos')).order_by('titulo')
    if query:
        qs = qs.filter(Q(titulo__icontains=query) | Q(codigo__icontains=query) | Q(tipo__icontains=query))
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
            # --- MAGIA DE AUDITORÍA DETALLADA ---
            detalle_cambios = generar_detalle_cambios(form)
            m = form.save()
            registrar_auditoria(request, "Editar Material", f"ID {m.id}. {detalle_cambios}")
            # ------------------------------------
            messages.success(request, "Material actualizado.")
            return redirect('gestion_materiales')
    else: form = MaterialForm(instance=obj)
    return render(request, 'biblioteca/editar_material.html', {'form': form})

@cargador_required
def eliminar_material_view(request, material_id):
    obj = get_object_or_404(Material, id=material_id)
    if request.method == 'POST': 
        obj.activo = False
        obj.save()
        registrar_auditoria(request, "Archivar Material", f"Archivado material: {obj.titulo}")
        messages.success(request, "Material archivado correctamente.")
        return redirect('gestion_materiales')
    return render(request, 'biblioteca/eliminar_material.html', {'material': obj})

@cargador_required
def reactivar_material_view(request, material_id):
    obj = get_object_or_404(Material, id=material_id)
    if request.method == 'POST': 
        obj.activo = True
        obj.save()
        registrar_auditoria(request, "Reactivar Material", f"Reactivado material: {obj.titulo}")
        return redirect('gestion_materiales')
    return redirect('gestion_materiales')

# --- AUTORES Y CATEGORIAS ---

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
            obj.activo = False
            obj.save()
            registrar_auditoria(request, "Archivar Autor", f"Archivado autor: {obj.nombre} {obj.apellido}")
        return redirect('gestion_autores')
    return redirect('gestion_autores')

@cargador_required
def reactivar_autor_view(request, autor_id):
    obj = get_object_or_404(Autor, id=autor_id)
    if request.method == 'POST': obj.activo = True; obj.save(); registrar_auditoria(request, "Reactivar Autor", f"Reactivado: {obj.nombre}"); return redirect('gestion_autores')
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
        if form.is_valid(): c = form.save(); registrar_auditoria(request, "Crear Categoría", f"Nueva: {c.nombre}"); messages.success(request, "Categoría creada."); return redirect('gestion_categorias')
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
    if request.method == 'POST': obj.activo = False; obj.save(); registrar_auditoria(request, "Archivar Categoría", f"Archivada: {obj.nombre}"); return redirect('gestion_categorias')
    return redirect('gestion_categorias')

@cargador_required
def reactivar_categoria_view(request, categoria_id):
    obj = get_object_or_404(Categoria, id=categoria_id)
    if request.method == 'POST': obj.activo = True; obj.save(); registrar_auditoria(request, "Reactivar Categoría", f"Reactivada: {obj.nombre}"); return redirect('gestion_categorias')
    return redirect('gestion_categorias')

# --- GESTIÓN AVANZADA ---

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
    # 1) Tomamos el texto de búsqueda
    q = request.GET.get('q', '').strip()

    # 2) Base de usuarios (sin superusuarios)
    qs = User.objects.filter(is_superuser=False).order_by('username')

    # 3) Filtrar si hay búsqueda
    if q:
        qs = qs.filter(
            Q(username__icontains=q) |
            Q(email__icontains=q) |
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q)
        )

    # 4) Paginación
    paginator = Paginator(qs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # 5) Armamos la estructura usuarios_con_roles igual que antes
    users = [
        {
            'user': u,
            'rol_actual': u.groups.first()
        }
        for u in page_obj
    ]

    context = {
        'usuarios_con_roles': users,
        'page_obj': page_obj,
        'roles_disponibles': Group.objects.all(),
        'search_query': q,   # 👈 para el template moderno
    }
    return render(request, 'biblioteca/gestion_usuarios.html', context)


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
            u.is_active = False; u.save(); registrar_auditoria(request, "Desactivar Usuario", f"Se desactivó al usuario '{u.username}'"); messages.success(request, "Desactivado.")
    return redirect('gestion_usuarios')

@admin_required
def admin_reactivar_usuario_view(request, user_id):
    u = get_object_or_404(User, id=user_id)
    if request.method == 'POST': u.is_active = True; u.save(); registrar_auditoria(request, "Reactivar Usuario", f"Se reactivó al usuario '{u.username}'"); messages.success(request, "Reactivado.")
    return redirect('gestion_usuarios')

@admin_required
def ejecutar_tareas_diarias_view(request):
    if request.method == 'POST':
        salida = StringIO()
        try:
            call_command('procesar_vencidos', stdout=salida); salida.write("\n")
            call_command('alerta_preventiva', stdout=salida); salida.write("\n")
            call_command('alerta_atrasos', stdout=salida)
            config_tareas, _ = ConfiguracionSistema.objects.get_or_create(clave="control_tareas_diarias")
            config_tareas.fecha = date.today(); config_tareas.save()
            txt = salida.getvalue()
            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            html_txt = ansi_escape.sub('', txt).replace("\n", "<br>")
            messages.success(request, mark_safe(f"<strong>✅ TAREAS COMPLETADAS:</strong><br>{html_txt}"))
        except Exception as e: messages.error(request, f"Error: {e}")
    return redirect('gestion')

# --- NOTICIAS ---
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

# --- REPORTES Y EXCEL (GRÁFICOS DINÁMICOS) ---
@admin_required
def reportes_view(request):
    hoy = date.today()
    activos = Prestamo.objects.filter(devuelto=False)
    vencidos = activos.filter(fecha_devolucion__lt=hoy).count()
    al_dia = activos.filter(fecha_devolucion__gte=hoy, renovado=False).count()
    renovados = activos.filter(fecha_devolucion__gte=hoy, renovado=True).count()

    # TOP 10 LIBROS (KPI Inventario Actualizado)
    top_libros = Prestamo.objects.filter(libro__isnull=False).values('libro__titulo') \
        .annotate(total=Count('id')).order_by('-total')[:10]
    
    if not top_libros: inv_labels = ['Sin datos']; inv_data = [1]
    else:
        inv_labels = [item['libro__titulo'] for item in top_libros]
        inv_data = [item['total'] for item in top_libros]

    top_categorias = Prestamo.objects.filter(libro__isnull=False).values('libro__categoria__nombre') \
        .annotate(total=Count('id')).order_by('-total')[:5]
    cat_labels = [item['libro__categoria__nombre'] for item in top_categorias]
    cat_data = [item['total'] for item in top_categorias]

    top_autores = Prestamo.objects.filter(libro__isnull=False).values('libro__autor__nombre', 'libro__autor__apellido') \
        .annotate(total=Count('id')).order_by('-total')[:5]
    aut_labels = [f"{item['libro__autor__nombre']} {item['libro__autor__apellido']}" for item in top_autores]
    aut_data = [item['total'] for item in top_autores]

    ctx = {
        'total_prestamos_activos': activos.count(),
        'total_usuarios': User.objects.count(),
        'total_libros': Libro.objects.filter(activo=True).count(),
        'total_materiales': Material.objects.filter(activo=True).count(),
        'total_vencidos': vencidos,
        'lista_vencidos': [{'prestamo': p, 'dias_atraso': (hoy-p.fecha_devolucion).days} for p in activos.filter(fecha_devolucion__lt=hoy)],
        'chart_estado_data': [al_dia, vencidos, renovados],
        'chart_inventario_labels': inv_labels, 'chart_inventario_data': inv_data,
        'chart_categorias_labels': cat_labels, 'chart_categorias_data': cat_data,
        'chart_autores_labels': aut_labels, 'chart_autores_data': aut_data,
    }
    return render(request, 'biblioteca/reportes.html', ctx)

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
    header_font = Font(bold=True, color="FFFFFF")
    fill_azul = PatternFill(start_color="2980b9", end_color="2980b9", fill_type="solid")
    fill_rojo = PatternFill(start_color="c0392b", end_color="c0392b", fill_type="solid")
    fill_verde = PatternFill(start_color="27ae60", end_color="27ae60", fill_type="solid")
    fill_turquesa = PatternFill(start_color="16a085", end_color="16a085", fill_type="solid")
    fill_morado = PatternFill(start_color="9b59b6", end_color="9b59b6", fill_type="solid")

    ws1 = wb.active; ws1.title = "Resumen Gerencial"
    ws1.append(["Indicador Clave", "Valor Actual", "Fecha Corte"])
    for cell in ws1[1]: cell.font = header_font; cell.fill = fill_azul
    ws1.append(["Préstamos Activos", Prestamo.objects.filter(devuelto=False).count(), hoy])
    ws1.append(["Usuarios Totales", User.objects.count(), hoy])
    ws1.column_dimensions['A'].width = 35

    ws2 = wb.create_sheet("Morosos"); ws2.append(["Usuario", "Email", "Ítem", "Días Atraso"])
    for cell in ws2[1]: cell.font = header_font; cell.fill = fill_rojo
    for p in Prestamo.objects.filter(devuelto=False, fecha_devolucion__lt=hoy):
        ws2.append([p.usuario.username, p.usuario.email, str(p.libro or p.material), (hoy - p.fecha_devolucion).days])
    ws2.column_dimensions['C'].width = 40

    ws3 = wb.create_sheet("Préstamos Activos"); ws3.append(["Usuario", "Ítem", "Fecha Dev."])
    for cell in ws3[1]: cell.font = header_font; cell.fill = fill_verde
    for p in Prestamo.objects.filter(devuelto=False):
        ws3.append([p.usuario.username, str(p.libro or p.material), p.fecha_devolucion])
    ws3.column_dimensions['B'].width = 40

    ws4 = wb.create_sheet("Inventario"); ws4.append(["Tipo", "Título", "Stock"])
    for cell in ws4[1]: cell.font = header_font; cell.fill = fill_turquesa
    for l in Libro.objects.filter(activo=True): ws4.append(["Libro", l.titulo, l.cantidad])
    for m in Material.objects.filter(activo=True): ws4.append(["Material", m.titulo, m.cantidad])
    ws4.column_dimensions['B'].width = 50

    # HOJA 5: RANKING LECTORES
    ws5 = wb.create_sheet("Top Lectores"); ws5.append(["Ranking", "Usuario", "Total Histórico"])
    for cell in ws5[1]: cell.font = header_font; cell.fill = fill_morado
    top_users = User.objects.annotate(total=Count('prestamo')).order_by('-total')[:50]
    for i, u in enumerate(top_users, 1): ws5.append([i, u.username, u.total])

    nombre_archivo = f"Reporte_SIGB_{hoy.strftime('%Y%m%d')}.xlsx"
    resp = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    resp['Content-Disposition'] = f'attachment; filename="{nombre_archivo}"'
    wb.save(resp)
    registrar_auditoria(request, "Exportar Excel", f"Reporte descargado por {request.user.username}")
    return resp