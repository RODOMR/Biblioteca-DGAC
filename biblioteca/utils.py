import random
import string
import holidays 
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from datetime import timedelta, date

def generar_codigo_retiro():
    """Genera un código alfanumérico aleatorio de 6 caracteres."""
    caracteres = string.ascii_uppercase + string.digits
    return ''.join(random.choice(caracteres) for _ in range(6))

def enviar_correo_notificacion(destinatario, asunto, mensaje):
    """Envío seguro de correos."""
    if destinatario:
        try:
            send_mail(
                subject=f"[Biblioteca DGAC] {asunto}",
                message=f"Estimado usuario,\n\n{mensaje}\n\nAtte,\nEquipo de Biblioteca",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[destinatario],
                fail_silently=True
            )
        except Exception as e:
            print(f"Error enviando correo: {e}")

def calcular_fecha_habil(fecha_inicio, dias_a_sumar):
    """
    Calcula una fecha futura sumando días hábiles a una fecha de inicio dada.
    Salta Sábados (5), Domingos (6) y FERIADOS DE CHILE.
    """
    # Aseguramos que fecha_inicio sea un objeto date (si viene datetime, lo convertimos)
    if isinstance(fecha_inicio, type(timezone.now())):
        fecha_actual = fecha_inicio.date()
    else:
        fecha_actual = fecha_inicio

    # Cargamos los feriados de Chile dinámicamente
    feriados_chile = holidays.CL() 
    
    dias_agregados = 0
    
    while dias_agregados < dias_a_sumar:
        # Avanzamos un día
        fecha_actual += timedelta(days=1)
        
        # REGLAS DE NEGOCIO:
        # 1. Si es Sábado (5) o Domingo (6) -> saltar
        # 2. Si está en feriados_chile -> saltar
        if fecha_actual.weekday() >= 5 or fecha_actual in feriados_chile:
            continue
        
        # Si es día hábil, sumamos al contador
        dias_agregados += 1
            
    return fecha_actual

def asignar_siguiente_reserva(libro=None, material=None):
    """
    Revisa si hay reservas en cola (PENDIENTE) y asigna el recurso liberado.
    """
    from .models import Reserva # Importación local para evitar referencia circular
    
    filters = {'libro': libro, 'material': None} if libro else {'libro': None, 'material': material}
    
    siguiente = Reserva.objects.filter(**filters, estado='PENDIENTE').order_by('fecha_reserva').first()
    
    if siguiente:
        siguiente.estado = 'PENDIENTE_RETIRO'
        
        # AQUI USAMOS LA NUEVA LÓGICA:
        # Fecha inicio: Hoy. Días a sumar: 2 días hábiles para retirar.
        siguiente.fecha_limite_retiro = calcular_fecha_habil(timezone.now().date(), 2)
        
        if not siguiente.codigo_retiro:
            siguiente.codigo_retiro = generar_codigo_retiro()
            
        siguiente.save()
        
        msg = f"¡Tu turno ha llegado! El ítem que reservaste ya está disponible.\n" \
              f"CÓDIGO DE RETIRO: {siguiente.codigo_retiro}\n" \
              f"Tienes hasta el {siguiente.fecha_limite_retiro} para retirarlo (Días hábiles)."
        
        enviar_correo_notificacion(siguiente.usuario.email, "¡Tu reserva está lista!", msg)
        return True
        
    return False