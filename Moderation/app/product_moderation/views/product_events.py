from django.conf import settings
from django.core.cache import cache
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from app.product_moderation.api import B2BClient, ProductEventSerializer
from app.product_moderation.services import (
    ModerationDecisionError,
    handle_product_event,
)
from app.product_moderation.views.auth import validate_service_key


class ProductEventView(APIView):
    b2b_client_class = B2BClient
    idempotency_ttl_seconds = 24 * 60 * 60

    def post(self, request) -> Response:
        service_key_error = validate_service_key(request, settings.B2B_TO_MOD_KEY)
        if service_key_error is not None:
            return service_key_error

        serializer = ProductEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event_data = serializer.validated_data
        idempotency_cache_key = (
            f"product_moderation:b2b_event:{event_data['idempotency_key']}"
        )
        if not cache.add(
            idempotency_cache_key,
            True,
            timeout=self.idempotency_ttl_seconds,
        ):
            return Response(
                {
                    "code": "IDEMPOTENCY_KEY_CONFLICT",
                    "message": "Idempotency key already processed",
                },
                status=status.HTTP_409_CONFLICT,
            )

        try:
            handle_product_event(
                event_type=event_data["event_type"],
                product_id=event_data["payload"]["product_id"],
                seller_id=event_data["payload"]["seller_id"],
                b2b_client=self.b2b_client_class(),
            )
        except ModerationDecisionError as exc:
            return Response(
                {"code": exc.code, "message": exc.message},
                status=exc.status_code,
            )

        return Response(status=status.HTTP_202_ACCEPTED)
