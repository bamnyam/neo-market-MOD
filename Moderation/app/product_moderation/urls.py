from django.urls import path

from app.product_moderation.views import ApproveProductView, DeclineProductView

urlpatterns = [
    path(
        "api/v1/products/<uuid:product_id>/approve",
        ApproveProductView.as_view(),
        name="approve-product",
    ),
    path(
        "api/v1/products/<uuid:product_id>/decline",
        DeclineProductView.as_view(),
        name="decline-product",
    ),
]
