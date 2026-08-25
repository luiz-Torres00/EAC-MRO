from rest_framework import generics, permissions
from .models import Produto
from .serializers import ProdutoSerializer


class ProdutoListCreateView(generics.ListCreateAPIView):
    serializer_class   = ProdutoSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Produto.objects.filter(ativo=True)


class ProdutoDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class   = ProdutoSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset           = Produto.objects.all()
