from rest_framework import serializers


class ApproveProductRequestSerializer(serializers.Serializer):
    moderator_comment = serializers.CharField(required=False, allow_blank=True)
