from datetime import timedelta
from django.db import models
from django.db.models import Count, Sum, Avg, Q, F, ExpressionWrapper, IntegerField, Case, When
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
    AbnormalHandlingCloseSerializer,
    ReviewDiffDetailSerializer, ReviewAbnormalListSerializer,
    ReviewTrayStatSerializer, ReviewAreaStatSerializer,
    ReviewPersonStatSerializer, ReviewSessionStatSerializer,
    TrayTrajectorySerializer, TrajectoryEventSerializer
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
        elif inventory_record and inventory_record.tray_record:
            tray_record = inventory_record.tray_record

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
        if tray.status in [TrayStatus.OBSERVING, TrayStatus.PENDING_CONFIRM]:
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


class ReviewViewSet(viewsets.ViewSet):

    def _apply_time_filters(self, queryset, time_field, request):
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        if start_date:
            queryset = queryset.filter(**{f'{time_field}__gte': start_date})
        if end_date:
            queryset = queryset.filter(**{f'{time_field}__lte': end_date + ' 23:59:59'})
        return queryset

    def _apply_common_filters(self, queryset, request, tray_prefix='tray__', record_prefix='tray_record__'):
        tray_code = request.query_params.get('tray_code')
        area = request.query_params.get('area')
        responsible_person = request.query_params.get('responsible_person')
        session = request.query_params.get('session')

        if tray_code:
            queryset = queryset.filter(**{f'{tray_prefix}tray_code__icontains': tray_code})
        if area:
            queryset = queryset.filter(**{f'{tray_prefix}area__icontains': area})
        if responsible_person:
            queryset = queryset.filter(**{f'{tray_prefix}responsible_person__icontains': responsible_person})
        if session:
            queryset = queryset.filter(**{f'{record_prefix}session__icontains': session})

        return queryset

    @action(detail=False, methods=['get'], url_path='overview')
    def overview(self, request):
        abnormals = AbnormalHandling.objects.select_related('tray', 'tray_record', 'inventory_record').all()
        abnormals = self._apply_time_filters(abnormals, 'created_at', request)
        abnormals = self._apply_common_filters(abnormals, request)

        diff_records = InventoryRecord.objects.select_related('tray', 'tray_record').exclude(diff_count=0)
        diff_records = self._apply_time_filters(diff_records, 'inventory_time', request)
        diff_records = self._apply_common_filters(diff_records, request)

        total_abnormal = abnormals.count()
        pending_abnormal = abnormals.filter(status=AbnormalStatus.PENDING).count()
        processing_abnormal = abnormals.filter(status=AbnormalStatus.PROCESSING).count()
        resolved_abnormal = abnormals.filter(status=AbnormalStatus.RESOLVED).count()
        closed_abnormal = abnormals.filter(status=AbnormalStatus.CLOSED).count()

        now = timezone.now()
        overdue_abnormal = abnormals.filter(
            status__in=[AbnormalStatus.PENDING, AbnormalStatus.PROCESSING],
            expected_completion_time__isnull=False,
            expected_completion_time__lt=now
        ).count()

        total_diff_amount = diff_records.aggregate(
            total=Sum(
                Case(
                    When(diff_count__gt=0, then=F('diff_count')),
                    When(diff_count__lt=0, then=-F('diff_count')),
                    default=0,
                    output_field=IntegerField()
                )
            )
        )['total'] or 0

        diff_record_count = diff_records.count()

        source_distribution = list(
            abnormals.values('source').annotate(count=Count('id')).order_by('-count')
        )
        for item in source_distribution:
            item['source_display'] = AbnormalSource(item['source']).label

        status_distribution = [
            {'status': AbnormalStatus.PENDING, 'status_display': '待处理', 'count': pending_abnormal},
            {'status': AbnormalStatus.PROCESSING, 'status_display': '处理中', 'count': processing_abnormal},
            {'status': AbnormalStatus.RESOLVED, 'status_display': '已处理', 'count': resolved_abnormal},
            {'status': AbnormalStatus.CLOSED, 'status_display': '已关闭', 'count': closed_abnormal},
        ]

        return Response({
            'time_range': {
                'start_date': request.query_params.get('start_date'),
                'end_date': request.query_params.get('end_date'),
            },
            'filters': {
                'tray_code': request.query_params.get('tray_code'),
                'area': request.query_params.get('area'),
                'responsible_person': request.query_params.get('responsible_person'),
                'session': request.query_params.get('session'),
            },
            'abnormal_stats': {
                'total': total_abnormal,
                'pending': pending_abnormal,
                'processing': processing_abnormal,
                'resolved': resolved_abnormal,
                'closed': closed_abnormal,
                'overdue': overdue_abnormal,
                'resolution_rate': round(
                    (resolved_abnormal + closed_abnormal) / total_abnormal * 100, 2
                ) if total_abnormal > 0 else 0,
            },
            'diff_stats': {
                'record_count': diff_record_count,
                'total_amount': total_diff_amount,
                'avg_amount': round(total_diff_amount / diff_record_count, 2) if diff_record_count > 0 else 0,
            },
            'source_distribution': source_distribution,
            'status_distribution': status_distribution,
        })

    @action(detail=False, methods=['get'], url_path='diff-details')
    def diff_details(self, request):
        queryset = InventoryRecord.objects.select_related(
            'tray', 'tray_record'
        ).prefetch_related(
            'abnormal_handlings'
        ).exclude(diff_count=0)

        queryset = self._apply_time_filters(queryset, 'inventory_time', request)
        queryset = self._apply_common_filters(queryset, request)

        confirm_status = request.query_params.get('confirm_status')
        has_abnormal = request.query_params.get('has_abnormal')
        min_abs_diff = request.query_params.get('min_abs_diff')

        if confirm_status:
            queryset = queryset.filter(confirm_status=confirm_status)
        if has_abnormal == 'true':
            queryset = queryset.filter(abnormal_handlings__isnull=False)
        elif has_abnormal == 'false':
            queryset = queryset.filter(abnormal_handlings__isnull=True)
        if min_abs_diff:
            min_abs_diff = int(min_abs_diff)
            queryset = queryset.filter(
                Q(diff_count__gte=min_abs_diff) | Q(diff_count__lte=-min_abs_diff)
            )

        queryset = queryset.order_by('-inventory_time')

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = ReviewDiffDetailSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = ReviewDiffDetailSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='abnormal-list')
    def abnormal_list(self, request):
        queryset = AbnormalHandling.objects.select_related(
            'tray', 'tray_record', 'inventory_record'
        ).all()

        queryset = self._apply_time_filters(queryset, 'created_at', request)
        queryset = self._apply_common_filters(queryset, request)

        status = request.query_params.get('status')
        source = request.query_params.get('source')
        is_overdue = request.query_params.get('is_overdue')
        handler = request.query_params.get('handler')

        if status:
            queryset = queryset.filter(status=status)
        if source:
            queryset = queryset.filter(source=source)
        if handler:
            queryset = queryset.filter(handler__icontains=handler)
        if is_overdue == 'true':
            queryset = queryset.filter(
                status__in=[AbnormalStatus.PENDING, AbnormalStatus.PROCESSING],
                expected_completion_time__isnull=False,
                expected_completion_time__lt=timezone.now()
            )
        elif is_overdue == 'false':
            queryset = queryset.filter(
                Q(status__in=[AbnormalStatus.RESOLVED, AbnormalStatus.CLOSED]) |
                Q(expected_completion_time__isnull=True) |
                Q(expected_completion_time__gte=timezone.now())
            )

        queryset = queryset.order_by('-created_at')

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = ReviewAbnormalListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = ReviewAbnormalListSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='stats/by-tray')
    def stats_by_tray(self, request):
        abnormals = AbnormalHandling.objects.select_related('tray').all()
        abnormals = self._apply_time_filters(abnormals, 'created_at', request)
        abnormals = self._apply_common_filters(abnormals, request)

        diff_records = InventoryRecord.objects.select_related('tray').exclude(diff_count=0)
        diff_records = self._apply_time_filters(diff_records, 'inventory_time', request)
        diff_records = self._apply_common_filters(diff_records, request)

        tray_abnormal_stats = {
            a['tray_id']: a for a in abnormals.values('tray_id').annotate(
                abnormal_total=Count('id'),
                abnormal_pending=Count('id', filter=Q(status=AbnormalStatus.PENDING)),
                abnormal_processing=Count('id', filter=Q(status=AbnormalStatus.PROCESSING)),
                abnormal_resolved=Count('id', filter=Q(status=AbnormalStatus.RESOLVED)),
                abnormal_closed=Count('id', filter=Q(status=AbnormalStatus.CLOSED)),
                abnormal_overdue=Count(
                    'id',
                    filter=Q(
                        status__in=[AbnormalStatus.PENDING, AbnormalStatus.PROCESSING],
                        expected_completion_time__isnull=False,
                        expected_completion_time__lt=timezone.now()
                    )
                ),
            )
        }

        tray_diff_stats = {
            d['tray_id']: d for d in diff_records.values('tray_id').annotate(
                diff_total_amount=Sum(
                    Case(
                        When(diff_count__gt=0, then=F('diff_count')),
                        When(diff_count__lt=0, then=-F('diff_count')),
                        default=0,
                        output_field=IntegerField()
                    )
                ),
                diff_record_count=Count('id'),
            )
        }

        tray_ids = set(tray_abnormal_stats.keys()) | set(tray_diff_stats.keys())
        trays = Tray.objects.filter(id__in=tray_ids)

        result = []
        for tray in trays:
            a_stat = tray_abnormal_stats.get(tray.id, {})
            d_stat = tray_diff_stats.get(tray.id, {})
            result.append({
                'tray_id': tray.id,
                'tray_code': tray.tray_code,
                'area': tray.area,
                'responsible_person': tray.responsible_person,
                'abnormal_total': a_stat.get('abnormal_total', 0),
                'abnormal_pending': a_stat.get('abnormal_pending', 0),
                'abnormal_processing': a_stat.get('abnormal_processing', 0),
                'abnormal_resolved': a_stat.get('abnormal_resolved', 0),
                'abnormal_closed': a_stat.get('abnormal_closed', 0),
                'abnormal_overdue': a_stat.get('abnormal_overdue', 0),
                'diff_total_amount': d_stat.get('diff_total_amount', 0) or 0,
                'diff_record_count': d_stat.get('diff_record_count', 0),
            })

        result.sort(key=lambda x: x['abnormal_total'] + x['diff_record_count'], reverse=True)

        top_n = request.query_params.get('top_n')
        if top_n:
            result = result[:int(top_n)]

        serializer = ReviewTrayStatSerializer(result, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='stats/by-area')
    def stats_by_area(self, request):
        abnormals = AbnormalHandling.objects.select_related('tray').all()
        abnormals = self._apply_time_filters(abnormals, 'created_at', request)
        abnormals = self._apply_common_filters(abnormals, request)

        diff_records = InventoryRecord.objects.select_related('tray').exclude(diff_count=0)
        diff_records = self._apply_time_filters(diff_records, 'inventory_time', request)
        diff_records = self._apply_common_filters(diff_records, request)

        area_abnormal_stats = {
            a['tray__area']: a for a in abnormals.values('tray__area').annotate(
                abnormal_total=Count('id'),
                abnormal_pending=Count('id', filter=Q(status=AbnormalStatus.PENDING)),
                abnormal_processing=Count('id', filter=Q(status=AbnormalStatus.PROCESSING)),
                abnormal_resolved=Count('id', filter=Q(status=AbnormalStatus.RESOLVED)),
                abnormal_closed=Count('id', filter=Q(status=AbnormalStatus.CLOSED)),
                abnormal_overdue=Count(
                    'id',
                    filter=Q(
                        status__in=[AbnormalStatus.PENDING, AbnormalStatus.PROCESSING],
                        expected_completion_time__isnull=False,
                        expected_completion_time__lt=timezone.now()
                    )
                ),
            )
        }

        area_diff_stats = {
            d['tray__area']: d for d in diff_records.values('tray__area').annotate(
                diff_total_amount=Sum(
                    Case(
                        When(diff_count__gt=0, then=F('diff_count')),
                        When(diff_count__lt=0, then=-F('diff_count')),
                        default=0,
                        output_field=IntegerField()
                    )
                ),
            )
        }

        area_tray_counts = {
            t['area']: t['count'] for t in Tray.objects.values('area').annotate(count=Count('id'))
        }

        area_names = set(area_abnormal_stats.keys()) | set(area_diff_stats.keys())

        result = []
        for area in area_names:
            a_stat = area_abnormal_stats.get(area, {})
            d_stat = area_diff_stats.get(area, {})
            result.append({
                'area': area,
                'tray_count': area_tray_counts.get(area, 0),
                'abnormal_total': a_stat.get('abnormal_total', 0),
                'abnormal_pending': a_stat.get('abnormal_pending', 0),
                'abnormal_processing': a_stat.get('abnormal_processing', 0),
                'abnormal_resolved': a_stat.get('abnormal_resolved', 0),
                'abnormal_closed': a_stat.get('abnormal_closed', 0),
                'abnormal_overdue': a_stat.get('abnormal_overdue', 0),
                'diff_total_amount': d_stat.get('diff_total_amount', 0) or 0,
            })

        result.sort(key=lambda x: x['abnormal_total'], reverse=True)

        serializer = ReviewAreaStatSerializer(result, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='stats/by-person')
    def stats_by_person(self, request):
        abnormals = AbnormalHandling.objects.select_related('tray').all()
        abnormals = self._apply_time_filters(abnormals, 'created_at', request)
        abnormals = self._apply_common_filters(abnormals, request)

        diff_records = InventoryRecord.objects.select_related('tray').exclude(diff_count=0)
        diff_records = self._apply_time_filters(diff_records, 'inventory_time', request)
        diff_records = self._apply_common_filters(diff_records, request)

        person_abnormal_stats = {
            a['tray__responsible_person']: a for a in abnormals.values('tray__responsible_person').annotate(
                abnormal_total=Count('id'),
                abnormal_pending=Count('id', filter=Q(status=AbnormalStatus.PENDING)),
                abnormal_processing=Count('id', filter=Q(status=AbnormalStatus.PROCESSING)),
                abnormal_resolved=Count('id', filter=Q(status=AbnormalStatus.RESOLVED)),
                abnormal_closed=Count('id', filter=Q(status=AbnormalStatus.CLOSED)),
                abnormal_overdue=Count(
                    'id',
                    filter=Q(
                        status__in=[AbnormalStatus.PENDING, AbnormalStatus.PROCESSING],
                        expected_completion_time__isnull=False,
                        expected_completion_time__lt=timezone.now()
                    )
                ),
            )
        }

        person_diff_stats = {
            d['tray__responsible_person']: d for d in diff_records.values('tray__responsible_person').annotate(
                diff_total_amount=Sum(
                    Case(
                        When(diff_count__gt=0, then=F('diff_count')),
                        When(diff_count__lt=0, then=-F('diff_count')),
                        default=0,
                        output_field=IntegerField()
                    )
                ),
            )
        }

        person_tray_counts = {
            t['responsible_person']: t['count'] for t in Tray.objects.values('responsible_person').annotate(count=Count('id'))
        }

        person_names = set(person_abnormal_stats.keys()) | set(person_diff_stats.keys())

        result = []
        for person in person_names:
            a_stat = person_abnormal_stats.get(person, {})
            d_stat = person_diff_stats.get(person, {})
            result.append({
                'responsible_person': person,
                'tray_count': person_tray_counts.get(person, 0),
                'abnormal_total': a_stat.get('abnormal_total', 0),
                'abnormal_pending': a_stat.get('abnormal_pending', 0),
                'abnormal_processing': a_stat.get('abnormal_processing', 0),
                'abnormal_resolved': a_stat.get('abnormal_resolved', 0),
                'abnormal_closed': a_stat.get('abnormal_closed', 0),
                'abnormal_overdue': a_stat.get('abnormal_overdue', 0),
                'diff_total_amount': d_stat.get('diff_total_amount', 0) or 0,
            })

        result.sort(key=lambda x: x['abnormal_total'], reverse=True)

        serializer = ReviewPersonStatSerializer(result, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='stats/by-session')
    def stats_by_session(self, request):
        records = TrayRecord.objects.all()
        records = self._apply_time_filters(records, 'receive_time', request)
        records = self._apply_common_filters(records, request, record_prefix='')

        abnormals = AbnormalHandling.objects.select_related('tray_record').all()
        abnormals = self._apply_time_filters(abnormals, 'created_at', request)
        abnormals = self._apply_common_filters(abnormals, request)

        diff_records = InventoryRecord.objects.select_related('tray_record').exclude(diff_count=0)
        diff_records = self._apply_time_filters(diff_records, 'inventory_time', request)
        diff_records = self._apply_common_filters(diff_records, request)

        session_record_stats = {
            s['session']: s['count'] for s in records.values('session').annotate(count=Count('id'))
        }

        session_abnormal_stats = {
            a['tray_record__session']: a for a in abnormals.filter(
                tray_record__session__isnull=False
            ).values('tray_record__session').annotate(
                abnormal_total=Count('id'),
                abnormal_pending=Count('id', filter=Q(status=AbnormalStatus.PENDING)),
            )
        }

        session_diff_stats = {
            d['tray_record__session']: d for d in diff_records.filter(
                tray_record__session__isnull=False
            ).values('tray_record__session').annotate(
                diff_total_amount=Sum(
                    Case(
                        When(diff_count__gt=0, then=F('diff_count')),
                        When(diff_count__lt=0, then=-F('diff_count')),
                        default=0,
                        output_field=IntegerField()
                    )
                ),
            )
        }

        session_names = set(session_record_stats.keys()) | set(session_abnormal_stats.keys()) | set(session_diff_stats.keys())

        result = []
        for session in session_names:
            a_stat = session_abnormal_stats.get(session, {})
            d_stat = session_diff_stats.get(session, {})
            result.append({
                'session': session,
                'record_count': session_record_stats.get(session, 0),
                'abnormal_total': a_stat.get('abnormal_total', 0),
                'abnormal_pending': a_stat.get('abnormal_pending', 0),
                'diff_total_amount': d_stat.get('diff_total_amount', 0) or 0,
            })

        result.sort(key=lambda x: x['abnormal_total'], reverse=True)

        serializer = ReviewSessionStatSerializer(result, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='pending-items')
    def pending_items(self, request):
        now = timezone.now()

        pending_abnormals = AbnormalHandling.objects.select_related('tray', 'tray_record').filter(
            status__in=[AbnormalStatus.PENDING, AbnormalStatus.PROCESSING]
        ).order_by('expected_completion_time')

        area = request.query_params.get('area')
        responsible_person = request.query_params.get('responsible_person')
        is_overdue = request.query_params.get('is_overdue')

        if area:
            pending_abnormals = pending_abnormals.filter(tray__area__icontains=area)
        if responsible_person:
            pending_abnormals = pending_abnormals.filter(tray__responsible_person__icontains=responsible_person)
        if is_overdue == 'true':
            pending_abnormals = pending_abnormals.filter(
                expected_completion_time__isnull=False,
                expected_completion_time__lt=now
            )
        elif is_overdue == 'false':
            pending_abnormals = pending_abnormals.filter(
                Q(expected_completion_time__isnull=True) |
                Q(expected_completion_time__gte=now)
            )

        pending_confirms = InventoryRecord.objects.select_related('tray', 'tray_record').filter(
            confirm_status=ConfirmStatus.PENDING
        )
        if area:
            pending_confirms = pending_confirms.filter(tray__area__icontains=area)
        if responsible_person:
            pending_confirms = pending_confirms.filter(tray__responsible_person__icontains=responsible_person)

        pending_confirms = pending_confirms.order_by('inventory_time')

        return Response({
            'pending_abnormal_count': pending_abnormals.count(),
            'pending_confirm_count': pending_confirms.count(),
            'overdue_abnormal_count': pending_abnormals.filter(
                expected_completion_time__isnull=False,
                expected_completion_time__lt=now
            ).count(),
            'pending_abnormals': ReviewAbnormalListSerializer(pending_abnormals[:50], many=True).data,
            'pending_confirms': ReviewDiffDetailSerializer(pending_confirms[:50], many=True).data,
        })

    @action(detail=True, methods=['get'], url_path='trajectory')
    def trajectory(self, request, pk=None):
        try:
            tray = Tray.objects.get(pk=pk)
        except Tray.DoesNotExist:
            return Response({'detail': '托盘不存在'}, status=status.HTTP_404_NOT_FOUND)

        events = []

        records = TrayRecord.objects.filter(tray=tray).order_by('receive_time')
        for record in records:
            if record.receive_time:
                events.append({
                    'event_type': 'pickup',
                    'event_type_display': '托盘领取',
                    'event_time': record.receive_time,
                    'operator': record.receiver,
                    'description': f'领取托盘，场次：{record.session}',
                    'detail': {
                        'record_id': record.id,
                        'session': record.session,
                        'receiver': record.receiver,
                    }
                })
            if record.return_time:
                events.append({
                    'event_type': 'return',
                    'event_type_display': '托盘归还',
                    'event_time': record.return_time,
                    'operator': record.receiver,
                    'description': f'归还托盘，场次：{record.session}',
                    'detail': {
                        'record_id': record.id,
                        'session': record.session,
                        'receiver': record.receiver,
                    }
                })

        inventories = InventoryRecord.objects.filter(tray=tray).order_by('inventory_time')
        for inv in inventories:
            events.append({
                'event_type': 'inventory',
                'event_type_display': '托盘清点',
                'event_time': inv.inventory_time,
                'operator': None,
                'description': f'清点完成，实际{inv.actual_count}，应存{inv.expected_count}，差异{inv.diff_count:+d}',
                'detail': {
                    'inventory_id': inv.id,
                    'actual_count': inv.actual_count,
                    'expected_count': inv.expected_count,
                    'diff_count': inv.diff_count,
                    'diff_description': inv.diff_description,
                    'confirm_status': inv.confirm_status,
                    'confirm_status_display': inv.get_confirm_status_display(),
                    'confirmer': inv.confirmer,
                    'confirm_time': inv.confirm_time.isoformat() if inv.confirm_time else None,
                    'conclusion': inv.conclusion,
                }
            })

        abnormals = AbnormalHandling.objects.filter(tray=tray).order_by('created_at')
        for abn in abnormals:
            events.append({
                'event_type': 'abnormal_register',
                'event_type_display': '异常登记',
                'event_time': abn.created_at,
                'operator': abn.handler,
                'description': f'登记异常（{abn.get_source_display()}）：{abn.description}',
                'detail': {
                    'abnormal_id': abn.id,
                    'source': abn.source,
                    'source_display': abn.get_source_display(),
                    'description': abn.description,
                    'handler': abn.handler,
                    'measures': abn.measures,
                    'expected_completion_time': abn.expected_completion_time.isoformat() if abn.expected_completion_time else None,
                    'status': abn.status,
                    'status_display': abn.get_status_display(),
                }
            })
            if abn.resolved_at:
                events.append({
                    'event_type': 'abnormal_resolve',
                    'event_type_display': '异常处理完成',
                    'event_time': abn.resolved_at,
                    'operator': abn.handler,
                    'description': f'异常处理完成：{abn.result}',
                    'detail': {
                        'abnormal_id': abn.id,
                        'result': abn.result,
                        'handler': abn.handler,
                    }
                })
            if abn.closed_at:
                events.append({
                    'event_type': 'abnormal_close',
                    'event_type_display': '异常关闭归档',
                    'event_time': abn.closed_at,
                    'operator': None,
                    'description': '异常单已关闭归档',
                    'detail': {
                        'abnormal_id': abn.id,
                    }
                })

        events.sort(key=lambda x: x['event_time'])

        pending_abnormal_count = abnormals.filter(
            status__in=[AbnormalStatus.PENDING, AbnormalStatus.PROCESSING]
        ).count()

        data = {
            'tray_id': tray.id,
            'tray_code': tray.tray_code,
            'area': tray.area,
            'responsible_person': tray.responsible_person,
            'current_status': tray.status,
            'current_status_display': tray.get_status_display(),
            'total_events': len(events),
            'total_abnormal': abnormals.count(),
            'pending_abnormal': pending_abnormal_count,
            'events': events,
        }

        serializer = TrayTrajectorySerializer(data)
        return Response(serializer.data)

    @property
    def paginator(self):
        from rest_framework.pagination import PageNumberPagination
        if not hasattr(self, '_paginator'):
            self._paginator = PageNumberPagination()
            self._paginator.page_size = 20
        return self._paginator

    def paginate_queryset(self, queryset):
        page_size = self.request.query_params.get('page_size')
        if page_size:
            try:
                self.paginator.page_size = int(page_size)
            except (ValueError, TypeError):
                pass
        return self.paginator.paginate_queryset(queryset, self.request, view=self)

    def get_paginated_response(self, data):
        return self.paginator.get_paginated_response(data)
