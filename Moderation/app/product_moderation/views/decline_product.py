import uuid

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from app.product_moderation.api import (
    B2BClient,
    DeclineProductRequestSerializer,
)
from app.product_moderation.services import (
    ModerationDecisionError,
    decline_product,
    get_moderator_id,
)


class DeclineProductView(APIView):
    b2b_client_class = B2BClient

    def post(self, request, product_id: uuid.UUID) -> Response:
        serializer = DeclineProductRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        moderator_id = get_moderator_id(request)
        if moderator_id is None:
            return Response(
                {"error": "Moderator id is required"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            result = decline_product(
                product_id=product_id,
                moderator_id=moderator_id,
                blocking_reason_id=serializer.validated_data["blocking_reason_id"],
                moderator_comment=serializer.validated_data["moderator_comment"],
                field_reports=serializer.validated_data["field_reports"],
                b2b_client=self.b2b_client_class(),
            )
        except ModerationDecisionError as exc:
            return Response({"error": exc.message}, status=exc.status_code)

        return Response(result, status=status.HTTP_200_OK)
