from django.urls import path
from django.http import HttpResponse
from ...biblioteca.views_auth import home_view, login_view, logout_view, register_view

def health(_request):
    return HttpResponse("SIGB OK — localhost")

urlpatterns = [
    # públicas
    path("", home_view, name="home"),
    path("health/", health, name="health"),

    # auth HTML
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("register/", register_view, name="register"),
]
