import uuid
from json import loads

from django.test import override_settings

from app.product_moderation.api import B2BClient
from app.product_moderation.api import b2b_client as b2b_client_module


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
    B2BClient().send_moderation_event(product_id, "MODERATED")

    request = requests[0]
    payload = loads(request.data.decode("utf-8"))

    assert request.full_url == "http://b2b.example/api/v1/moderation/events"
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert request.get_header("X-service-key") == "secret"
    assert payload["event_type"] == "MODERATED"
    assert uuid.UUID(payload["idempotency_key"])
    assert payload["occurred_at"]
    assert payload["product_id"] == product_id


@override_settings(B2B_URL="http://b2b.example", MOD_TO_B2B_KEY="secret")
def test_b2b_client_sends_blocked_event_contract(monkeypatch):
    requests = []

    def fake_urlopen(request, timeout):
        requests.append(request)
        return FakeB2BResponse()

    monkeypatch.setattr(b2b_client_module, "urlopen", fake_urlopen)

    product_id = str(uuid.uuid4())
    B2BClient().send_moderation_event(product_id, "BLOCKED")

    request = requests[0]
    payload = loads(request.data.decode("utf-8"))

    assert request.full_url == "http://b2b.example/api/v1/moderation/events"
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert request.get_header("X-service-key") == "secret"
    assert payload["event_type"] == "BLOCKED"
    assert uuid.UUID(payload["idempotency_key"])
    assert payload["occurred_at"]
    assert payload["product_id"] == product_id
    assert set(payload) == {
        "event_type",
        "idempotency_key",
        "occurred_at",
        "product_id",
    }
