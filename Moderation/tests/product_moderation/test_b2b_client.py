import uuid
from json import loads

from django.test import override_settings

from app.product_moderation.api import B2BClient
from app.product_moderation.api import b2b_client as b2b_client_module
from app.product_moderation.models import ProductModeration


class FakeB2BResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None


@override_settings(B2B_URL="http://b2b.example", MOD_TO_B2B_KEY="secret")
def test_b2b_client_sends_moderated_event_contract(monkeypatch):
    requests = []

    def fake_urlopen(request, timeout):
        requests.append(request)
        return FakeB2BResponse()

    monkeypatch.setattr(b2b_client_module, "urlopen", fake_urlopen)

    product_id = str(uuid.uuid4())
    B2BClient().send_moderation_event(product_id, ProductModeration.Status.MODERATED)

    request = requests[0]
    payload = loads(request.data.decode("utf-8"))

    assert request.full_url == "http://b2b.example/api/v1/events/moderation"
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert request.get_header("X-service-key") == "secret"
    assert uuid.UUID(payload["idempotency_key"])
    assert payload["product_id"] == product_id
    assert payload["status"] == "MODERATED"


@override_settings(B2B_URL="http://b2b.example", MOD_TO_B2B_KEY="secret")
def test_b2b_client_sends_blocked_event_contract(monkeypatch):
    requests = []

    def fake_urlopen(request, timeout):
        requests.append(request)
        return FakeB2BResponse()

    monkeypatch.setattr(b2b_client_module, "urlopen", fake_urlopen)

    product_id = str(uuid.uuid4())
    reason_id = str(uuid.uuid4())
    B2BClient().send_moderation_event(
        product_id,
        ProductModeration.Status.BLOCKED,
        hard_block=False,
        blocking_reason={
            "id": reason_id,
            "title": "Описание не соответствует товару",
            "comment": "Описание и фото не соответствуют товару",
        },
        field_reports=[
            {
                "field_name": "description",
                "sku_id": None,
                "comment": "Текст описания скопирован с другого товара",
            }
        ],
    )

    request = requests[0]
    payload = loads(request.data.decode("utf-8"))

    assert request.full_url == "http://b2b.example/api/v1/events/moderation"
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert request.get_header("X-service-key") == "secret"
    assert payload == {
        "product_id": product_id,
        "status": "BLOCKED",
        "hard_block": False,
        "blocking_reason": {
            "id": reason_id,
            "title": "Описание не соответствует товару",
            "comment": "Описание и фото не соответствуют товару",
        },
        "field_reports": [
            {
                "field_name": "description",
                "sku_id": None,
                "comment": "Текст описания скопирован с другого товара",
            }
        ],
    }
