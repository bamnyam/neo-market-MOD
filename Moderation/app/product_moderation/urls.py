from django.urls import path

from app.product_moderation.views import (
    ApproveProductView,
    DeclineProductView,
    ProductEventView,
)

urlpatterns = [
    path(
        "api/v1/tickets/<uuid:ticket_id>/approve",
        ApproveProductView.as_view(),
        name="approve-product",
    ),
    path(
        "api/v1/tickets/<uuid:ticket_id>/block",
        DeclineProductView.as_view(),
        name="block-ticket",
    ),
    path(
        "api/v1/events/product",
        ProductEventView.as_view(),
        name="product-event",
    ),
]
