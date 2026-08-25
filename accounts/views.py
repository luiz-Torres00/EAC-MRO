from rest_framework import generics, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from django.utils import timezone
from django.contrib.auth.hashers import check_password

from .models import Usuario, SolicitacaoAcesso, Cargo
from .serializers import (
    UsuarioSerializer, UsuarioCreateSerializer,
    SolicitacaoSerializer, MeuTokenSerializer, CargoSerializer,
)


class LoginView(TokenObtainPairView):
    """POST /api/auth/login/ — retorna access + refresh token com dados do usuário."""
    serializer_class = MeuTokenSerializer

    def post(self, request, *args, **kwargs):
        # Só permite login se aprovado
        email = request.data.get('email', '').lower()
        try:
            user = Usuario.objects.get(email=email)
            if not user.is_approved:
                return Response(
                    {'detail': 'Conta ainda não aprovada por um administrador.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
        except Usuario.DoesNotExist:
            pass  # deixa o JWT retornar 401 padrão
        return super().post(request, *args, **kwargs)


class MeView(APIView):
    """GET /api/auth/me/ — dados do usuário autenticado."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(UsuarioSerializer(request.user).data)

    def patch(self, request):
        """Atualiza nome, cargo, setor, matricula."""
        allowed = ['nome', 'sobrenome', 'cargo', 'setor', 'matricula']
        data    = {k: v for k, v in request.data.items() if k in allowed}
        serializer = UsuarioSerializer(request.user, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class SolicitarAcessoView(generics.CreateAPIView):
    """POST /api/auth/solicitar/ — qualquer um pode pedir acesso."""
    permission_classes  = [permissions.AllowAny]
    serializer_class    = SolicitacaoSerializer


class SolicitacoesListView(generics.ListAPIView):
    """GET /api/auth/solicitacoes/ — lista para admins."""
    permission_classes = [permissions.IsAdminUser]
    serializer_class   = SolicitacaoSerializer
    queryset           = SolicitacaoAcesso.objects.filter(status='pendente').order_by('-criado_em')


class AprovarSolicitacaoView(APIView):
    """POST /api/auth/solicitacoes/<id>/aprovar/ — cria o usuário e aprova."""
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk):
        try:
            solic = SolicitacaoAcesso.objects.get(pk=pk, status='pendente')
        except SolicitacaoAcesso.DoesNotExist:
            return Response({'detail': 'Solicitação não encontrada.'}, status=404)

        # Cria o usuário
        user = Usuario.objects.create(
            email       = solic.email,
            nome        = solic.nome,
            sobrenome   = solic.sobrenome,
            matricula   = solic.matricula,
            setor       = solic.setor,
            cargo       = solic.cargo,
            is_approved = True,
        )
        user.password   = solic.senha_hash   # já está hasheada
        user.save()

        solic.status      = 'aprovado'
        solic.avaliado_em = timezone.now()
        solic.avaliado_por= request.user
        solic.save()

        return Response(UsuarioSerializer(user).data, status=201)


class RecusarSolicitacaoView(APIView):
    """POST /api/auth/solicitacoes/<id>/recusar/"""
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk):
        try:
            solic = SolicitacaoAcesso.objects.get(pk=pk, status='pendente')
        except SolicitacaoAcesso.DoesNotExist:
            return Response({'detail': 'Solicitação não encontrada.'}, status=404)
        solic.status      = 'recusado'
        solic.avaliado_em = timezone.now()
        solic.avaliado_por= request.user
        solic.save()
        return Response({'detail': 'Recusado.'})


class UsuariosListView(generics.ListAPIView):
    """GET /api/auth/usuarios/ — lista usuários aprovados (para mencao widget)."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = UsuarioSerializer
    queryset           = Usuario.objects.filter(is_approved=True, is_active=True).order_by('nome')


class UsuarioDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /api/auth/usuarios/<id>/"""
    permission_classes = [permissions.IsAdminUser]
    serializer_class   = UsuarioSerializer
    queryset           = Usuario.objects.all()

    def patch(self, request, *args, **kwargs):
        """Admin pode atualizar is_approved e perms."""
        allowed = ['is_approved', 'is_staff', 'perms', 'cargo', 'setor']
        data    = {k: v for k, v in request.data.items() if k in allowed}
        instance = self.get_object()
        serializer = UsuarioSerializer(instance, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class AdminCriarUsuarioView(generics.CreateAPIView):
    """
    POST /api/auth/usuarios/criar/ — admin cria um usuário direto, já
    aprovado, sem passar pelo fluxo de solicitação de acesso.
    """
    permission_classes = [permissions.IsAdminUser]
    serializer_class   = UsuarioCreateSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UsuarioSerializer(user).data, status=201)


CARGOS_PADRAO = [
    ('Aux. Almoxarifado', False),
    ('Almoxarife',        False),
    ('Encarregado',       True),
    ('Supervisor',        True),
    ('Coordenador',       True),
    ('Gerente',           True),
    ('Gerente Geral',     True),
]


class CargoListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/auth/cargos/ — lista de cargos (qualquer usuário logado, usado
    pra popular o dropdown do formulário de usuário).
    POST /api/auth/cargos/ — cria um novo cargo (só admin).
    """
    serializer_class = CargoSerializer

    def get_queryset(self):
        # Semeia os cargos padrão na primeira vez que alguém acessa esta
        # tela, pra não depender de uma migração de dados separada.
        if not Cargo.objects.exists():
            Cargo.objects.bulk_create([
                Cargo(nome=nome, is_gestao=gestao) for nome, gestao in CARGOS_PADRAO
            ])
        return Cargo.objects.all()

    def get_permissions(self):
        if self.request.method == 'POST':
            return [permissions.IsAdminUser()]
        return [permissions.IsAuthenticated()]


class CargoDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /api/auth/cargos/<id>/ — só admin."""
    permission_classes = [permissions.IsAdminUser]
    serializer_class   = CargoSerializer
    queryset           = Cargo.objects.all()
