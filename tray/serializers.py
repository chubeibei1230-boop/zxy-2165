from rest_framework import serializers
from .models import Tray, TrayRecord, InventoryRecord, TrayStatus, ConfirmStatus


class TraySerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Tray
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at', 'status']

    def validate_capacity(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError('容量上限必须大于0')
        return value

    def validate(self, attrs):
        if self.instance is not None:
            if 'status' in self.initial_data:
                raise serializers.ValidationError({'status': '不能直接修改状态，请通过业务接口进行状态流转'})
        return attrs


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


class ReleaseObservingSerializer(serializers.Serializer):
    tray_id = serializers.IntegerField()
    operator = serializers.CharField(max_length=50)
    remark = serializers.CharField(required=False, default='', allow_blank=True)
