from rest_framework import status
from rest_framework.response import Response


def validate_service_key(request, expected_key: str) -> Response | None:
    if not expected_key or request.headers.get("X-Service-Key") != expected_key:
        return Response(
            {"code": "UNAUTHORIZED", "message": "Invalid service key"},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    return None
