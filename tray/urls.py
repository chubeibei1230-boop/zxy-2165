from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'trays', views.TrayViewSet)
router.register(r'records', views.TrayRecordViewSet)
router.register(r'inventories', views.InventoryRecordViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
