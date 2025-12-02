
# Archivo: biblioteca/forms.py

from django import forms
from .models import Libro, Autor, Categoria, Perfil,Material
from .models import Noticia

class LibroForm(forms.ModelForm):
    autor = forms.ModelChoiceField(
        queryset=Autor.objects.filter(activo=True),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Autor"
    )
    categoria = forms.ModelChoiceField(
        queryset=Categoria.objects.filter(activo=True),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Categoría"
    )

    class Meta:
        model = Libro
        fields = ['titulo', 'isbn', 'autor', 'categoria', 'sinopsis', 'fecha_publicacion', 'cantidad']
        
        
        widgets = {
            'titulo': forms.TextInput(attrs={'class': 'form-control'}),
            'isbn': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 9780307474278'}),
            'sinopsis': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'fecha_publicacion': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}), 
            'cantidad': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}), 
        }
        
        
        labels = {
            'titulo': 'Título del Libro',
            'isbn': 'ISBN (13 dígitos)',
            'sinopsis': 'Sinopsis (Resumen)',
            'fecha_publicacion': 'Fecha de Publicación',
            'cantidad': 'Nº de Copias Totales', 
        }

class AutorForm(forms.ModelForm):
    
    class Meta:
        model = Autor
        fields = ['nombre', 'apellido', 'biografia']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'apellido': forms.TextInput(attrs={'class': 'form-control'}),
            'biografia': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }
        labels = {
            'nombre': 'Nombre del Autor',
            'apellido': 'Apellido del Autor',
            'biografia': 'Biografía (Opcional)',
        }

class CategoriaForm(forms.ModelForm):
    
    class Meta:
        model = Categoria
        fields = ['nombre']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Novela, Ensayo, Manual...'}),
        }
        labels = {
            'nombre': 'Nombre de la Categoría',
        }

class PerfilForm(forms.ModelForm):
    """
    Este formulario permite a los usuarios SELECCIONAR
    su avatar (foto de perfil) de una lista.
    """
    
    class Meta:
        model = Perfil  
        fields = ['avatar']
        
        #  Usamos un dropdown (Select)
        widgets = {
            'avatar': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'avatar': 'Selecciona tu Avatar',
        }

class MaterialForm(forms.ModelForm):
 #Crear y Editar Materiales (Manuales, Revistas, etc.).
    
    
    class Meta:
        model = Material  # se basa en el modelo 'Material'
        
        # (Basado en el Modelo_datos.docx) 
        fields = [
            'titulo', 
            'codigo', # Código de inventario (único)
            'tipo',   # Ej: Manual, Revista
            'formato', # Ej: Físico, PDF
            'autor',   # (Este es un CharField, no una FK, según el modelo)
            'ubicacion', # Ej: Estante A-42
            'descripcion', 
            'publicado',
            'cantidad'
        ]
        
        
        widgets = {
            'titulo': forms.TextInput(attrs={'class': 'form-control'}),
            'codigo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: DGAC-MAN-001'}),
            'tipo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Manual Aeronáutico'}),
            'formato': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Físico'}),
            'autor': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: DGAC / Airbus'}),
            'ubicacion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Estante A-42'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'publicado': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'cantidad': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
        }
labels = {
            'cantidad': 'Nº de Copias Totales',
        }

class NoticiaForm(forms.ModelForm):
    class Meta:
        model = Noticia
        fields = ['titulo', 'contenido', 'imagen']
        widgets = {
            'titulo': forms.TextInput(attrs={'class': 'form-control'}),
            'contenido': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'imagen': forms.FileInput(attrs={'class': 'form-control'}), # Input tipo archivo
        }