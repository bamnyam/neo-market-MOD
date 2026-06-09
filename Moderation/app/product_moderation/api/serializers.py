from rest_framework import serializers

from app.product_moderation.models import ProductModerationFieldReport


class ApproveProductRequestSerializer(serializers.Serializer):
    moderator_comment = serializers.CharField(required=False, allow_blank=True)


class FieldReportSerializer(serializers.Serializer):
    FIELD_NAME_ALIASES = {
        "productImages": "product_images",
        "skuName": "sku_name",
        "skuImage": "sku_image",
        "skuPrice": "sku_price",
    }

    field_name = serializers.ChoiceField(
        choices=ProductModerationFieldReport.FieldName.choices
    )
    sku_id = serializers.UUIDField(required=False, allow_null=True)
    comment = serializers.CharField(max_length=500)

    def to_internal_value(self, data):
        if isinstance(data, dict) and "field_name" in data:
            data = {
                **data,
                "field_name": self.FIELD_NAME_ALIASES.get(
                    data["field_name"],
                    data["field_name"],
                ),
            }
        return super().to_internal_value(data)


class DeclineProductRequestSerializer(serializers.Serializer):
    blocking_reason_id = serializers.UUIDField()
    moderator_comment = serializers.CharField(max_length=1000)
    field_reports = FieldReportSerializer(many=True, required=False, default=list)
