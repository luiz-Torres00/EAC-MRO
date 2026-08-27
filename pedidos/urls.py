from django.urls import path
from .views import (
    PedidoListCreateView, PedidoDetailView,
    AprovarPedidoView, RecusarPedidoView,
    DevolverPedidoView, ConfirmarDevolucaoView, EstenderPedidoView,
    AbrirOcorrenciaView, CobrarDevolucaoView,
    RelatorioXlsxView,
)

urlpatterns = [
    path('',                        PedidoListCreateView.as_view(),    name='pedidos'),
    path('relatorio/',              RelatorioXlsxView.as_view(),       name='pedido-relatorio'),
    path('<int:pk>/',               PedidoDetailView.as_view(),        name='pedido-detalhe'),
    path('<int:pk>/aprovar/',       AprovarPedidoView.as_view(),       name='pedido-aprovar'),
    path('<int:pk>/recusar/',       RecusarPedidoView.as_view(),       name='pedido-recusar'),
    path('<int:pk>/devolver/',      DevolverPedidoView.as_view(),      name='pedido-devolver'),
    path('<int:pk>/confirmar-devolucao/', ConfirmarDevolucaoView.as_view(), name='pedido-confirmar-devolucao'),
    path('<int:pk>/estender/',      EstenderPedidoView.as_view(),      name='pedido-estender'),
    path('<int:pk>/ocorrencia/',    AbrirOcorrenciaView.as_view(),     name='pedido-ocorrencia'),
    path('<int:pk>/cobrar/',        CobrarDevolucaoView.as_view(),     name='pedido-cobrar'),
]