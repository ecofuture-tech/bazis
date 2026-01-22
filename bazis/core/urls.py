from django.http.response import HttpResponse
from django.urls import path


app_name = 'bazis'


def heathcheck(request):
    """
    Handles the health check endpoint, returning an empty HTTP response to indicate
    that the service is up and running.

    Tags: RAG, EXPORT
    """
    return HttpResponse('')


urlpatterns = [
    path('healthcheck', heathcheck),
]
