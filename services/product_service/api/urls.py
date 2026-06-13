"""HyperScale Platform — Product Service API URL Configuration."""

from django.urls import path

from services.product_service.api import views

urlpatterns = [
    path("products", views.create_product, name="product-create"),
    path("products/", views.list_products, name="product-list"),
    path("products/<str:product_id>", views.product_detail, name="product-detail"),
    path("products/<str:product_id>/inventory", views.update_inventory, name="product-inventory"),
    path("categories/tree", views.category_tree, name="category-tree"),
    path("categories", views.create_category, name="category-create"),
]
