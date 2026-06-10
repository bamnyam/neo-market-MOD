import uuid

from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from app.product_moderation.api import (
    ApproveProductRequestSerializer,
    B2BClient,
)
from app.product_moderation.services import (
    ModerationDecisionError,
    approve_product,
    get_moderator_id,
)
from app.product_moderation.views.auth import validate_service_key


class ApproveProductView(APIView):
    b2b_client_class = B2BClient

    def post(self, request, ticket_id: uuid.UUID) -> Response:
        service_key_error = validate_service_key(request, settings.MOD_SERVICE_KEY)
        if service_key_error is not None:
            return service_key_error

        serializer = ApproveProductRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        moderator_id = get_moderator_id(request)
        if moderator_id is None:
            return Response(
                {"code": "UNAUTHORIZED", "message": "Moderator id is required"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            result = approve_product(
                ticket_id=ticket_id,
                moderator_id=moderator_id,
                moderator_comment=serializer.validated_data.get("comment"),
                b2b_client=self.b2b_client_class(),
            )
        except ModerationDecisionError as exc:
            return Response(
                {"code": exc.code, "message": exc.message},
                status=exc.status_code,
            )

        return Response(result, status=status.HTTP_200_OK)
