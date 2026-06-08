import uuid

from django.db import models


class ProductBlockingReason(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    hard_block = models.BooleanField(default=False)

    class Meta:
        db_table = "product_blocking_reasons"
        ordering = ["title"]

    def __str__(self) -> str:
        return self.title
