from django.urls import path
from .views import ProdutoListCreateView, ProdutoDetailView

urlpatterns = [
    path('',         ProdutoListCreateView.as_view(), name='produtos'),
    path('<int:pk>/',ProdutoDetailView.as_view(),      name='produto-detalhe'),
]
