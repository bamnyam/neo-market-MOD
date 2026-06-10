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
    def __init__(
        self,
        message: str,
        status_code: int,
        code: str = "MODERATION_DECISION_ERROR",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


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
    ticket_id: uuid.UUID,
    moderator_id: uuid.UUID,
    moderator_comment: str | None,
    b2b_client,
) -> dict[str, Any]:
    moderation = _get_ticket(ticket_id)
    _validate_moderation(moderation, moderator_id)

    try:
        product = b2b_client.get_product(str(moderation.product_id))
    except B2BClientError as exc:
        logger.exception(
            "Cannot approve ticket %s: B2B product check failed", ticket_id
        )
        raise ModerationDecisionError(
            "Failed to check product in B2B",
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "B2B_PRODUCT_CHECK_FAILED",
        ) from exc

    if len(product.get("skus") or []) == 0:
        raise ModerationDecisionError(
            "Product has no SKUs, cannot approve",
            HTTPStatus.CONFLICT,
            "PRODUCT_HAS_NO_SKUS",
        )

    try:
        with transaction.atomic():
            moderation = ProductModeration.objects.select_for_update().get(
                id=ticket_id
            )
            _validate_moderation(moderation, moderator_id)

            moderation.status = ProductModeration.Status.APPROVED
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
                str(moderation.product_id),
                "MODERATED",
            )
    except B2BClientError as exc:
        logger.exception("Cannot approve ticket %s: B2B event failed", ticket_id)
        raise ModerationDecisionError(
            "Failed to send moderation event to B2B",
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "B2B_EVENT_FAILED",
        ) from exc

    return _ticket_response(moderation)


def decline_product(
    *,
    ticket_id: uuid.UUID,
    moderator_id: uuid.UUID,
    blocking_reason_ids: list[uuid.UUID],
    field_reports: list[dict[str, Any]],
    b2b_client,
) -> dict[str, Any]:
    moderation = _get_ticket(ticket_id)
    _validate_moderation(moderation, moderator_id)

    blocking_reasons = _get_blocking_reasons(blocking_reason_ids)
    blocking_reason = blocking_reasons[0]
    target_status = (
        ProductModeration.Status.HARD_BLOCKED
        if any(reason.hard_block for reason in blocking_reasons)
        else ProductModeration.Status.BLOCKED
    )

    try:
        with transaction.atomic():
            moderation = ProductModeration.objects.select_for_update().get(
                id=ticket_id
            )
            _validate_moderation(moderation, moderator_id)

            moderation.status = target_status
            moderation.date_moderation = timezone.now()
            moderation.blocking_reason = blocking_reason
            moderation.moderator_comment = None
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
                        field_name=_legacy_field_name(field_report["field_path"]),
                        comment=field_report["message"],
                        field_path=field_report["field_path"],
                        message=field_report["message"],
                        severity=field_report["severity"],
                    )
                    for field_report in field_reports
                ]
            )

            b2b_client.send_moderation_event(
                str(moderation.product_id),
                ProductModeration.Status.BLOCKED,
            )
    except B2BClientError as exc:
        logger.exception("Cannot block ticket %s: B2B event failed", ticket_id)
        raise ModerationDecisionError(
            "Failed to send moderation event to B2B",
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "B2B_EVENT_FAILED",
        ) from exc

    return _ticket_response(moderation)


def handle_product_event(
    *,
    event: str,
    product_id: uuid.UUID,
    seller_id: uuid.UUID,
    b2b_client,
) -> None:
    if event == "EDITED":
        _handle_edited_event(product_id=product_id, b2b_client=b2b_client)
        return

    if event == "DELETED":
        ProductModeration.objects.filter(product_id=product_id).delete()
        return

    if event == "CREATED":
        _handle_created_event(
            product_id=product_id,
            seller_id=seller_id,
            b2b_client=b2b_client,
        )
        return

    raise ModerationDecisionError("Unknown product event", HTTPStatus.BAD_REQUEST)


def _get_moderation(product_id: uuid.UUID) -> ProductModeration:
    try:
        return ProductModeration.objects.get(product_id=product_id)
    except ProductModeration.DoesNotExist as exc:
        raise ModerationDecisionError(
            "Product not found in moderation queue",
            HTTPStatus.NOT_FOUND,
        ) from exc


def _get_ticket(ticket_id: uuid.UUID) -> ProductModeration:
    try:
        return ProductModeration.objects.get(id=ticket_id)
    except ProductModeration.DoesNotExist as exc:
        raise ModerationDecisionError(
            "Ticket not found",
            HTTPStatus.NOT_FOUND,
            "TICKET_NOT_FOUND",
        ) from exc


def _get_blocking_reason(blocking_reason_id: uuid.UUID) -> ProductBlockingReason:
    try:
        return ProductBlockingReason.objects.get(id=blocking_reason_id)
    except ProductBlockingReason.DoesNotExist as exc:
        raise ModerationDecisionError(
            "Blocking reason not found",
            HTTPStatus.BAD_REQUEST,
            "BLOCKING_REASON_NOT_FOUND",
        ) from exc


