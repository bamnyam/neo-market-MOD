import logging
import uuid

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from app.product_moderation.api import (
    ApproveProductRequestSerializer,
    B2BClient,
    B2BClientError,
)
from app.product_moderation.models import ProductModeration

logger = logging.getLogger(__name__)


class ApproveProductView(APIView):
    b2b_client_class = B2BClient

    def post(self, request, product_id: uuid.UUID) -> Response:
        serializer = ApproveProductRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        moderator_id = self._get_moderator_id(request)
        if moderator_id is None:
            return Response(
                {"error": "Moderator id is required"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        moderation = self._get_moderation(product_id)
        if moderation is None:
            return Response(
                {"error": "Product not found in moderation queue"},
                status=status.HTTP_404_NOT_FOUND,
            )

        error_response = self._validate_moderation(moderation, moderator_id)
        if error_response is not None:
            return error_response

        client = self.b2b_client_class()

        try:
            product = client.get_product(str(product_id))
        except B2BClientError:
            logger.exception(
                "Cannot approve product %s: B2B product check failed", product_id
            )
            return Response(
                {"error": "Failed to check product in B2B"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if len(product.get("skus") or []) == 0:
            return Response(
                {"error": "Product has no SKUs, cannot approve"},
                status=status.HTTP_409_CONFLICT,
            )

        try:
            with transaction.atomic():
                moderation = ProductModeration.objects.select_for_update().get(
                    product_id=product_id
                )
                error_response = self._validate_moderation(moderation, moderator_id)
                if error_response is not None:
                    return error_response

                moderation.status = ProductModeration.Status.MODERATED
                moderation.date_moderation = timezone.now()
                moderation.moderator_comment = serializer.validated_data.get(
                    "moderator_comment"
                )
                moderation.blocking_reason = None
                moderation.save(
                    update_fields=[
                        "status",
                        "date_moderation",
                        "moderator_comment",
                        "blocking_reason",
                        "date_updated",
                    ]
                )
                moderation.field_reports.all().delete()
                client.send_moderation_event(
                    str(product_id),
                    ProductModeration.Status.MODERATED,
                )
        except B2BClientError:
            logger.exception("Cannot approve product %s: B2B event failed", product_id)
            return Response(
                {"error": "Failed to send moderation event to B2B"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "product_id": str(product_id),
                "status": ProductModeration.Status.MODERATED,
            },
            status=status.HTTP_200_OK,
        )

    def _get_moderator_id(self, request) -> uuid.UUID | None:
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            try:
                return uuid.UUID(str(user.pk))
            except (TypeError, ValueError):
                pass

        raw_moderator_id = request.headers.get("X-Moderator-Id")
        if raw_moderator_id is None:
            return None

        try:
            return uuid.UUID(raw_moderator_id)
        except ValueError:
            return None

    def _get_moderation(self, product_id: uuid.UUID) -> ProductModeration | None:
        try:
            return ProductModeration.objects.get(product_id=product_id)
        except ProductModeration.DoesNotExist:
            return None

    def _validate_moderation(
        self,
        moderation: ProductModeration,
        moderator_id: uuid.UUID,
    ) -> Response | None:
        if moderation.status == ProductModeration.Status.HARD_BLOCKED:
            return Response(
                {"error": "Product is permanently blocked"},
                status=status.HTTP_409_CONFLICT,
            )

        if moderation.status != ProductModeration.Status.IN_REVIEW:
            return Response(
                {"error": "Product is not in review status"},
                status=status.HTTP_409_CONFLICT,
            )

        if moderation.moderator_id != moderator_id:
            return Response(
                {"error": "This moderation card is not assigned to you"},
                status=status.HTTP_403_FORBIDDEN,
            )

        return None
