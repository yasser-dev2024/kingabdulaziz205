from django.urls import path
from .views import inbox, new_thread, thread_detail, reply_thread, close_thread

app_name = "messaging"

urlpatterns = [
    path('', inbox, name='inbox'),
    path('new/', new_thread, name='new'),
    path('<int:pk>/', thread_detail, name='detail'),
    path('<int:pk>/reply/', reply_thread, name='reply'),
    path('<int:pk>/close/', close_thread, name='close'),
]
