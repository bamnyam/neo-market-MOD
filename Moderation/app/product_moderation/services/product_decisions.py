import logging
import uuid
from http import HTTPStatus
from typing import Any

from django.db import transaction
from django.utils import timezone

from app.product_moderation.api import B2BClientError
from app.product_moderation.models import (
    ProductBlockingReason,
    ProductModeration,
    ProductModerationFieldReport,
)

logger = logging.getLogger(__name__)


class ModerationDecisionError(Exception):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def get_moderator_id(request) -> uuid.UUID | None:
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


def approve_product(
    *,
    product_id: uuid.UUID,
    moderator_id: uuid.UUID,
    moderator_comment: str | None,
    b2b_client,
) -> dict[str, str]:
    moderation = _get_moderation(product_id)
    _validate_moderation(moderation, moderator_id)

    try:
        product = b2b_client.get_product(str(product_id))
    except B2BClientError as exc:
        logger.exception(
            "Cannot approve product %s: B2B product check failed", product_id
        )
        raise ModerationDecisionError(
            "Failed to check product in B2B",
            HTTPStatus.INTERNAL_SERVER_ERROR,
        ) from exc

    if len(product.get("skus") or []) == 0:
        raise ModerationDecisionError(
            "Product has no SKUs, cannot approve",
            HTTPStatus.CONFLICT,
        )

    try:
        with transaction.atomic():
            moderation = ProductModeration.objects.select_for_update().get(
                product_id=product_id
            )
            _validate_moderation(moderation, moderator_id)

            moderation.status = ProductModeration.Status.MODERATED
            moderation.date_moderation = timezone.now()
            moderation.moderator_comment = moderator_comment
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
            b2b_client.send_moderation_event(
                str(product_id),
                ProductModeration.Status.MODERATED,
            )
    except B2BClientError as exc:
        logger.exception("Cannot approve product %s: B2B event failed", product_id)
        raise ModerationDecisionError(
            "Failed to send moderation event to B2B",
            HTTPStatus.INTERNAL_SERVER_ERROR,
        ) from exc

    return {
        "product_id": str(product_id),
        "status": ProductModeration.Status.MODERATED,
    }


def decline_product(
    *,
    product_id: uuid.UUID,
    moderator_id: uuid.UUID,
    blocking_reason_id: uuid.UUID,
    moderator_comment: str,
    field_reports: list[dict[str, Any]],
    b2b_client,
) -> dict[str, str]:
    moderation = _get_moderation(product_id)
    _validate_moderation(moderation, moderator_id)

    blocking_reason = _get_blocking_reason(blocking_reason_id)
    if blocking_reason.hard_block:
        raise ModerationDecisionError(
            "Blocking reason requires hard block flow",
            HTTPStatus.BAD_REQUEST,
        )

    try:
        with transaction.atomic():
            moderation = ProductModeration.objects.select_for_update().get(
                product_id=product_id
            )
            _validate_moderation(moderation, moderator_id)

            moderation.status = ProductModeration.Status.BLOCKED
            moderation.date_moderation = timezone.now()
            moderation.blocking_reason = blocking_reason
            moderation.moderator_comment = moderator_comment
            moderation.save(
                update_fields=[
                    "status",
                    "date_moderation",
                    "blocking_reason",
                    "moderator_comment",
                    "date_updated",
                ]
            )

            moderation.field_reports.all().delete()
            ProductModerationFieldReport.objects.bulk_create(
                [
                    ProductModerationFieldReport(
                        product_moderation=moderation,
                        field_name=field_report["field_name"],
                        sku_id=field_report.get("sku_id"),
                        comment=field_report["comment"],
                    )
                    for field_report in field_reports
                ]
            )

            b2b_client.send_moderation_event(
                str(product_id),
                ProductModeration.Status.BLOCKED,
                hard_block=False,
                blocking_reason={
                    "id": str(blocking_reason.id),
                    "title": blocking_reason.title,
                    "comment": moderator_comment,
                },
                field_reports=[
                    {
                        "field_name": field_report["field_name"],
                        "sku_id": (
                            str(field_report["sku_id"])
                            if field_report.get("sku_id") is not None
                            else None
                        ),
                        "comment": field_report["comment"],
                    }
                    for field_report in field_reports
                ],
            )
    except B2BClientError as exc:
        logger.exception("Cannot decline product %s: B2B event failed", product_id)
        raise ModerationDecisionError(
            "Failed to send moderation event to B2B",
            HTTPStatus.INTERNAL_SERVER_ERROR,
        ) from exc

    return {
        "product_id": str(product_id),
        "status": ProductModeration.Status.BLOCKED,
    }


def _get_moderation(product_id: uuid.UUID) -> ProductModeration:
    try:
        return ProductModeration.objects.get(product_id=product_id)
    except ProductModeration.DoesNotExist as exc:
        raise ModerationDecisionError(
            "Product not found in moderation queue",
            HTTPStatus.NOT_FOUND,
        ) from exc


def _get_blocking_reason(blocking_reason_id: uuid.UUID) -> ProductBlockingReason:
    try:
        return ProductBlockingReason.objects.get(id=blocking_reason_id)
    except ProductBlockingReason.DoesNotExist as exc:
        raise ModerationDecisionError(
            "Blocking reason not found",
            HTTPStatus.BAD_REQUEST,
        ) from exc


def _validate_moderation(
    moderation: ProductModeration,
    moderator_id: uuid.UUID,
) -> None:
    if moderation.status == ProductModeration.Status.HARD_BLOCKED:
        raise ModerationDecisionError(
            "Product is permanently blocked",
            HTTPStatus.CONFLICT,
        )

    if moderation.status != ProductModeration.Status.IN_REVIEW:
        raise ModerationDecisionError(
            "Product is not in review",
            HTTPStatus.CONFLICT,
        )

    if moderation.moderator_id != moderator_id:
        raise ModerationDecisionError(
            "This moderation card is not assigned to you",
            HTTPStatus.FORBIDDEN,
        )
