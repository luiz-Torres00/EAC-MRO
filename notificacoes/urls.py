from django.urls import path
from .views import NotificacaoListView, MarcarLidaView, MarcarTodasLidasView

urlpatterns = [
    path('',                   NotificacaoListView.as_view(),  name='notificacoes'),
    path('<int:pk>/lida/',     MarcarLidaView.as_view(),        name='notif-lida'),
    path('marcar-todas/',      MarcarTodasLidasView.as_view(),  name='notif-todas'),
]
