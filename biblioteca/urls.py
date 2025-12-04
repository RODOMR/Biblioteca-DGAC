#
# Archivo: biblioteca/urls.py
#
from django.urls import path
from . import views_auth
from . import views 
from django.contrib.auth import views as auth_views

urlpatterns = [
    # ... (Todas tus rutas de Módulos 1 a 7) ...
    path('', views_auth.home_view, name='home'),
    path('login/', views_auth.login_view, name='login'),
    path('register/', views_auth.register_view, name='register'),
    path('reset_password/', 
         auth_views.PasswordResetView.as_view(template_name="biblioteca/password/password_reset.html"), 
         name ='reset_password'),

    path('reset_password_sent/', 
        auth_views.PasswordResetDoneView.as_view(template_name="biblioteca/password/password_reset_sent.html"), 
        name ='password_reset_done'),

    path('reset/<uidb64>/<token>/', 
        auth_views.PasswordResetConfirmView.as_view(template_name="biblioteca/password/password_reset_form.html"), 
        name ='password_reset_confirm'),

    path('reset_password_complete/', 
        auth_views.PasswordResetCompleteView.as_view(template_name="biblioteca/password/password_reset_done.html"), 
        name ='password_reset_complete'),
    path('logout/', views_auth.logout_view, name='logout'),
    path('health/', views_auth.health_view, name='health'),
    path('catalogo/', views.lista_libros, name='catalogo'),
    path('prestar/<int:libro_id>/', views.prestar_libro_view, name='prestar_libro'),
    path('mis-prestamos/', views.mis_prestamos_view, name='mis_prestamos'),
    path('devolver/<int:prestamo_id>/', views.devolver_libro_view, name='devolver_libro'),
    path('renovar/<int:prestamo_id>/', views.renovar_prestamo_view, name='renovar_prestamo'),
    path('reportes/', views.reportes_view, name='reportes'),
    path('reportes/enviar-recordatorios/', views.enviar_recordatorios_view, name='enviar_recordatorios'),
    path('api/buscar-sugerencias/', views.buscar_sugerencias_view, name='buscar_sugerencias'),
    path('reservar/<int:libro_id>/', views.reservar_libro_view, name='reservar_libro'),
    path('reportes/', views.reportes_view, name='reportes'),
    path('reportes/exportar-excel/', views.exportar_reporte_excel_view, name='exportar_reporte_excel'),
    path('reportes/enviar-recordatorios/', views.enviar_recordatorios_view, name='enviar_recordatorios'),
    
    # (Gestión de Catálogo) ---
    path('gestion/', views.gestion_view, name='gestion'),
    path('gestion/crear-libro/', views.crear_libro_view, name='crear_libro'),
    path('gestion/libros/', views.gestion_libros_view, name='gestion_libros'),
    path('gestion/editar-libro/<int:libro_id>/', views.editar_libro_view, name='editar_libro'),
    path('gestion/eliminar-libro/<int:libro_id>/', views.eliminar_libro_view, name='eliminar_libro'),
    path('catalogo/', views.lista_libros, name='catalogo'),
    path('libro/<int:libro_id>/', views.detalle_libro_view, name='detalle_libro'), 
    path('api/buscar-sugerencias/', views.buscar_sugerencias_view, name='buscar_sugerencias'),
    path('catalogo/', views.lista_libros, name='catalogo'),
    path('libro/<int:libro_id>/', views.detalle_libro_view, name='detalle_libro'),
    path('material/<int:material_id>/', views.detalle_material_view, name='detalle_material'), 
    path('api/buscar-sugerencias/', views.buscar_sugerencias_view, name='buscar_sugerencias'),

    # (Gestión de Autores)
    path('gestion/autores/', views.gestion_autores_view, name='gestion_autores'),
    path('gestion/crear-autor/', views.crear_autor_view, name='crear_autor'),
    path('gestion/editar-autor/<int:autor_id>/', views.editar_autor_view, name='editar_autor'),
    path('gestion/categorias/', views.gestion_categorias_view, name='gestion_categorias'),
    path('gestion/crear-categoria/', views.crear_categoria_view, name='crear_categoria'),
    path('gestion/editar-categoria/<int:categoria_id>/', views.editar_categoria_view, name='editar_categoria'),
    #(Archivar Autor) ---
    path('gestion/eliminar-autor/<int:autor_id>/', views.eliminar_autor_view, name='eliminar_autor'),
    path('gestion/reactivar-autor/<int:autor_id>/', views.reactivar_autor_view, name='reactivar_autor'),
    #11.C (Archivar Categoría) 
    path('gestion/eliminar-categoria/<int:categoria_id>/', views.eliminar_categoria_view, name='eliminar_categoria'),
    path('gestion/reactivar-categoria/<int:categoria_id>/', views.reactivar_categoria_view, name='reactivar_categoria'),

    # Historial de Usuario
    path('historial/', views.historial_prestamos_view, name='historial_prestamos'),

    #Módulo 11 (Reactivar) 
    path('gestion/reactivar-libro/<int:libro_id>/', views.reactivar_libro_view, name='reactivar_libro'),
    # Módulo 13 (Favoritos)
    path('favoritos/', views.mis_favoritos_view, name='mis_favoritos'),
    path('favoritos/agregar/<int:item_id>/', views.agregar_favorito_view, name='agregar_favorito'),
    #Perfil
    path('perfil/', views.perfil_view, name='perfil'),
    #Gestión de Materiales)
    path('gestion/materiales/', views.gestion_materiales_view, name='gestion_materiales'),
    path('gestion/crear-material/', views.crear_material_view, name='crear_material'),
    path('gestion/editar-material/<int:material_id>/', views.editar_material_view, name='editar_material'),
    path('gestion/eliminar-material/<int:material_id>/', views.eliminar_material_view, name='eliminar_material'),
    path('gestion/reactivar-material/<int:material_id>/', views.reactivar_material_view, name='reactivar_material'),
    path('prestar/material/<int:material_id>/', views.prestar_material_view, name='prestar_material'),
    path('reservar/material/<int:material_id>/', views.reservar_material_view, name='reservar_material'),
    #gestion audioria
    path('gestion/historial/', views.gestion_historial_view, name='gestion_historial'),
    # --- Módulo 17: Gestión de Usuarios (Admin) ---
    path('gestion/usuarios/', views.gestion_usuarios_view, name='gestion_usuarios'),
    path('gestion/usuarios/cambiar-rol/<int:user_id>/', views.admin_cambiar_rol_view, name='admin_cambiar_rol'),
    path('gestion/usuarios/desactivar/<int:user_id>/', views.admin_desactivar_usuario_view, name='admin_desactivar_usuario'),
    path('gestion/usuarios/reactivar/<int:user_id>/', views.admin_reactivar_usuario_view, name='admin_reactivar_usuario'),

    # --- Módulo 16: Auditoría ---
    path('gestion/historial/', views.gestion_historial_view, name='gestion_historial'),
    path('gestion/historial/exportar/', views.exportar_historial_view, name='exportar_historial'),
    
    # Rutas de Noticias
    path('noticias/', views.lista_noticias_view, name='lista_noticias'),
    path('gestion/crear-noticia/', views.crear_noticia_view, name='crear_noticia'),
    path('gestion/eliminar-noticia/<int:noticia_id>/', views.eliminar_noticia_view, name='eliminar_noticia'),
    path('noticias/<int:noticia_id>/', views.detalle_noticia_view, name='detalle_noticia'),
    path('gestion/procesar-retiro/', views.procesar_retiro_view, name='procesar_retiro'),
    path('gestion/tareas-diarias/', views.ejecutar_tareas_diarias_view, name='ejecutar_tareas_diarias'),
    path('gestion/devoluciones/', views.procesar_devolucion_view, name='procesar_devolucion'),
]   
    