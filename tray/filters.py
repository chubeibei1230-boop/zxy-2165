import django_filters
from .models import Tray, TrayRecord, InventoryRecord, AbnormalHandling


class TrayFilter(django_filters.FilterSet):
    area = django_filters.CharFilter(field_name='area', lookup_expr='icontains')
    applicable_sessions = django_filters.CharFilter(field_name='applicable_sessions', lookup_expr='icontains')
    responsible_person = django_filters.CharFilter(field_name='responsible_person', lookup_expr='icontains')
    status = django_filters.CharFilter(field_name='status')
    start_date = django_filters.DateFilter(field_name='created_at', lookup_expr='gte')
    end_date = django_filters.DateFilter(field_name='created_at', lookup_expr='lte')

    class Meta:
        model = Tray
        fields = ['area', 'applicable_sessions', 'responsible_person', 'status']


class TrayRecordFilter(django_filters.FilterSet):
    area = django_filters.CharFilter(field_name='tray__area', lookup_expr='icontains')
    session = django_filters.CharFilter(field_name='session', lookup_expr='icontains')
    receiver = django_filters.CharFilter(field_name='receiver', lookup_expr='icontains')
    is_returned = django_filters.BooleanFilter(field_name='is_returned')
    start_date = django_filters.DateFilter(field_name='receive_time', lookup_expr='gte')
    end_date = django_filters.DateFilter(field_name='receive_time', lookup_expr='lte')
    tray_code = django_filters.CharFilter(field_name='tray__tray_code', lookup_expr='icontains')

    class Meta:
        model = TrayRecord
        fields = ['tray', 'session', 'receiver', 'is_returned']


class InventoryRecordFilter(django_filters.FilterSet):
    area = django_filters.CharFilter(field_name='tray__area', lookup_expr='icontains')
    session = django_filters.CharFilter(field_name='tray_record__session', lookup_expr='icontains')
    responsible_person = django_filters.CharFilter(field_name='tray__responsible_person', lookup_expr='icontains')
    confirm_status = django_filters.CharFilter(field_name='confirm_status')
    start_date = django_filters.DateFilter(field_name='inventory_time', lookup_expr='gte')
    end_date = django_filters.DateFilter(field_name='inventory_time', lookup_expr='lte')
    min_diff = django_filters.NumberFilter(field_name='diff_count', lookup_expr='gte')
    max_diff = django_filters.NumberFilter(field_name='diff_count', lookup_expr='lte')
    tray_code = django_filters.CharFilter(field_name='tray__tray_code', lookup_expr='icontains')

    class Meta:
        model = InventoryRecord
        fields = ['tray', 'confirm_status']


class AbnormalHandlingFilter(django_filters.FilterSet):
    tray_code = django_filters.CharFilter(field_name='tray__tray_code', lookup_expr='icontains')
    area = django_filters.CharFilter(field_name='tray__area', lookup_expr='icontains')
    handler = django_filters.CharFilter(field_name='handler', lookup_expr='icontains')
    status = django_filters.CharFilter(field_name='status')
    source = django_filters.CharFilter(field_name='source')
    start_date = django_filters.DateFilter(field_name='created_at', lookup_expr='gte')
    end_date = django_filters.DateFilter(field_name='created_at', lookup_expr='lte')
    tray_id = django_filters.NumberFilter(field_name='tray__id')

    class Meta:
        model = AbnormalHandling
        fields = ['tray', 'handler', 'status', 'source']
