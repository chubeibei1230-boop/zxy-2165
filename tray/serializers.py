from rest_framework import serializers
from .models import (
    Tray, TrayRecord, InventoryRecord, TrayStatus, ConfirmStatus,
    AbnormalHandling, AbnormalSource, AbnormalStatus,
    ReviewTask, ReviewTaskStatus, ReviewTaskSource, ReviewResult
)


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


class AbnormalHandlingSerializer(serializers.ModelSerializer):
    tray_code = serializers.CharField(source='tray.tray_code', read_only=True)
    tray_area = serializers.CharField(source='tray.area', read_only=True)
    source_display = serializers.CharField(source='get_source_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = AbnormalHandling
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at', 'resolved_at', 'closed_at']


class AbnormalHandlingDetailSerializer(AbnormalHandlingSerializer):
    tray_detail = TraySerializer(source='tray', read_only=True)
    tray_record_detail = TrayRecordSerializer(source='tray_record', read_only=True)
    inventory_record_detail = InventoryRecordSerializer(source='inventory_record', read_only=True)

    class Meta(AbnormalHandlingSerializer.Meta):
        fields = '__all__'


class AbnormalHandlingCreateSerializer(serializers.Serializer):
    tray_id = serializers.IntegerField()
    inventory_record_id = serializers.IntegerField(required=False, allow_null=True)
    tray_record_id = serializers.IntegerField(required=False, allow_null=True)
    source = serializers.ChoiceField(choices=AbnormalSource.choices, default=AbnormalSource.INVENTORY_DIFF)
    handler = serializers.CharField(max_length=50)
    measures = serializers.CharField(required=False, default='', allow_blank=True)
    expected_completion_time = serializers.DateTimeField(required=False, allow_null=True)
    description = serializers.CharField(required=False, default='', allow_blank=True)


class AbnormalHandlingResolveSerializer(serializers.Serializer):
    result = serializers.CharField()
    measures = serializers.CharField(required=False, default='', allow_blank=True)


class AbnormalHandlingCloseSerializer(serializers.Serializer):
    pass


class ReviewDiffDetailSerializer(serializers.ModelSerializer):
    tray_code = serializers.CharField(source='tray.tray_code', read_only=True)
    tray_area = serializers.CharField(source='tray.area', read_only=True)
    tray_responsible_person = serializers.CharField(source='tray.responsible_person', read_only=True)
    session = serializers.CharField(source='tray_record.session', read_only=True, allow_null=True)
    receiver = serializers.CharField(source='tray_record.receiver', read_only=True, allow_null=True)
    confirm_status_display = serializers.CharField(source='get_confirm_status_display', read_only=True)
    has_abnormal = serializers.SerializerMethodField()
    abnormal_status = serializers.SerializerMethodField()
    abnormal_status_display = serializers.SerializerMethodField()
    abnormal_handler = serializers.SerializerMethodField()

    class Meta:
        model = InventoryRecord
        fields = [
            'id', 'tray_code', 'tray_area', 'tray_responsible_person',
            'session', 'receiver',
            'inventory_time', 'actual_count', 'expected_count', 'diff_count',
            'diff_description', 'confirm_status', 'confirm_status_display',
            'confirmer', 'confirm_time', 'conclusion',
            'has_abnormal', 'abnormal_status', 'abnormal_status_display', 'abnormal_handler'
        ]

    def get_has_abnormal(self, obj):
        return obj.abnormal_handlings.exists()

    def get_abnormal_status(self, obj):
        abnormal = obj.abnormal_handlings.order_by('-created_at').first()
        return abnormal.status if abnormal else None

    def get_abnormal_status_display(self, obj):
        abnormal = obj.abnormal_handlings.order_by('-created_at').first()
        return abnormal.get_status_display() if abnormal else None

    def get_abnormal_handler(self, obj):
        abnormal = obj.abnormal_handlings.order_by('-created_at').first()
        return abnormal.handler if abnormal else None


class ReviewAbnormalListSerializer(serializers.ModelSerializer):
    tray_code = serializers.CharField(source='tray.tray_code', read_only=True)
    tray_area = serializers.CharField(source='tray.area', read_only=True)
    tray_responsible_person = serializers.CharField(source='tray.responsible_person', read_only=True)
    session = serializers.CharField(source='tray_record.session', read_only=True, allow_null=True)
    receiver = serializers.CharField(source='tray_record.receiver', read_only=True, allow_null=True)
    source_display = serializers.CharField(source='get_source_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    is_overdue = serializers.SerializerMethodField()
    inventory_diff_count = serializers.IntegerField(source='inventory_record.diff_count', read_only=True, allow_null=True)

    class Meta:
        model = AbnormalHandling
        fields = [
            'id', 'tray_code', 'tray_area', 'tray_responsible_person',
            'session', 'receiver',
            'source', 'source_display', 'description',
            'handler', 'measures', 'expected_completion_time',
            'status', 'status_display', 'is_overdue',
            'result', 'created_at', 'updated_at', 'resolved_at', 'closed_at',
            'inventory_diff_count'
        ]

    def get_is_overdue(self, obj):
        if obj.expected_completion_time and obj.status in [AbnormalStatus.PENDING, AbnormalStatus.PROCESSING]:
            from django.utils import timezone
            return obj.expected_completion_time < timezone.now()
        return False


class ReviewTrayStatSerializer(serializers.Serializer):
    tray_id = serializers.IntegerField()
    tray_code = serializers.CharField()
    area = serializers.CharField()
    responsible_person = serializers.CharField()
    abnormal_total = serializers.IntegerField()
    abnormal_pending = serializers.IntegerField()
    abnormal_processing = serializers.IntegerField()
    abnormal_resolved = serializers.IntegerField()
    abnormal_closed = serializers.IntegerField()
    abnormal_overdue = serializers.IntegerField()
    diff_total_amount = serializers.IntegerField()
    diff_record_count = serializers.IntegerField()


class ReviewAreaStatSerializer(serializers.Serializer):
    area = serializers.CharField()
    tray_count = serializers.IntegerField()
    abnormal_total = serializers.IntegerField()
    abnormal_pending = serializers.IntegerField()
    abnormal_processing = serializers.IntegerField()
    abnormal_resolved = serializers.IntegerField()
    abnormal_closed = serializers.IntegerField()
    abnormal_overdue = serializers.IntegerField()
    diff_total_amount = serializers.IntegerField()


class ReviewPersonStatSerializer(serializers.Serializer):
    responsible_person = serializers.CharField()
    tray_count = serializers.IntegerField()
    abnormal_total = serializers.IntegerField()
    abnormal_pending = serializers.IntegerField()
    abnormal_processing = serializers.IntegerField()
    abnormal_resolved = serializers.IntegerField()
    abnormal_closed = serializers.IntegerField()
    abnormal_overdue = serializers.IntegerField()
    diff_total_amount = serializers.IntegerField()


class ReviewSessionStatSerializer(serializers.Serializer):
    session = serializers.CharField()
    record_count = serializers.IntegerField()
    abnormal_total = serializers.IntegerField()
    abnormal_pending = serializers.IntegerField()
    diff_total_amount = serializers.IntegerField()


class TrajectoryEventSerializer(serializers.Serializer):
    event_type = serializers.CharField()
    event_type_display = serializers.CharField()
    event_time = serializers.DateTimeField()
    operator = serializers.CharField(allow_null=True, allow_blank=True)
    description = serializers.CharField()
    detail = serializers.DictField()


class TrayTrajectorySerializer(serializers.Serializer):
    tray_id = serializers.IntegerField()
    tray_code = serializers.CharField()
    area = serializers.CharField()
    responsible_person = serializers.CharField()
    current_status = serializers.CharField()
    current_status_display = serializers.CharField()
    total_events = serializers.IntegerField()
    total_abnormal = serializers.IntegerField()
    pending_abnormal = serializers.IntegerField()
    events = TrajectoryEventSerializer(many=True)


class ReviewTaskSerializer(serializers.ModelSerializer):
    tray_code = serializers.CharField(source='tray.tray_code', read_only=True)
    tray_area = serializers.CharField(source='tray.area', read_only=True)
    tray_responsible_person = serializers.CharField(source='tray.responsible_person', read_only=True)
    session = serializers.CharField(source='tray_record.session', read_only=True, allow_null=True)
    receiver = serializers.CharField(source='tray_record.receiver', read_only=True, allow_null=True)
    source_display = serializers.CharField(source='get_source_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    review_result_display = serializers.CharField(source='get_review_result_display', read_only=True, allow_null=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    inventory_diff_count = serializers.IntegerField(source='inventory_record.diff_count', read_only=True, allow_null=True)
    abnormal_status = serializers.CharField(source='abnormal_handling.status', read_only=True, allow_null=True)
    abnormal_status_display = serializers.CharField(source='abnormal_handling.get_status_display', read_only=True, allow_null=True)

    class Meta:
        model = ReviewTask
        fields = '__all__'
        read_only_fields = [
            'created_at', 'updated_at', 'task_code', 'review_time',
            'assign_time', 'completed_time', 'cancelled_time'
        ]


class ReviewTaskDetailSerializer(ReviewTaskSerializer):
    tray_detail = TraySerializer(source='tray', read_only=True)
    tray_record_detail = TrayRecordSerializer(source='tray_record', read_only=True)
    inventory_record_detail = InventoryRecordSerializer(source='inventory_record', read_only=True)
    abnormal_handling_detail = AbnormalHandlingSerializer(source='abnormal_handling', read_only=True)

    class Meta(ReviewTaskSerializer.Meta):
        fields = '__all__'


class ReviewTaskCreateSerializer(serializers.Serializer):
    tray_id = serializers.IntegerField()
    inventory_record_id = serializers.IntegerField(required=False, allow_null=True)
    tray_record_id = serializers.IntegerField(required=False, allow_null=True)
    abnormal_handling_id = serializers.IntegerField(required=False, allow_null=True)
    source = serializers.ChoiceField(choices=ReviewTaskSource.choices, default=ReviewTaskSource.MANUAL)
    description = serializers.CharField(required=False, default='', allow_blank=True)
    priority = serializers.ChoiceField(
        choices=[('high', '高'), ('medium', '中'), ('low', '低')],
        required=False, default='medium'
    )
    creator = serializers.CharField(required=False, default='', allow_blank=True)
    reviewer = serializers.CharField(required=False, default='', allow_blank=True)


class ReviewTaskAssignSerializer(serializers.Serializer):
    reviewer = serializers.CharField(max_length=50)


class ReviewTaskSubmitSerializer(serializers.Serializer):
    review_result = serializers.ChoiceField(choices=ReviewResult.choices)
    review_opinion = serializers.CharField(required=False, default='', allow_blank=True)


class ReviewTaskCancelSerializer(serializers.Serializer):
    cancel_reason = serializers.CharField()


class ReviewTaskStatsSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    pending_assign = serializers.IntegerField()
    processing = serializers.IntegerField()
    completed = serializers.IntegerField()
    cancelled = serializers.IntegerField()
    completion_rate = serializers.FloatField()
    source_distribution = serializers.ListField(child=serializers.DictField())
    priority_distribution = serializers.ListField(child=serializers.DictField())
