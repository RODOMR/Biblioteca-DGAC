#
# Archivo: biblioteca/admin.py
#
from django.contrib import admin

# 1. Importamos TODOS los modelos (incluyendo el nuevo 'Reserva')
from .models import Categoria, Autor, Libro, Prestamo, Reserva, Favorito

# --- Registros Avanzados (Módulo 2) ---

@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('nombre',)

@admin.register(Autor)
class AutorAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'apellido')

@admin.register(Libro)
class LibroAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'autor', 'categoria', 'isbn')
    list_filter = ('categoria', 'autor')
    search_fields = ('titulo', 'isbn')


 
# Registramos los modelos de "Circulación"
admin.site.register(Prestamo)
admin.site.register(Reserva) 
admin.site.register(Favorito)