from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', TemplateView.as_view(template_name='home.html'), name='home'),
    path('hlulhv1409/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('referrals/', include('referrals.urls')),
    path('workflow/', include('workflow.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
