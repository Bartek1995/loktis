"""
URL routing dla location_analysis.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    AnalyzeListingView, 
    AnalyzeLocationView, 
    ValidateURLView, 
    HistoryViewSet, 
    ProvidersView, 
    ProfilesView,
    ReportDetailView,
)

router = DefaultRouter()
router.register(r'history', HistoryViewSet, basename='history')

urlpatterns = [
    path('analyze/', AnalyzeListingView.as_view(), name='analyze'),
    path('analyze-location/', AnalyzeLocationView.as_view(), name='analyze-location'),
    path('validate-url/', ValidateURLView.as_view(), name='validate-url'),
    path('providers/', ProvidersView.as_view(), name='providers'),
    path('profiles/', ProfilesView.as_view(), name='profiles'),
    path('profiles/<str:profile_key>/', ProfilesView.as_view(), name='profile-detail'),
    path('report/<str:public_id>/', ReportDetailView.as_view(), name='report-detail'),
    path('', include(router.urls)),
]
