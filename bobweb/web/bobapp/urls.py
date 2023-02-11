from django.urls import path
from django.views.generic import TemplateView

import bobweb.web.bobapp.views
from . import views

urlpatterns = [
    path('', bobweb.web.bobapp.views.index, name='home'),
]