def _get_blocking_reasons(
    blocking_reason_ids: list[uuid.UUID],
) -> list[ProductBlockingReason]:
    reasons_by_id = {
        reason.id: reason
        for reason in ProductBlockingReason.objects.filter(id__in=blocking_reason_ids)
    }
    missing_reason_ids = [
        reason_id for reason_id in blocking_reason_ids if reason_id not in reasons_by_id
    ]
    if missing_reason_ids:
        raise ModerationDecisionError(
            "Blocking reason not found",
            HTTPStatus.BAD_REQUEST,
            "BLOCKING_REASON_NOT_FOUND",
        )
    return [reasons_by_id[reason_id] for reason_id in blocking_reason_ids]


def _legacy_field_name(field_path: str) -> str:
    legacy_names = {choice.value for choice in ProductModerationFieldReport.FieldName}
    return field_path if field_path in legacy_names else ProductModerationFieldReport.FieldName.TITLE


def _handle_created_event(
    *,
    product_id: uuid.UUID,
    seller_id: uuid.UUID,
    b2b_client,
) -> None:
    if ProductModeration.objects.filter(
        product_id=product_id,
        status=ProductModeration.Status.HARD_BLOCKED,
    ).exists():
        return

    if ProductModeration.objects.filter(product_id=product_id).exists():
        raise ModerationDecisionError(
            "Product already exists in moderation queue",
            HTTPStatus.BAD_REQUEST,
        )

    try:
        product = b2b_client.get_product(str(product_id))
    except B2BClientError as exc:
        logger.exception("Cannot process CREATED event for product %s", product_id)
        raise ModerationDecisionError(
            "Failed to get product from B2B",
            HTTPStatus.INTERNAL_SERVER_ERROR,
        ) from exc

    ProductModeration.objects.create(
        product_id=product_id,
        seller_id=seller_id,
        json_after=product,
        status=ProductModeration.Status.PENDING,
        queue_priority=ProductModeration.QueuePriority.NEW_PRODUCTS,
        total_active_quantity=ProductModeration.calculate_total_active_quantity(
            product
        ),
    )


def _handle_edited_event(*, product_id: uuid.UUID, b2b_client) -> None:
    try:
        with transaction.atomic():
            moderation = ProductModeration.objects.select_for_update().get(
                product_id=product_id
            )
            if moderation.status == ProductModeration.Status.HARD_BLOCKED:
                return

            old_status = moderation.status
            old_json_after = moderation.json_after

            try:
                product = b2b_client.get_product(str(product_id))
            except B2BClientError as exc:
                logger.exception(
                    "Cannot process EDITED event for product %s", product_id
                )
                raise ModerationDecisionError(
                    "Failed to get product from B2B",
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                ) from exc

            total_active_quantity = ProductModeration.calculate_total_active_quantity(
                product
            )
            moderation.json_before = old_json_after
            moderation.json_after = product
            moderation.status = ProductModeration.Status.PENDING
            moderation.queue_priority = ProductModeration.calculate_queue_priority(
                old_status=old_status,
                total_active_quantity=total_active_quantity,
                current_queue_priority=moderation.queue_priority,
            )
            moderation.total_active_quantity = total_active_quantity
            moderation.moderator_id = None
            moderation.save(
                update_fields=[
                    "json_before",
                    "json_after",
                    "status",
                    "queue_priority",
                    "total_active_quantity",
                    "moderator_id",
                    "date_updated",
                ]
            )
            moderation.field_reports.all().delete()
    except ProductModeration.DoesNotExist as exc:
        raise ModerationDecisionError(
            "Product not found in moderation queue",
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
            "TICKET_PERMANENTLY_BLOCKED",
        )

    if moderation.status != ProductModeration.Status.IN_REVIEW:
        raise ModerationDecisionError(
            "Ticket is not in review status",
            HTTPStatus.CONFLICT,
            "TICKET_WRONG_STATUS",
        )

    if moderation.moderator_id != moderator_id:
        raise ModerationDecisionError(
            "This ticket is not assigned to you",
            HTTPStatus.FORBIDDEN,
            "TICKET_NOT_ASSIGNED_TO_YOU",
        )


def _ticket_response(moderation: ProductModeration) -> dict[str, Any]:
    return {
        "id": str(moderation.id),
        "product_id": str(moderation.product_id),
        "seller_id": str(moderation.seller_id),
        "kind": "CREATE" if moderation.json_before is None else "EDIT",
        "status": moderation.status,
        "queue_priority": moderation.queue_priority,
        "assigned_moderator_id": (
            str(moderation.moderator_id) if moderation.moderator_id else None
        ),
        "claimed_at": None,
        "claim_expires_at": None,
        "decision_at": (
            moderation.date_moderation.isoformat()
            if moderation.date_moderation
            else None
        ),
        "created_at": moderation.date_created.isoformat(),
        "updated_at": moderation.date_updated.isoformat(),
    }
