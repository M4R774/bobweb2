from django.shortcuts import render
from bobweb.web.bobapp.models import *


def index(request):
    chat = Chat.objects.get(id=-1001088846469)
    return render(request, 'home.html', {'chat': chat})
