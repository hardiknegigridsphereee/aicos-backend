# finance/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from finance.views import FeeStructureViewSet, StudentFeeViewSet, FeeTransactionViewSet

router = DefaultRouter()
router.register(r'fee-structures', FeeStructureViewSet, basename='fee-structure')
router.register(r'student-fees', StudentFeeViewSet, basename='student-fee')
router.register(r'transactions', FeeTransactionViewSet, basename='fee-transaction')

urlpatterns = [
    path('', include(router.urls)),
]
