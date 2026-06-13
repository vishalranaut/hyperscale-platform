"""HyperScale Platform — User Service API URL Configuration."""

from django.urls import path

from services.user_service.api import views

urlpatterns = [
    # Auth endpoints
    path("auth/register", views.register, name="auth-register"),
    path("auth/login", views.login, name="auth-login"),
    path("auth/oauth/<str:provider>", views.oauth_login, name="auth-oauth"),
    path("auth/refresh", views.refresh_token, name="auth-refresh"),
    path("auth/logout", views.logout, name="auth-logout"),
    path("auth/verify-email", views.verify_email, name="auth-verify-email"),

    # User endpoints
    path("users/me", views.me, name="user-me"),
    path("users/me/permissions", views.user_permissions, name="user-permissions"),
    path("users/<str:user_id>", views.user_detail, name="user-detail"),
    path("users/<str:user_id>/roles", views.assign_role, name="user-assign-role"),
    path("users/", views.user_list, name="user-list"),
]
