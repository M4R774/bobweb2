from django.shortcuts import render

from web.bobapp.models import Chat


def index(request):
    chat = Chat.objects.get(id=-1001088846469)
    return render(request, 'home.html', {'chat': chat})
