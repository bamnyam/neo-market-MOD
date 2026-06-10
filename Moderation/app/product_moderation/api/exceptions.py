from rest_framework.views import exception_handler


def contract_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None

    detail = response.data
    if isinstance(detail, dict) and "code" in detail and "message" in detail:
        return response

    response.data = {
        "code": getattr(exc, "default_code", "ERROR").upper(),
        "message": _detail_to_message(detail),
    }
    return response


def _detail_to_message(detail) -> str:
    if isinstance(detail, dict):
        messages = []
        for field, value in detail.items():
            messages.append(f"{field}: {_detail_to_message(value)}")
        return "; ".join(messages)
    if isinstance(detail, list):
        return "; ".join(_detail_to_message(item) for item in detail)
    return str(detail)
