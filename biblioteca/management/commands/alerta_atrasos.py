from django.core.management.base import BaseCommand
from django.utils import timezone
from biblioteca.models import Prestamo, Historial
from biblioteca.utils import enviar_correo_notificacion

class Command(BaseCommand):
    help = 'Envía correos de cobranza a usuarios con préstamos vencidos'

    def handle(self, *args, **kwargs):
        hoy = timezone.now().date()
        
        self.stdout.write("=== ROBOT DE COBRANZA (ATRASOS) ===")
        
        # Buscar préstamos que vencieron AYER o ANTES
        vencidos = Prestamo.objects.filter(devuelto=False, fecha_devolucion__lt=hoy)
        
        count = 0
        for p in vencidos:
            dias_atraso = (hoy - p.fecha_devolucion).days
            titulo = p.libro.titulo if p.libro else p.material.titulo
            
            # 1. Enviar correo
            asunto = f"🔴 URGENTE: Préstamo Vencido - {titulo}"
            mensaje = (
                f"Estimado/a {p.usuario.first_name},\n\n"
                f"Su préstamo del ítem '{titulo}' tiene {dias_atraso} días de atraso.\n"
                f"Fecha límite fue: {p.fecha_devolucion.strftime('%d-%m-%Y')}\n\n"
                f"Por favor regularizar su situación."
            )
            enviar_correo_notificacion(p.usuario.email, asunto, mensaje)
            
            # 2. Registro Auditoría
            Historial.objects.create(
                usuario=None, 
                accion="Robot Cobranza",
                detalle=f"Cobro enviado a: {p.usuario.email} | Atraso: {dias_atraso} días | Ítem: {titulo}"
            )
            
            self.stdout.write(f"-> Cobro enviado a: {p.usuario.email}")
            count += 1

        # --- HUELLA DE EJECUCIÓN ESTANDARIZADA ---
        if count == 0:
            Historial.objects.create(
                usuario=None,
                accion="Robot Cobranza",
                detalle="Ejecución correcta. No existen préstamos atrasados hoy."
            )
            # AQUI ESTÁ EL CAMBIO VISUAL:
            self.stdout.write("ℹ️ Huella registrada: Sin morosos pendientes.")
        else:
            self.stdout.write(self.style.SUCCESS(f'✅ Proceso finalizado. {count} avisos enviados.'))