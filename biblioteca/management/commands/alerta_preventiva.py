from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from biblioteca.models import Prestamo, Historial
from biblioteca.utils import enviar_correo_notificacion

class Command(BaseCommand):
    help = 'Envía correos preventivos 1 día antes del vencimiento'

    def handle(self, *args, **kwargs):
        hoy = timezone.now().date()
        manana = hoy + timedelta(days=1)
        
        por_vencer = Prestamo.objects.filter(devuelto=False, fecha_devolucion=manana)
        
        count = 0
        for p in por_vencer:
            titulo = p.libro.titulo if p.libro else p.material.titulo
            asunto = f"⏰ Recordatorio: Devolución Mañana - {titulo}"
            mensaje = (
                f"Hola {p.usuario.first_name},\n\n"
                f"Te recordamos que tu préstamo vence MAÑANA ({manana.strftime('%d-%m-%Y')}).\n"
                "Evita multas devolviendo a tiempo."
            )
            
            enviar_correo_notificacion(p.usuario.email, asunto, mensaje)
            
            # Auditoría individual (Aviso)
            Historial.objects.create(
                usuario=None,
                accion="Robot Alerta",
                detalle=f"Aviso preventivo enviado a: {p.usuario.email} | Ítem: {titulo}"
            )
            count += 1

        # --- HUELLA DE EJECUCIÓN (SI NO HUBO ACCIÓN) ---
        if count == 0:
            Historial.objects.create(
                usuario=None,
                accion="Robot Alerta",
                detalle="Ejecución correcta. No hay préstamos que venzan mañana."
            )
            self.stdout.write("ℹ️ Huella registrada: Sin vencimientos próximos.")
        else:
            self.stdout.write(self.style.SUCCESS(f'Fin: {count} alertas enviadas.'))