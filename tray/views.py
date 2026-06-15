from datetime import timedelta
from django.db import models
from django.db.models import Count, Sum, Avg, Q, F, ExpressionWrapper, IntegerField
from django.utils import timezone
from django.conf import settings
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Tray, TrayRecord, InventoryRecord, TrayStatus, ConfirmStatus, AbnormalHandling, AbnormalSource, AbnormalStatus
from .serializers import (
    TraySerializer, TrayRecordSerializer, InventoryRecordSerializer,
    PickupSerializer, ReturnSerializer, InventorySerializer, ConfirmSerializer,
    ReleaseObservingSerializer,
    AbnormalHandlingSerializer, AbnormalHandlingDetailSerializer,
    AbnormalHandlingCreateSerializer, AbnormalHandlingResolveSerializer,
    AbnormalHandlingCloseSerializer
)
from .filters import TrayFilter, TrayRecordFilter, InventoryRecordFilter, AbnormalHandlingFilter


class TrayViewSet(viewsets.ModelViewSet):
    queryset = Tray.objects.all()
    serializer_class = TraySerializer
    filterset_class = TrayFilter
    search_fields = ['tray_code', 'area', 'responsible_person', 'applicable_sessions']
    ordering_fields = ['created_at', 'updated_at', 'tray_code']

    @action(detail=False, methods=['post'], serializer_class=PickupSerializer)
    def pickup(self, request):
        serializer = PickupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            tray = Tray.objects.get(id=data['tray_id'])
        except Tray.DoesNotExist:
            return Response({'detail': '托盘不存在'}, status=status.HTTP_404_NOT_FOUND)

        if tray.has_unreturned_record():
            return Response({'detail': '该托盘存在未归还的领出记录，不能再次领取'}, status=status.HTTP_400_BAD_REQUEST)

        if tray.status == TrayStatus.CHECKED_OUT:
            return Response({'detail': '该托盘已领出，未归还前不能再次领取'}, status=status.HTTP_400_BAD_REQUEST)

        if tray.status not in [TrayStatus.PENDING_PICKUP, TrayStatus.AVAILABLE]:
            return Response({'detail': f'当前状态为{tray.get_status_display()}，不能领取'}, status=status.HTTP_400_BAD_REQUEST)

        if not tray.is_session_applicable(data['session']):
            return Response({
                'detail': f'场次"{data["session"]}"不在托盘适用场次范围内，适用场次为：{tray.applicable_sessions}'
            }, status=status.HTTP_400_BAD_REQUEST)

        tray.status = TrayStatus.CHECKED_OUT
        tray.save()

        record = TrayRecord.objects.create(
            tray=tray,
            session=data['session'],
            receiver=data['receiver'],
            receive_time=timezone.now()
        )

        return Response({
            'tray': TraySerializer(tray).data,
            'record': TrayRecordSerializer(record).data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], serializer_class=ReturnSerializer)
    def return_tray(self, request):
        serializer = ReturnSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            tray = Tray.objects.get(id=data['tray_id'])
        except Tray.DoesNotExist:
            return Response({'detail': '托盘不存在'}, status=status.HTTP_404_NOT_FOUND)

        if tray.status != TrayStatus.CHECKED_OUT:
            return Response({'detail': f'当前状态为{tray.get_status_display()}，不能归还'}, status=status.HTTP_400_BAD_REQUEST)

        tray.status = TrayStatus.PENDING_COUNT
        tray.save()

        latest_record = TrayRecord.objects.filter(tray=tray, is_returned=False).order_by('-created_at').first()
        if latest_record:
            latest_record.return_time = timezone.now()
            latest_record.is_returned = True
            latest_record.save()

        return Response({
            'tray': TraySerializer(tray).data,
            'record': TrayRecordSerializer(latest_record).data if latest_record else None
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], serializer_class=InventorySerializer)
    def inventory(self, request):
        serializer = InventorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            tray = Tray.objects.get(id=data['tray_id'])
        except Tray.DoesNotExist:
            return Response({'detail': '托盘不存在'}, status=status.HTTP_404_NOT_FOUND)

        if tray.status != TrayStatus.PENDING_COUNT:
            return Response({'detail': f'当前状态为{tray.get_status_display()}，不能清点'}, status=status.HTTP_400_BAD_REQUEST)

        diff_count = data['actual_count'] - data['expected_count']

        latest_record = TrayRecord.objects.filter(tray=tray).order_by('-created_at').first()

        inventory = InventoryRecord.objects.create(
            tray=tray,
            tray_record=latest_record,
            actual_count=data['actual_count'],
            expected_count=data['expected_count'],
            diff_count=diff_count,
            diff_description=data.get('diff_description', '')
        )

        threshold = getattr(settings, 'DIFF_THRESHOLD', 5)

        if abs(diff_count) > threshold:
            tray.status = TrayStatus.OBSERVING
        else:
            tray.status = TrayStatus.PENDING_CONFIRM

        tray.save()

        return Response({
            'tray': TraySerializer(tray).data,
            'inventory': InventoryRecordSerializer(inventory).data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], serializer_class=ConfirmSerializer)
    def confirm(self, request):
        serializer = ConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            inventory = InventoryRecord.objects.get(id=data['inventory_id'])
        except InventoryRecord.DoesNotExist:
            return Response({'detail': '清点记录不存在'}, status=status.HTTP_404_NOT_FOUND)

        if inventory.confirm_status == ConfirmStatus.CONFIRMED:
            return Response({'detail': '该清点记录已确认，无需重复确认'}, status=status.HTTP_400_BAD_REQUEST)

        tray = inventory.tray

        if tray.status not in [TrayStatus.PENDING_CONFIRM, TrayStatus.OBSERVING]:
            return Response({'detail': f'当前状态为{tray.get_status_display()}，不能确认'}, status=status.HTTP_400_BAD_REQUEST)

        conclusion = data.get('conclusion', '').strip()
        if tray.status == TrayStatus.OBSERVING and not conclusion:
            return Response({'detail': '观察中的托盘确认时必须填写确认结论'}, status=status.HTTP_400_BAD_REQUEST)

        if tray.status == TrayStatus.OBSERVING:
            pending_abnormal_count = AbnormalHandling.objects.filter(
                tray=tray,
                status__in=[AbnormalStatus.PENDING, AbnormalStatus.PROCESSING]
            ).count()
            if pending_abnormal_count > 0:
                return Response(
                    {'detail': f'该托盘存在{pending_abnormal_count}个未处理的异常单，请先处理异常后再确认'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        pending_count = InventoryRecord.objects.filter(
            tray=tray,
            confirm_status=ConfirmStatus.PENDING
        ).exclude(id=inventory.id).count()

        inventory.confirm_status = ConfirmStatus.CONFIRMED
        inventory.confirmer = data['confirmer']
        inventory.confirm_time = timezone.now()
        inventory.conclusion = conclusion
        inventory.save()

        if pending_count == 0:
            tray.status = TrayStatus.AVAILABLE
            tray.save()

        return Response({
            'tray': TraySerializer(tray).data,
            'inventory': InventoryRecordSerializer(inventory).data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], serializer_class=ReleaseObservingSerializer)
    def release_observing(self, request):
        serializer = ReleaseObservingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            tray = Tray.objects.get(id=data['tray_id'])
        except Tray.DoesNotExist:
            return Response({'detail': '托盘不存在'}, status=status.HTTP_404_NOT_FOUND)

        if tray.status != TrayStatus.OBSERVING:
            return Response({'detail': f'当前状态为{tray.get_status_display()}，不是观察中状态，无需解除'}, status=status.HTTP_400_BAD_REQUEST)

        pending_count = InventoryRecord.objects.filter(
            tray=tray,
            confirm_status=ConfirmStatus.PENDING
        ).count()
        if pending_count > 0:
            return Response({'detail': f'该托盘还有{pending_count}条待确认的清点记录，请先确认完毕'}, status=status.HTTP_400_BAD_REQUEST)

        remark = data.get('remark', '').strip()
        if not remark:
            return Response({'detail': '解除观察时必须填写处理说明'}, status=status.HTTP_400_BAD_REQUEST)

        tray.status = TrayStatus.AVAILABLE
        if tray.remark:
            tray.remark = tray.remark + f'\n[{timezone.now().strftime("%Y-%m-%d %H:%M:%S")}] 解除观察，操作人：{data["operator"]}，说明：{remark}'
        else:
            tray.remark = f'[{timezone.now().strftime("%Y-%m-%d %H:%M:%S")}] 解除观察，操作人：{data["operator"]}，说明：{remark}'
        tray.save()

        return Response({
            'tray': TraySerializer(tray).data,
            'detail': '已成功解除观察状态，托盘恢复可用'
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='stats/overview')
    def stats_overview(self, request):
        total_trays = Tray.objects.count()
        status_stats = Tray.objects.values('status').annotate(count=Count('id'))
        status_map = {s['status']: s['count'] for s in status_stats}

        pending_confirm_count = InventoryRecord.objects.filter(
            confirm_status=ConfirmStatus.PENDING
        ).count()

        total_diff_count = InventoryRecord.objects.filter(
            confirm_status=ConfirmStatus.CONFIRMED
        ).aggregate(total=Sum('diff_count'))['total'] or 0

        today = timezone.now().date()
        today_records = TrayRecord.objects.filter(
            receive_time__date=today
        ).count()

        return Response({
            'total_trays': total_trays,
            'status_stats': status_map,
            'pending_confirm_count': pending_confirm_count,
            'total_diff_count': abs(total_diff_count),
            'today_pickup_count': today_records,
            'abnormal_pending_count': AbnormalHandling.objects.filter(
                status__in=[AbnormalStatus.PENDING, AbnormalStatus.PROCESSING]
            ).count(),
            'abnormal_resolved_count': AbnormalHandling.objects.filter(
                status__in=[AbnormalStatus.RESOLVED, AbnormalStatus.CLOSED]
            ).count(),
            'abnormal_area_distribution': list(
                AbnormalHandling.objects.filter(
                    status__in=[AbnormalStatus.PENDING, AbnormalStatus.PROCESSING]
                ).values('tray__area').annotate(count=Count('id')).order_by('-count')
            ),
        })

    @action(detail=False, methods=['get'], url_path='stats/high-diff-trays')
    def high_diff_trays(self, request):
        limit = int(request.query_params.get('limit', 10))
        min_diff_count = int(request.query_params.get('min_diff_count', 3))

        from django.db.models import Case, When, IntegerField

        abs_diff = Sum(
            Case(
                When(inventory_records__diff_count__gt=0, then=F('inventory_records__diff_count')),
                When(inventory_records__diff_count__lt=0, then=-F('inventory_records__diff_count')),
                default=0,
                output_field=IntegerField()
            )
        )

        trays = Tray.objects.annotate(
            diff_count=Count('inventory_records', filter=~Q(inventory_records__diff_count=0)),
            total_diff=abs_diff
        ).filter(diff_count__gte=min_diff_count).order_by('-diff_count')[:limit]

        data = []
        for tray in trays:
            data.append({
                'tray_id': tray.id,
                'tray_code': tray.tray_code,
                'area': tray.area,
                'responsible_person': tray.responsible_person,
                'diff_times': tray.diff_count,
                'total_diff_amount': tray.total_diff or 0,
                'status': tray.status,
                'status_display': tray.get_status_display(),
            })

        return Response(data)

    @action(detail=False, methods=['get'], url_path='stats/area-efficiency')
    def area_efficiency(self, request):
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        queryset = TrayRecord.objects.all()
        if start_date:
            queryset = queryset.filter(receive_time__gte=start_date)
        if end_date:
            queryset = queryset.filter(receive_time__lte=end_date + ' 23:59:59')

        queryset = queryset.filter(is_returned=True)

        area_stats = queryset.values('tray__area').annotate(
            total_turnovers=Count('id'),
            avg_duration=Avg(F('return_time') - F('receive_time'))
        ).order_by('-total_turnovers')

        data = []
        for stat in area_stats:
            avg_duration = stat['avg_duration']
            avg_hours = avg_duration.total_seconds() / 3600 if avg_duration else 0
            data.append({
                'area': stat['tray__area'],
                'total_turnovers': stat['total_turnovers'],
                'avg_duration_hours': round(avg_hours, 2),
            })

        return Response(data)

    @action(detail=False, methods=['get'], url_path='stats/daily-trend')
    def daily_trend(self, request):
        days = int(request.query_params.get('days', 30))
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days - 1)

        daily_data = []
        for i in range(days):
            current_date = start_date + timedelta(days=i)
            next_date = current_date + timedelta(days=1)

            pickup_count = TrayRecord.objects.filter(
                receive_time__gte=current_date,
                receive_time__lt=next_date
            ).count()

            return_count = TrayRecord.objects.filter(
                return_time__gte=current_date,
                return_time__lt=next_date,
                is_returned=True
            ).count()

            inventory_count = InventoryRecord.objects.filter(
                inventory_time__gte=current_date,
                inventory_time__lt=next_date
            ).count()

            diff_count = InventoryRecord.objects.filter(
                inventory_time__gte=current_date,
                inventory_time__lt=next_date
            ).aggregate(total=Sum('diff_count'))['total'] or 0

            daily_data.append({
                'date': current_date.strftime('%Y-%m-%d'),
                'pickup_count': pickup_count,
                'return_count': return_count,
                'inventory_count': inventory_count,
                'diff_amount': abs(diff_count),
            })

        return Response(daily_data)

    @action(detail=False, methods=['get'], url_path='stats/abnormal-records')
    def abnormal_records(self, request):
        threshold = getattr(settings, 'DIFF_THRESHOLD', 5)
        min_consecutive = int(request.query_params.get('min_consecutive', 3))

        high_diff_records = InventoryRecord.objects.filter(
            diff_count__gt=threshold
        ) | InventoryRecord.objects.filter(
            diff_count__lt=-threshold
        )
        high_diff_records = high_diff_records.select_related('tray').order_by('-inventory_time')[:20]

        high_diff_data = InventoryRecordSerializer(high_diff_records, many=True).data

        late_returns = self._get_late_returns()

        consecutive_diff_persons = self._get_consecutive_diff_persons(min_consecutive)

        missing_conclusion = InventoryRecord.objects.filter(
            confirm_status=ConfirmStatus.CONFIRMED,
            conclusion=''
        ).count()

        pending_confirm = InventoryRecord.objects.filter(
            confirm_status=ConfirmStatus.PENDING
        ).count()

        return Response({
            'high_diff_records': high_diff_data,
            'late_returns': late_returns,
            'consecutive_diff_persons': consecutive_diff_persons,
            'missing_conclusion_count': missing_conclusion,
            'pending_confirm_count': pending_confirm,
        })

    def _get_late_returns(self):
        records = TrayRecord.objects.filter(
            is_returned=True,
            return_time__isnull=False,
            receive_time__isnull=False
        ).select_related('tray').order_by('-return_time')[:50]

        late_returns = []
        for i, record in enumerate(records):
            if i == len(records) - 1:
                break
            next_record = records[i + 1]
            if next_record.session == record.session:
                continue
            duration = record.return_time - record.receive_time
            if duration > timedelta(hours=8):
                late_returns.append({
                    'tray_id': record.tray.id,
                    'tray_code': record.tray.tray_code,
                    'session': record.session,
                    'receiver': record.receiver,
                    'receive_time': record.receive_time,
                    'return_time': record.return_time,
                    'duration_hours': round(duration.total_seconds() / 3600, 2),
                })
                if len(late_returns) >= 10:
                    break

        return late_returns

    def _get_consecutive_diff_persons(self, min_count):
        from django.db.models import Case, When, IntegerField

        abs_diff_sum = Sum(
            Case(
                When(diff_count__gt=0, then=F('diff_count')),
                When(diff_count__lt=0, then=-F('diff_count')),
                default=0,
                output_field=IntegerField()
            )
        )

        persons = InventoryRecord.objects.filter(
            confirm_status=ConfirmStatus.CONFIRMED
        ).exclude(diff_count=0).values('tray__responsible_person').annotate(
            diff_times=Count('id'),
            total_diff=abs_diff_sum
        ).filter(diff_times__gte=min_count).order_by('-diff_times')

        result = []
        for p in persons:
            result.append({
                'responsible_person': p['tray__responsible_person'],
                'diff_times': p['diff_times'],
                'total_diff': p['total_diff'] or 0,
            })

        return result


class TrayRecordViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = TrayRecord.objects.all()
    serializer_class = TrayRecordSerializer
    filterset_class = TrayRecordFilter
    search_fields = ['tray__tray_code', 'session', 'receiver']
    ordering_fields = ['created_at', 'receive_time', 'return_time']


class InventoryRecordViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = InventoryRecord.objects.all()
    serializer_class = InventoryRecordSerializer
    filterset_class = InventoryRecordFilter
    search_fields = ['tray__tray_code', 'diff_description', 'conclusion', 'confirmer']
    ordering_fields = ['created_at', 'inventory_time', 'diff_count']


class AbnormalHandlingViewSet(viewsets.ModelViewSet):
    queryset = AbnormalHandling.objects.select_related('tray', 'inventory_record', 'tray_record').all()
    serializer_class = AbnormalHandlingSerializer
    filterset_class = AbnormalHandlingFilter
    search_fields = ['tray__tray_code', 'handler', 'description', 'measures', 'result']
    ordering_fields = ['created_at', 'updated_at', 'expected_completion_time']

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return AbnormalHandlingDetailSerializer
        if self.action == 'create':
            return AbnormalHandlingCreateSerializer
        if self.action == 'resolve':
            return AbnormalHandlingResolveSerializer
        if self.action == 'close':
            return AbnormalHandlingCloseSerializer
        return AbnormalHandlingSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            tray = Tray.objects.get(id=data['tray_id'])
        except Tray.DoesNotExist:
            return Response({'detail': '托盘不存在'}, status=status.HTTP_404_NOT_FOUND)

        if tray.status not in [TrayStatus.OBSERVING, TrayStatus.PENDING_CONFIRM, TrayStatus.PENDING_COUNT]:
            return Response(
                {'detail': f'当前托盘状态为{tray.get_status_display()}，无需登记异常处理单'},
                status=status.HTTP_400_BAD_REQUEST
            )

        source = data.get('source', AbnormalSource.INVENTORY_DIFF)

        if source == AbnormalSource.INVENTORY_DIFF:
            if not data.get('inventory_record_id'):
                return Response(
                    {'detail': '异常来源为"清点差异"时必须指定关联的清点记录'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if source == AbnormalSource.OBSERVING_STATUS:
            if tray.status != TrayStatus.OBSERVING:
                return Response(
                    {'detail': '异常来源为"观察状态"时托盘必须处于观察中状态'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        inventory_record = None
        if 'inventory_record_id' in data and data.get('inventory_record_id'):
            try:
                inventory_record = InventoryRecord.objects.get(id=data['inventory_record_id'], tray=tray)
            except InventoryRecord.DoesNotExist:
                return Response({'detail': '清点记录不存在或不属于该托盘'}, status=status.HTTP_400_BAD_REQUEST)

            if source == AbnormalSource.INVENTORY_DIFF and inventory_record.diff_count == 0:
                return Response(
                    {'detail': '该清点记录无数量差异，不能以"清点差异"来源登记异常处理单'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        tray_record = None
        if 'tray_record_id' in data and data.get('tray_record_id'):
            try:
                tray_record = TrayRecord.objects.get(id=data['tray_record_id'], tray=tray)
            except TrayRecord.DoesNotExist:
                return Response({'detail': '领还记录不存在或不属于该托盘'}, status=status.HTTP_400_BAD_REQUEST)

        abnormal = AbnormalHandling.objects.create(
            tray=tray,
            inventory_record=inventory_record,
            tray_record=tray_record,
            source=data.get('source', AbnormalSource.INVENTORY_DIFF),
            handler=data['handler'],
            measures=data.get('measures', ''),
            expected_completion_time=data.get('expected_completion_time'),
            description=data.get('description', ''),
            status=AbnormalStatus.PENDING,
        )

        return Response(
            AbnormalHandlingDetailSerializer(abnormal).data,
            status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=['post'], serializer_class=AbnormalHandlingResolveSerializer)
    def resolve(self, request, pk=None):
        abnormal = self.get_object()

        if abnormal.status not in [AbnormalStatus.PENDING, AbnormalStatus.PROCESSING]:
            return Response(
                {'detail': f'当前状态为{abnormal.get_status_display()}，不能处理'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        abnormal.status = AbnormalStatus.RESOLVED
        abnormal.result = data['result']
        if data.get('measures'):
            abnormal.measures = data['measures']
        abnormal.resolved_at = timezone.now()
        abnormal.save()

        if abnormal.inventory_record and abnormal.inventory_record.confirm_status == ConfirmStatus.PENDING:
            abnormal.inventory_record.confirm_status = ConfirmStatus.CONFIRMED
            abnormal.inventory_record.confirmer = abnormal.handler
            abnormal.inventory_record.confirm_time = timezone.now()
            abnormal.inventory_record.conclusion = data['result']
            abnormal.inventory_record.save()

        tray = abnormal.tray
        if tray.status == TrayStatus.OBSERVING:
            pending_abnormals = AbnormalHandling.objects.filter(
                tray=tray,
                status__in=[AbnormalStatus.PENDING, AbnormalStatus.PROCESSING]
            ).exclude(id=abnormal.id).count()

            pending_confirms = InventoryRecord.objects.filter(
                tray=tray,
                confirm_status=ConfirmStatus.PENDING
            ).count()

            if pending_abnormals == 0 and pending_confirms == 0:
                tray.status = TrayStatus.AVAILABLE
                tray.save()

        return Response({
            'abnormal': AbnormalHandlingDetailSerializer(abnormal).data,
            'tray': TraySerializer(tray).data,
        })

    @action(detail=True, methods=['post'], serializer_class=AbnormalHandlingCloseSerializer)
    def close(self, request, pk=None):
        abnormal = self.get_object()

        if abnormal.status != AbnormalStatus.RESOLVED:
            return Response(
                {'detail': f'当前状态为{abnormal.get_status_display()}，只有已处理状态才能关闭'},
                status=status.HTTP_400_BAD_REQUEST
            )

        abnormal.status = AbnormalStatus.CLOSED
        abnormal.closed_at = timezone.now()
        abnormal.save()

        return Response(AbnormalHandlingDetailSerializer(abnormal).data)

    @action(detail=True, methods=['post'])
    def start_processing(self, request, pk=None):
        abnormal = self.get_object()

        if abnormal.status != AbnormalStatus.PENDING:
            return Response(
                {'detail': f'当前状态为{abnormal.get_status_display()}，只有待处理状态才能开始处理'},
                status=status.HTTP_400_BAD_REQUEST
            )

        abnormal.status = AbnormalStatus.PROCESSING
        abnormal.save()

        return Response(AbnormalHandlingSerializer(abnormal).data)

    @action(detail=False, methods=['get'], url_path='stats/overview')
    def stats_overview(self, request):
        pending_count = AbnormalHandling.objects.filter(
            status__in=[AbnormalStatus.PENDING, AbnormalStatus.PROCESSING]
        ).count()

        resolved_count = AbnormalHandling.objects.filter(
            status__in=[AbnormalStatus.RESOLVED, AbnormalStatus.CLOSED]
        ).count()

        closed_count = AbnormalHandling.objects.filter(
            status=AbnormalStatus.CLOSED
        ).count()

        area_distribution = AbnormalHandling.objects.filter(
            status__in=[AbnormalStatus.PENDING, AbnormalStatus.PROCESSING]
        ).values('tray__area').annotate(
            count=Count('id')
        ).order_by('-count')

        overdue_count = AbnormalHandling.objects.filter(
            status__in=[AbnormalStatus.PENDING, AbnormalStatus.PROCESSING],
            expected_completion_time__lt=timezone.now()
        ).count()

        source_distribution = AbnormalHandling.objects.values('source').annotate(
            count=Count('id')
        ).order_by('-count')

        return Response({
            'pending_count': pending_count,
            'resolved_count': resolved_count,
            'closed_count': closed_count,
            'overdue_count': overdue_count,
            'area_distribution': list(area_distribution),
            'source_distribution': list(source_distribution),
        })
