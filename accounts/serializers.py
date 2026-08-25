from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.hashers import make_password
from .models import Usuario, SolicitacaoAcesso, Cargo


class CargoSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Cargo
        fields = ['id', 'nome', 'is_gestao', 'criado_em']
        read_only_fields = ['id', 'criado_em']


class UsuarioSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Usuario
        fields = [
            'id', 'email', 'nome', 'sobrenome', 'matricula',
            'setor', 'cargo', 'is_staff', 'is_approved', 'perms', 'criado_em',
        ]
        read_only_fields = ['id', 'criado_em']


class UsuarioCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model  = Usuario
        fields = ['email', 'nome', 'sobrenome', 'matricula', 'setor', 'cargo', 'password', 'is_staff', 'perms']

    def create(self, validated_data):
        password = validated_data.pop('password')
        user     = Usuario(**validated_data)
        user.set_password(password)
        user.is_approved = True   # criado direto por um admin — já entra aprovado
        user.save()
        return user


class SolicitacaoSerializer(serializers.ModelSerializer):
    senha = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model  = SolicitacaoAcesso
        fields = ['id', 'nome', 'sobrenome', 'email', 'matricula', 'setor', 'cargo', 'senha', 'status', 'criado_em']
        read_only_fields = ['id', 'status', 'criado_em']

    def create(self, validated_data):
        senha = validated_data.pop('senha')
        validated_data['senha_hash'] = make_password(senha)
        return super().create(validated_data)


class MeuTokenSerializer(TokenObtainPairSerializer):
    """Adiciona dados do usuário ao token de acesso."""
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['nome']       = user.nome
        token['email']      = user.email
        token['setor']      = user.setor
        token['cargo']      = user.cargo
        token['is_staff']   = user.is_staff
        token['perms']      = user.perms
        return token
