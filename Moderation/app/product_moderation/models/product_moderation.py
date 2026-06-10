import uuid

from django.db import models
from django.db.models import Q

from app.product_moderation.models.product_blocking_reason import (
    ProductBlockingReason,
)


class ProductModeration(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        IN_REVIEW = "IN_REVIEW", "In review"
        APPROVED = "APPROVED", "Approved"
        BLOCKED = "BLOCKED", "Blocked"
        HARD_BLOCKED = "HARD_BLOCKED", "Hard blocked"

    class QueuePriority(models.IntegerChoices):
        NEW_PRODUCTS = 1, "New products"
        FIXED_AFTER_BLOCK = 2, "Fixed after block"
        EDITED_IN_STOCK = 3, "Edited in stock"
        EDITED_OUT_OF_STOCK = 4, "Edited out of stock"

    ALLOWED_STATUS_TRANSITIONS = {
        Status.PENDING: {Status.IN_REVIEW},
        Status.IN_REVIEW: {Status.APPROVED, Status.BLOCKED, Status.HARD_BLOCKED},
        Status.APPROVED: {Status.PENDING},
        Status.BLOCKED: {Status.PENDING},
        Status.HARD_BLOCKED: set(),
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product_id = models.UUIDField(unique=True)
    seller_id = models.UUIDField()
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PENDING,
    )
    queue_priority = models.PositiveSmallIntegerField(choices=QueuePriority.choices)
    total_active_quantity = models.PositiveIntegerField(default=0)
    json_before = models.JSONField(null=True, blank=True)
    json_after = models.JSONField()
    blocking_reason = models.ForeignKey(
        ProductBlockingReason,
        on_delete=models.PROTECT,
        related_name="product_moderations",
        null=True,
        blank=True,
    )
    moderator_id = models.UUIDField(null=True, blank=True)
    moderator_comment = models.TextField(null=True, blank=True)
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)
    date_moderation = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "product_moderation"
        ordering = ["queue_priority", "date_updated"]
        indexes = [
            models.Index(fields=["status", "queue_priority", "date_updated"]),
            models.Index(
                fields=["date_updated"],
                name="pm_queue_new_idx",
                condition=Q(status="PENDING", date_moderation__isnull=True),
            ),
            models.Index(
                fields=["date_updated"],
                name="pm_queue_fixed_idx",
                condition=Q(
                    status="PENDING",
                    date_moderation__isnull=False,
                    blocking_reason__isnull=False,
                ),
            ),
            models.Index(
                fields=["date_updated"],
                name="pm_queue_stock_idx",
                condition=Q(
                    status="PENDING",
                    date_moderation__isnull=False,
                    blocking_reason__isnull=True,
                    total_active_quantity__gt=0,
                ),
            ),
            models.Index(
                fields=["date_updated"],
                name="pm_queue_no_stock_idx",
                condition=Q(
                    status="PENDING",
                    date_moderation__isnull=False,
                    blocking_reason__isnull=True,
                    total_active_quantity=0,
                ),
            ),
            models.Index(fields=["seller_id"]),
            models.Index(fields=["moderator_id"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(queue_priority__gte=1) & Q(queue_priority__lte=4),
                name="product_moderation_queue_priority_1_4",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product_id} ({self.status})"

    def can_transition_to(self, target_status: str) -> bool:
        return target_status in self.ALLOWED_STATUS_TRANSITIONS[self.status]

    @staticmethod
    def calculate_total_active_quantity(product_data: dict) -> int:
        return sum(
            sku.get("active_quantity", sku.get("activeQuantity", 0))
            for sku in product_data.get("skus", [])
        )

    @classmethod
    def calculate_queue_priority(
        cls,
        *,
        old_status: str | None,
        total_active_quantity: int,
        current_queue_priority: int | None = None,
    ) -> int:
        if old_status == cls.Status.BLOCKED:
            return cls.QueuePriority.FIXED_AFTER_BLOCK
        if old_status == cls.Status.APPROVED and total_active_quantity > 0:
            return cls.QueuePriority.EDITED_IN_STOCK
        if old_status == cls.Status.APPROVED and total_active_quantity == 0:
            return cls.QueuePriority.EDITED_OUT_OF_STOCK
        return current_queue_priority or cls.QueuePriority.NEW_PRODUCTS
