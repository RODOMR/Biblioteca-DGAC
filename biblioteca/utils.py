import random
import string
import holidays # <--- IMPORTAR LIBRERÍA NUEVA
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

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

def calcular_fecha_habiles(dias=2):
    """
    Calcula la fecha sumando días hábiles.
    Salta Sábados, Domingos Y FERIADOS DE CHILE.
    """
    fecha = timezone.now().date()
    
    # Cargamos los feriados de Chile para el año actual y el próximo
    # (automáticamente sabe cuándo es Semana Santa, Fiestas Patrias, etc.)
    feriados_chile = holidays.CL() 
    
    contador = 0
    while contador < dias:
        fecha += timedelta(days=1)
        
        # REGLAS DE NEGOCIO:
        # 1. No es Sábado (5) ni Domingo (6)
        # 2. La fecha NO está en la lista de feriados de Chile
        if fecha.weekday() < 5 and fecha not in feriados_chile:
            contador += 1
            
    return fecha

def asignar_siguiente_reserva(libro=None, material=None):
    """
    Revisa si hay reservas en cola (PENDIENTE) y asigna el recurso liberado.
    """
    from .models import Reserva # Importación local
    
    filters = {'libro': libro, 'material': None} if libro else {'libro': None, 'material': material}
    
    siguiente = Reserva.objects.filter(**filters, estado='PENDIENTE').order_by('fecha_reserva').first()
    
    if siguiente:
        siguiente.estado = 'PENDIENTE_RETIRO'
        # USAMOS LA NUEVA LÓGICA DE DÍAS HÁBILES CHILENOS
        siguiente.fecha_limite_retiro = calcular_fecha_habiles(2)
        
        if not siguiente.codigo_retiro:
            siguiente.codigo_retiro = generar_codigo_retiro()
            
        siguiente.save()
        
        msg = f"¡Tu turno ha llegado! El ítem que reservaste ya está disponible.\n" \
              f"CÓDIGO DE RETIRO: {siguiente.codigo_retiro}\n" \
              f"Tienes hasta el {siguiente.fecha_limite_retiro} para retirarlo (Días hábiles)."
        
        enviar_correo_notificacion(siguiente.usuario.email, "¡Tu reserva está lista!", msg)
        return True
        
    return False