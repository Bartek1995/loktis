"""
URL routing dla listing_analyzer.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import AnalyzeView, ValidateURLView, HistoryViewSet, ProvidersView

router = DefaultRouter()
router.register(r'history', HistoryViewSet, basename='history')

urlpatterns = [
    path('analyze/', AnalyzeView.as_view(), name='analyze'),
    path('validate-url/', ValidateURLView.as_view(), name='validate-url'),
    path('providers/', ProvidersView.as_view(), name='providers'),
    path('', include(router.urls)),
]
