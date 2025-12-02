#
# Archivo: biblioteca_project/urls.py
#
from django.contrib import admin
from django.urls import path, include

# Importamos la configuración (settings) y el helper (static)
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Ruta principal a nuestra app 'biblioteca'
    path('', include('biblioteca.urls')),
]

# ¡LÍNEA MÁS IMPORTANTE!
# Esto le dice a Django que sirva archivos (como CSS e imágenes)
# desde tu carpeta 'static/' cuando DEBUG=True.
if settings.DEBUG:
    # Usamos STATICFILES_DIRS[0] porque así lo definimos en settings.py
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])



urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('biblioteca.urls')),
]

# Esto permite servir las fotos subidas mientras estás en modo DEBUG (local)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)