from django.urls import path
from .views import (
    list_referrals,
    create_referral,
    detail_referral,
    assign_referral,
    close_referral,
    reply_referral,  # جديد
)

app_name = "referrals"

urlpatterns = [
    path('', list_referrals, name='index'),
    path('new/', create_referral, name='new'),
    path('<int:pk>/', detail_referral, name='detail'),
    path('<int:pk>/assign/', assign_referral, name='assign'),
    path('<int:pk>/close/', close_referral, name='close'),
    path('<int:pk>/reply/', reply_referral, name='reply'),  # جديد
]
