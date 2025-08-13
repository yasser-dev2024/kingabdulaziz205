from django.urls import path
from .views import reports_view

app_name = "workflow"

urlpatterns = [
    path('reports/', reports_view, name='reports'),
]
