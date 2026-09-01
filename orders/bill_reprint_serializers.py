from rest_framework import serializers

from orders.models import BillReprintRequest
from orders.serializers import staff_display_name


class BillReprintRequestSerializer(serializers.ModelSerializer):
    order_id = serializers.IntegerField(source="order.id", read_only=True)
    branch_name = serializers.CharField(source="order.branch.name", read_only=True)
    table_number = serializers.CharField(source="order.table_number", read_only=True)
    order_type = serializers.CharField(source="order.order_type", read_only=True)
    order_total = serializers.DecimalField(
        source="order.total_amount",
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )
    bill_print_count = serializers.IntegerField(
        source="order.bill_print_count",
        read_only=True,
    )
    requested_by_name = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()

    class Meta:
        model = BillReprintRequest
        fields = [
            "id",
            "order_id",
            "branch_name",
            "table_number",
            "order_type",
            "order_total",
            "bill_print_count",
            "status",
            "requested_by",
            "requested_by_name",
            "approved_by",
            "approved_by_name",
            "decided_at",
            "created_at",
        ]
        read_only_fields = fields

    def get_requested_by_name(self, obj):
        return staff_display_name(obj.requested_by)

    def get_approved_by_name(self, obj):
        return staff_display_name(obj.approved_by)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["approval_required"] = instance.status == "pending"
        return data
