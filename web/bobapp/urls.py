from django.urls import path
from django.views.generic import TemplateView

import web.bobapp.views
from . import views

urlpatterns = [
    path('', web.bobapp.views.index, name='home'),
]
