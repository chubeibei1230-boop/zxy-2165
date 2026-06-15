from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.conf import settings


class TrayStatus(models.TextChoices):
    PENDING_PICKUP = 'pending_pickup', '待领取'
    CHECKED_OUT = 'checked_out', '已领出'
    PENDING_COUNT = 'pending_count', '待清点'
    PENDING_CONFIRM = 'pending_confirm', '待确认'
    AVAILABLE = 'available', '恢复可用'
    OBSERVING = 'observing', '观察中'


class ConfirmStatus(models.TextChoices):
    PENDING = 'pending', '待确认'
    CONFIRMED = 'confirmed', '已确认'


class Tray(models.Model):
    tray_code = models.CharField(max_length=50, unique=True, verbose_name='托盘编号')
    capacity = models.IntegerField(
        verbose_name='容量上限',
        validators=[MinValueValidator(1, message='容量上限必须大于0')]
    )
    area = models.CharField(max_length=100, verbose_name='所属区域')
    applicable_sessions = models.CharField(max_length=200, verbose_name='适用场次')
    responsible_person = models.CharField(max_length=50, verbose_name='责任人')
    status = models.CharField(
        max_length=20,
        choices=TrayStatus.choices,
        default=TrayStatus.PENDING_PICKUP,
        verbose_name='状态'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    remark = models.TextField(blank=True, default='', verbose_name='备注')

    class Meta:
        db_table = 'tray'
        verbose_name = '托盘'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return self.tray_code

    def clean(self):
        if self.capacity is not None and self.capacity <= 0:
            raise ValidationError({'capacity': '容量上限必须大于0'})

    def is_session_applicable(self, session):
        if not session or not self.applicable_sessions:
            return False
        sessions = [s.strip() for s in self.applicable_sessions.replace('，', ',').split(',')]
        return session in sessions

    def has_unreturned_record(self):
        return self.records.filter(is_returned=False).exists()


class TrayRecord(models.Model):
    tray = models.ForeignKey(Tray, on_delete=models.CASCADE, related_name='records', verbose_name='托盘')
    session = models.CharField(max_length=100, verbose_name='适用场次')
    receiver = models.CharField(max_length=50, verbose_name='领取人')
    receive_time = models.DateTimeField(null=True, blank=True, verbose_name='领取时间')
    return_time = models.DateTimeField(null=True, blank=True, verbose_name='归还时间')
    is_returned = models.BooleanField(default=False, verbose_name='是否已归还')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        db_table = 'tray_record'
        verbose_name = '领还记录'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.tray.tray_code} - {self.session}'


class InventoryRecord(models.Model):
    tray = models.ForeignKey(Tray, on_delete=models.CASCADE, related_name='inventory_records', verbose_name='托盘')
    tray_record = models.ForeignKey(TrayRecord, on_delete=models.SET_NULL, null=True, blank=True, related_name='inventory_records', verbose_name='领还记录')
    inventory_time = models.DateTimeField(auto_now_add=True, verbose_name='清点时间')
    actual_count = models.IntegerField(verbose_name='实际数量')
    expected_count = models.IntegerField(verbose_name='应存数量')
    diff_count = models.IntegerField(verbose_name='差异数量')
    diff_description = models.TextField(blank=True, default='', verbose_name='差异说明')
    confirm_status = models.CharField(
        max_length=20,
        choices=ConfirmStatus.choices,
        default=ConfirmStatus.PENDING,
        verbose_name='确认状态'
    )
    confirmer = models.CharField(max_length=50, blank=True, default='', verbose_name='确认人')
    confirm_time = models.DateTimeField(null=True, blank=True, verbose_name='确认时间')
    conclusion = models.TextField(blank=True, default='', verbose_name='确认结论')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        db_table = 'inventory_record'
        verbose_name = '清点记录'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.tray.tray_code} - 清点差异:{self.diff_count}'
