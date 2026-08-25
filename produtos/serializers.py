from rest_framework import serializers
from .models import Produto


class ProdutoSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Produto
        fields = ['id', 'nome', 'ativo', 'criado_em']
        read_only_fields = ['id', 'criado_em']
