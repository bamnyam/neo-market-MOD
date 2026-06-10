from django.conf import settings
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

    def post(self, request) -> Response:
        service_key_error = validate_service_key(request, settings.B2B_TO_MOD_KEY)
        if service_key_error is not None:
            return service_key_error

        serializer = ProductEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            handle_product_event(
                event=serializer.validated_data["event"],
                product_id=serializer.validated_data["product_id"],
                seller_id=serializer.validated_data["seller_id"],
                b2b_client=self.b2b_client_class(),
            )
        except ModerationDecisionError as exc:
            return Response(
                {"code": exc.code, "message": exc.message},
                status=exc.status_code,
            )

        return Response(status=status.HTTP_200_OK)
