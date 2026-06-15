from rest_framework import serializers
from .models import Tray, TrayRecord, InventoryRecord, TrayStatus, ConfirmStatus


class TraySerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Tray
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class TrayRecordSerializer(serializers.ModelSerializer):
    tray_code = serializers.CharField(source='tray.tray_code', read_only=True)

    class Meta:
        model = TrayRecord
        fields = '__all__'
        read_only_fields = ['created_at']


class InventoryRecordSerializer(serializers.ModelSerializer):
    tray_code = serializers.CharField(source='tray.tray_code', read_only=True)
    confirm_status_display = serializers.CharField(source='get_confirm_status_display', read_only=True)

    class Meta:
        model = InventoryRecord
        fields = '__all__'
        read_only_fields = ['created_at', 'inventory_time']


class PickupSerializer(serializers.Serializer):
    tray_id = serializers.IntegerField()
    session = serializers.CharField(max_length=100)
    receiver = serializers.CharField(max_length=50)


class ReturnSerializer(serializers.Serializer):
    tray_id = serializers.IntegerField()


class InventorySerializer(serializers.Serializer):
    tray_id = serializers.IntegerField()
    actual_count = serializers.IntegerField()
    expected_count = serializers.IntegerField()
    diff_description = serializers.CharField(required=False, default='', allow_blank=True)


class ConfirmSerializer(serializers.Serializer):
    inventory_id = serializers.IntegerField()
    confirmer = serializers.CharField(max_length=50)
    conclusion = serializers.CharField(required=False, default='', allow_blank=True)
