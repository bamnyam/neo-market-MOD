from django.urls import path

from app.product_moderation.views import ApproveProductView

urlpatterns = [
    path(
        "api/v1/tickets/<uuid:ticket_id>/approve",
        ApproveProductView.as_view(),
        name="approve-product",
    ),
]
