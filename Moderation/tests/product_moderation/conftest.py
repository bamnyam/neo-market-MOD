import uuid

import pytest
from rest_framework.test import APIClient

from app.product_moderation.api import B2BClientError
from app.product_moderation.models import ProductBlockingReason, ProductModeration
from app.product_moderation.views import (
    ApproveProductView,
    DeclineProductView,
    ProductEventView,
)


class SuccessfulApproveB2BClient:
    def get_product(self, product_id: str) -> dict:
        return {"id": product_id, "skus": [{"id": str(uuid.uuid4())}]}

    def send_moderation_event(self, product_id: str, event_type: str) -> None:
        return None


class NoSkuB2BClient(SuccessfulApproveB2BClient):
    def get_product(self, product_id: str) -> dict:
        return {"id": product_id, "skus": []}


class EventErrorApproveB2BClient(SuccessfulApproveB2BClient):
    def send_moderation_event(self, product_id: str, event_type: str) -> None:
        raise B2BClientError("event failed")


class SuccessfulDeclineB2BClient:
    events = []

    def send_moderation_event(self, product_id: str, event_type: str) -> None:
        self.events.append(
            {
                "product_id": product_id,
                "event_type": event_type,
            }
        )


class EventErrorDeclineB2BClient(SuccessfulDeclineB2BClient):
    def send_moderation_event(self, product_id: str, event_type: str) -> None:
        raise B2BClientError("event failed")


@pytest.fixture(autouse=True)
def reset_b2b_client_classes():
    ApproveProductView.b2b_client_class = SuccessfulApproveB2BClient
    SuccessfulDeclineB2BClient.events = []
    DeclineProductView.b2b_client_class = SuccessfulDeclineB2BClient
    ProductEventView.b2b_client_class = SuccessfulApproveB2BClient
    yield
    ApproveProductView.b2b_client_class = SuccessfulApproveB2BClient
    SuccessfulDeclineB2BClient.events = []
    DeclineProductView.b2b_client_class = SuccessfulDeclineB2BClient
    ProductEventView.b2b_client_class = SuccessfulApproveB2BClient


@pytest.fixture
def api_client(settings):
    settings.MOD_SERVICE_KEY = "mod-service-key"
    client = APIClient()
    client.credentials(HTTP_X_SERVICE_KEY="mod-service-key")
    return client


@pytest.fixture
def create_moderation():
    def factory(**kwargs) -> ProductModeration:
        defaults = {
            "product_id": uuid.uuid4(),
            "seller_id": uuid.uuid4(),
            "status": ProductModeration.Status.IN_REVIEW,
            "queue_priority": ProductModeration.QueuePriority.NEW_PRODUCTS,
            "json_after": {"title": "Product"},
            "moderator_id": uuid.uuid4(),
        }
        defaults.update(kwargs)
        return ProductModeration.objects.create(**defaults)

    return factory


@pytest.fixture
def create_blocking_reason():
    def factory(**kwargs) -> ProductBlockingReason:
        defaults = {
            "title": "Описание не соответствует товару",
            "hard_block": False,
        }
        defaults.update(kwargs)
        return ProductBlockingReason.objects.create(**defaults)

    return factory


@pytest.fixture
def no_sku_b2b_client_class():
    return NoSkuB2BClient


@pytest.fixture
def event_error_approve_b2b_client_class():
    return EventErrorApproveB2BClient


@pytest.fixture
def successful_decline_b2b_client_class():
    return SuccessfulDeclineB2BClient


@pytest.fixture
def event_error_decline_b2b_client_class():
    return EventErrorDeclineB2BClient
