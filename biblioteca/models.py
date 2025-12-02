from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db.models import Q, CheckConstraint
from django.core.validators import MinValueValidator
from django.utils import timezone
from datetime import timedelta
from .utils import generar_codigo_retiro

# ==========================================
# 1. MODELOS CATALOGRÁFICOS (Inventario)
# ==========================================

class Categoria(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return self.nombre

class Autor(models.Model):
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    biografia = models.TextField(blank=True, null=True)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.nombre} {self.apellido}"

class Libro(models.Model):
    titulo = models.CharField(max_length=200)
    isbn = models.CharField(max_length=13, unique=True)
    autor = models.ForeignKey(Autor, on_delete=models.PROTECT)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT)
    sinopsis = models.TextField(blank=True, null=True)
    fecha_publicacion = models.DateField(blank=True, null=True)
    activo = models.BooleanField(default=True)
    cantidad = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])

    def __str__(self):
        return self.titulo

class Material(models.Model):
    titulo = models.CharField(max_length=200)
    autor = models.CharField(max_length=100, blank=True)
    descripcion = models.TextField(blank=True, null=True)
    publicado = models.DateField(blank=True, null=True)
    tipo = models.CharField(max_length=100, default="Documento")
    ubicacion = models.CharField(max_length=100, blank=True)
    formato = models.CharField(max_length=50, default="Físico")
    codigo = models.CharField(max_length=50, unique=True)
    activo = models.BooleanField(default=True)
    cantidad = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])

    def __str__(self):
        return self.titulo

# ==========================================
# 2. MODELOS DE CIRCULACIÓN (Préstamos y Reservas)
# ==========================================

class Prestamo(models.Model):
    libro = models.ForeignKey(Libro, on_delete=models.CASCADE, null=True, blank=True)
    material = models.ForeignKey(Material, on_delete=models.CASCADE, null=True, blank=True)
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    fecha_prestamo = models.DateField(auto_now_add=True)
    fecha_devolucion = models.DateField()
    devuelto = models.BooleanField(default=False)
    renovado = models.BooleanField(default=False)
    fecha_devolucion_real = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            CheckConstraint(
                check=(Q(libro__isnull=False) & Q(material__isnull=True)) | 
                      (Q(libro__isnull=True) & Q(material__isnull=False)),
                name='prestamo_libro_o_material'
            )
        ]

    def __str__(self):
        item = self.libro.titulo if self.libro else self.material.titulo
        estado = "Devuelto" if self.devuelto else "Activo"
        return f"{self.usuario.username} : {item} ({estado})"

class Reserva(models.Model):
    libro = models.ForeignKey(Libro, on_delete=models.CASCADE, null=True, blank=True)
    material = models.ForeignKey(Material, on_delete=models.CASCADE, null=True, blank=True)
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    fecha_reserva = models.DateTimeField(auto_now_add=True)
    
    # CAMPOS PARA "CLICK & COLLECT"
    codigo_retiro = models.CharField(max_length=6, unique=True, blank=True)
    fecha_limite_retiro = models.DateField(null=True, blank=True)
    
    estado = models.CharField(max_length=20, default='PENDIENTE', choices=[
        ('PENDIENTE', 'En Lista de Espera'),
        ('PENDIENTE_RETIRO', 'Listo para Retiro'),
        ('COMPLETADA', 'Entregado (Prestamo)'),
        ('CANCELADA', 'Cancelada / No Retirado')
    ])

    def __str__(self):
        item = self.libro.titulo if self.libro else self.material.titulo
        return f"Reserva [{self.codigo_retiro}] - {self.usuario.username}: {item}"

    def save(self, *args, **kwargs):
        # 1. Generar código SIEMPRE si no tiene uno
        if not self.codigo_retiro:
            while True:
                nuevo_codigo = generar_codigo_retiro()
                if not Reserva.objects.filter(codigo_retiro=nuevo_codigo).exists():
                    self.codigo_retiro = nuevo_codigo
                    break
            
        # 2. Calcular Fecha Límite (Solo si pasa a retiro y no tiene fecha)
        if self.estado == 'PENDIENTE_RETIRO' and not self.fecha_limite_retiro:
            self.fecha_limite_retiro = timezone.now().date() + timedelta(days=2)
                
        super().save(*args, **kwargs)

# ==========================================
# 3. OTROS MÓDULOS (Noticias, Usuario, Sistema)
# ==========================================

class Noticia(models.Model):
    titulo = models.CharField(max_length=200)
    contenido = models.TextField()
    imagen = models.ImageField(upload_to='noticias/', blank=True, null=True)
    fecha = models.DateTimeField(auto_now_add=True)
    autor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return self.titulo

    class Meta:
        ordering = ['-fecha']

class Favorito(models.Model):
    libro = models.ForeignKey(Libro, on_delete=models.CASCADE, null=True, blank=True)
    material = models.ForeignKey(Material, on_delete=models.CASCADE, null=True, blank=True)
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        item = self.libro.titulo if self.libro else self.material.titulo
        return f"Favorito de {self.usuario.username}: {item}"

AVATAR_CHOICES = [
    ('avatares/default.png', 'Por Defecto'),
    ('avatares/capitan.png', 'Capitán'),
    ('avatares/capitana.png', 'Capitana'),
    ('avatares/investigador.png', 'Investigador'),
    ('avatares/investigadora.png', 'Investigadora'),
    ('avatares/hombre_blanco.png', 'Lector (HB)'),
    ('avatares/mujer_blanca.png', 'Lectora (MB)'),
    ('avatares/hombre_negro.png', 'Lector (HN)'),
    ('avatares/mujer_negra.png', 'Lectora (MN)'),
]

class Perfil(models.Model):
    usuario = models.OneToOneField(User, on_delete=models.CASCADE)
    avatar = models.CharField(max_length=100, choices=AVATAR_CHOICES, default='avatares/default.png')

    def __str__(self):
        return f"Perfil de {self.usuario.username}"

@receiver(post_save, sender=User)
def crear_perfil(sender, instance, created, **kwargs):
    if created:
        Perfil.objects.create(usuario=instance)

class Historial(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    accion = models.CharField(max_length=50)
    detalle = models.CharField(max_length=255)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha']

    def __str__(self):
        return f"{self.fecha} - {self.accion}"

class ConfiguracionSistema(models.Model):
    clave = models.CharField(max_length=50, primary_key=True)
    fecha = models.DateField(null=True, blank=True)

    @staticmethod
    def obtener_instancia():
        obj, _ = ConfiguracionSistema.objects.get_or_create(clave="ultimo_respaldo_audit")
        return obj