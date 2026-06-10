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

    def post(self, request, ticket_id: uuid.UUID) -> Response:
        serializer = ApproveProductRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        moderator_id = self._get_moderator_id(request)
        if moderator_id is None:
            return self._error(
                "UNAUTHORIZED",
                "Moderator id is required",
                status.HTTP_401_UNAUTHORIZED,
            )

        moderation = self._get_moderation(ticket_id)
        if moderation is None:
            return self._error(
                "TICKET_NOT_FOUND",
                "Ticket not found",
                status.HTTP_404_NOT_FOUND,
            )

        error_response = self._validate_moderation(moderation, moderator_id)
        if error_response is not None:
            return error_response

        client = self.b2b_client_class()

        try:
            product = client.get_product(str(moderation.product_id))
        except B2BClientError:
            logger.exception(
                "Cannot approve ticket %s: B2B product check failed", ticket_id
            )
            return self._error(
                "B2B_PRODUCT_CHECK_FAILED",
                "Failed to check product in B2B",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if len(product.get("skus") or []) == 0:
            return self._error(
                "PRODUCT_HAS_NO_SKUS",
                "Product has no SKUs, cannot approve",
                status.HTTP_409_CONFLICT,
            )

        try:
            with transaction.atomic():
                moderation = ProductModeration.objects.select_for_update().get(
                    id=ticket_id
                )
                error_response = self._validate_moderation(moderation, moderator_id)
                if error_response is not None:
                    return error_response

                moderation.status = ProductModeration.Status.APPROVED
                moderation.date_moderation = timezone.now()
                moderation.moderator_comment = serializer.validated_data.get("comment")
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
                    str(moderation.product_id),
                    "MODERATED",
                )
        except B2BClientError:
            logger.exception("Cannot approve ticket %s: B2B event failed", ticket_id)
            return self._error(
                "B2B_EVENT_FAILED",
                "Failed to send moderation event to B2B",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(self._ticket_response(moderation), status=status.HTTP_200_OK)

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

    def _get_moderation(self, ticket_id: uuid.UUID) -> ProductModeration | None:
        try:
            return ProductModeration.objects.get(id=ticket_id)
        except ProductModeration.DoesNotExist:
            return None

    def _validate_moderation(
        self,
        moderation: ProductModeration,
        moderator_id: uuid.UUID,
    ) -> Response | None:
        if moderation.status == ProductModeration.Status.HARD_BLOCKED:
            return self._error(
                "TICKET_PERMANENTLY_BLOCKED",
                "Product is permanently blocked",
                status.HTTP_409_CONFLICT,
            )

        if moderation.status != ProductModeration.Status.IN_REVIEW:
            return self._error(
                "TICKET_WRONG_STATUS",
                "Ticket is not in review status",
                status.HTTP_409_CONFLICT,
            )

        if moderation.moderator_id != moderator_id:
            return self._error(
                "TICKET_NOT_ASSIGNED_TO_YOU",
                "This ticket is not assigned to you",
                status.HTTP_409_CONFLICT,
            )

        return None

    def _ticket_response(self, moderation: ProductModeration) -> dict:
        return {
            "id": str(moderation.id),
            "product_id": str(moderation.product_id),
            "seller_id": str(moderation.seller_id),
            "kind": "CREATE" if moderation.json_before is None else "EDIT",
            "status": moderation.status,
            "queue_priority": moderation.queue_priority,
            "assigned_moderator_id": (
                str(moderation.moderator_id) if moderation.moderator_id else None
            ),
            "claimed_at": None,
            "claim_expires_at": None,
            "decision_at": (
                moderation.date_moderation.isoformat()
                if moderation.date_moderation
                else None
            ),
            "created_at": moderation.date_created.isoformat(),
            "updated_at": moderation.date_updated.isoformat(),
        }

    def _error(self, code: str, message: str, response_status: int) -> Response:
        return Response(
            {"code": code, "message": message},
            status=response_status,
        )
