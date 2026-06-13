"""HyperScale Platform — Order Service API URLs."""

from django.urls import path
from services.order_service.api import views

urlpatterns = [
    path("cart", views.get_cart, name="cart-get"),
    path("cart/items", views.add_cart_item, name="cart-add-item"),
    path("cart/items/<str:product_id>", views.remove_cart_item, name="cart-remove-item"),
    path("orders", views.place_order, name="order-create"),
    path("orders/", views.list_orders, name="order-list"),
    path("orders/<str:order_id>", views.get_order, name="order-detail"),
    path("orders/<str:order_id>/cancel", views.cancel_order, name="order-cancel"),
    path("orders/<str:order_id>/refund", views.refund_order, name="order-refund"),
]
