from rest_framework import serializers
from .models import Pedido
from accounts.serializers import UsuarioSerializer


class PedidoSerializer(serializers.ModelSerializer):
    solicitante_obj  = UsuarioSerializer(source='solicitante', read_only=True)
    concedente_obj   = UsuarioSerializer(source='concedente',  read_only=True)
    criado_por_obj   = UsuarioSerializer(source='criado_por',  read_only=True)
    solicitante_setor= serializers.SerializerMethodField()

    class Meta:
        model  = Pedido
        fields = '__all__'
        read_only_fields = ['id', 'codigo', 'criado_em', 'atualizado_em']

    def get_solicitante_setor(self, obj):
        return obj.solicitante.setor if obj.solicitante_id and obj.solicitante else ''


class PedidoCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Pedido
        exclude = ['codigo', 'criado_em', 'atualizado_em']

    def validate(self, attrs):
        # Regra de negócio, não só de UI: os dados que servem pro controle do
        # empréstimo são obrigatórios na criação — só o número do pedido é
        # livre. Validamos aqui pra não depender só do frontend.
        erros = {}
        if not attrs.get('solicitante'):
            erros['solicitante'] = 'Obrigatório.'
        if not attrs.get('concedente'):
            erros['concedente'] = 'Obrigatório.'
        if not attrs.get('mg_solicitante'):
            erros['mg_solicitante'] = 'Obrigatório.'
        if not (attrs.get('produto') or '').strip():
            erros['produto'] = 'Obrigatório.'
        if not attrs.get('inicio_iso'):
            erros['inicio_iso'] = 'Obrigatório.'
        if not attrs.get('dev_iso'):
            erros['dev_iso'] = 'Obrigatório.'
        if erros:
            raise serializers.ValidationError(erros)
        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        if request and not validated_data.get('criado_por'):
            validated_data['criado_por'] = request.user
        # Preenche campos de nome/email a partir dos FKs
        sol = validated_data.get('solicitante')
        con = validated_data.get('concedente')
        if sol:
            validated_data.setdefault('solicitante_nome',  sol.nome)
            validated_data.setdefault('solicitante_email', sol.email)
        if con:
            validated_data.setdefault('concedente_nome',  con.nome)
            validated_data.setdefault('concedente_email', con.email)
        return super().create(validated_data)
