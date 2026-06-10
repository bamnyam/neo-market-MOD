import uuid

from django.db import models

from app.product_moderation.models.product_moderation import ProductModeration


class ProductModerationFieldReport(models.Model):
    class FieldName(models.TextChoices):
        TITLE = "title", "Title"
        DESCRIPTION = "description", "Description"
        PRODUCT_IMAGES = "product_images", "Product images"
        CATEGORY = "category", "Category"
        SKU_NAME = "sku_name", "SKU name"
        SKU_IMAGE = "sku_image", "SKU image"
        SKU_PRICE = "sku_price", "SKU price"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product_moderation = models.ForeignKey(
        ProductModeration,
        on_delete=models.CASCADE,
        related_name="field_reports",
    )
    field_name = models.CharField(max_length=32, choices=FieldName.choices)
    sku_id = models.UUIDField(null=True, blank=True)
    comment = models.TextField()
    field_path = models.CharField(max_length=255, null=True, blank=True)
    message = models.TextField(null=True, blank=True)
    severity = models.CharField(max_length=32, null=True, blank=True)
    date_created = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "product_moderation_field_report"
        ordering = ["date_created"]
        indexes = [
            models.Index(fields=["product_moderation", "field_name"]),
            models.Index(fields=["sku_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.field_name}: {self.product_moderation_id}"
