from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from biblioteca.models import Reserva, Historial
from biblioteca.utils import enviar_correo_notificacion, asignar_siguiente_reserva

class Command(BaseCommand):
    help = 'Cancela reservas no retiradas. Si es pasadas las 18:00, incluye las de hoy.'

    def handle(self, *args, **kwargs):
        ahora = timezone.now()
        hoy = ahora.date()
        hora_actual = ahora.hour
        HORA_CIERRE = 18 

        self.stdout.write(f"=== ROBOT DE MANTENIMIENTO ===")
        
        # Lógica de hora
        if hora_actual >= HORA_CIERRE:
            criterio_fecha = {'fecha_limite_retiro__lte': hoy}
        else:
            criterio_fecha = {'fecha_limite_retiro__lt': hoy}

        vencidas = Reserva.objects.filter(estado='PENDIENTE_RETIRO', **criterio_fecha)
        
        count_cancel = 0
        for res in vencidas:
            res.estado = 'CANCELADA'
            res.save()
            
            # Auditoría individual (Cancelación)
            item_titulo = res.libro.titulo if res.libro else res.material.titulo
            Historial.objects.create(
                usuario=None, # Sistema
                accion="Cancelación Auto",
                detalle=f"Reserva de '{item_titulo}' cancelada por no retiro (Usuario: {res.usuario.username})."
            )
            
            msg_cancel = f"Tu reserva de '{item_titulo}' ha sido CANCELADA por no retiro."
            enviar_correo_notificacion(res.usuario.email, "Reserva Cancelada", msg_cancel)
            
            asignar_siguiente_reserva(libro=res.libro, material=res.material)
            count_cancel += 1

        # Limpieza mensual
        fecha_corte = hoy - timedelta(days=30)
        Reserva.objects.filter(estado='CANCELADA', fecha_limite_retiro__lt=fecha_corte).delete()
        
        # --- HUELLA DE EJECUCIÓN (SI NO HUBO ACCIÓN) ---
        if count_cancel == 0:
            Historial.objects.create(
                usuario=None,
                accion="Robot Limpieza",
                detalle="Ejecución correcta. No se encontraron reservas vencidas para cancelar."
            )
            self.stdout.write("ℹ️ Huella registrada: Sin novedades.")
        else:
            self.stdout.write(self.style.SUCCESS(f'Proceso terminado. {count_cancel} reservas canceladas.'))