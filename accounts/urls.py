from django.urls import path
from .views import (
    LoginView, MeView, SolicitarAcessoView,
    SolicitacoesListView, AprovarSolicitacaoView, RecusarSolicitacaoView,
    UsuariosListView, UsuarioDetailView, AdminCriarUsuarioView,
    CargoListCreateView, CargoDetailView,
)

urlpatterns = [
    path('login/',                          LoginView.as_view(),             name='login'),
    path('me/',                             MeView.as_view(),                name='me'),
    path('solicitar/',                      SolicitarAcessoView.as_view(),   name='solicitar'),
    path('solicitacoes/',                   SolicitacoesListView.as_view(),  name='solicitacoes'),
    path('solicitacoes/<int:pk>/aprovar/',  AprovarSolicitacaoView.as_view(),name='aprovar-solic'),
    path('solicitacoes/<int:pk>/recusar/',  RecusarSolicitacaoView.as_view(),name='recusar-solic'),
    path('usuarios/criar/',                 AdminCriarUsuarioView.as_view(), name='usuario-criar'),
    path('usuarios/',                       UsuariosListView.as_view(),      name='usuarios'),
    path('usuarios/<int:pk>/',              UsuarioDetailView.as_view(),     name='usuario-detalhe'),
    path('cargos/',                         CargoListCreateView.as_view(),   name='cargos'),
    path('cargos/<int:pk>/',                CargoDetailView.as_view(),       name='cargo-detalhe'),
]
