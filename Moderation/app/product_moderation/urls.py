from django.urls import path

from app.product_moderation.views import ApproveProductView

urlpatterns = [
    path(
        "api/v1/products/<uuid:product_id>/approve",
        ApproveProductView.as_view(),
        name="approve-product",
    ),
]
