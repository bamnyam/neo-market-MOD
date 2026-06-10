from rest_framework import serializers

class ApproveProductRequestSerializer(serializers.Serializer):
    comment = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class FieldReportSerializer(serializers.Serializer):
    field_path = serializers.CharField(max_length=255)
    message = serializers.CharField(max_length=500)
    severity = serializers.CharField(max_length=32)


class BlockDecisionRequestSerializer(serializers.Serializer):
    blocking_reason_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
    )
    field_reports = FieldReportSerializer(many=True, required=False, default=list)


DeclineProductRequestSerializer = BlockDecisionRequestSerializer


class ProductEventSerializer(serializers.Serializer):
    event = serializers.ChoiceField(choices=["CREATED", "EDITED", "DELETED"])
    product_id = serializers.UUIDField()
    seller_id = serializers.UUIDField()
    date = serializers.DateTimeField(required=False)
