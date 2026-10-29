from django.urls import path
from . import views

urlpatterns = [
    path("auth/register", views.RegisterView.as_view()),
    path("auth/login", views.LoginView.as_view()),
    path("auth/logout", views.LogoutView.as_view()),
    path("documents", views.DocumentListCreateView.as_view()),
    path("documents/<int:pk>", views.DocumentDetailView.as_view()),
]