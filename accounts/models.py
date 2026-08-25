from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class UsuarioManager(BaseUserManager):
    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError('E-mail obrigatório')
        email = self.normalize_email(email)
        user  = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault('is_staff',    True)
        extra.setdefault('is_superuser',True)
        extra.setdefault('is_approved', True)
        return self.create_user(email, password, **extra)


class Usuario(AbstractBaseUser, PermissionsMixin):
    SETOR_CHOICES = [
        ('MG1','MG1'), ('MG2','MG2'), ('MG3','MG3'), ('MG4','MG4'),
        ('Cenografia','Cenografia'), ('Arte','Arte'),
    ]
    CARGO_CHOICES = [
        ('Aux. Almoxarifado','Aux. Almoxarifado'),
        ('Almoxarife','Almoxarife'),
        ('Encarregado','Encarregado'),
        ('Supervisor','Supervisor'),
        ('Coordenador','Coordenador'),
        ('Gerente','Gerente'),
        ('Gerente Geral','Gerente Geral'),
    ]

    email       = models.EmailField(unique=True)
    nome        = models.CharField(max_length=100)
    sobrenome   = models.CharField(max_length=100, blank=True)
    matricula   = models.CharField(max_length=50, blank=True)
    setor       = models.CharField(max_length=20, choices=SETOR_CHOICES, blank=True)
    # Sem `choices` fixo: os cargos disponíveis agora são geridos dinamicamente
    # pelo modelo Cargo (tela Usuários & Permissões). O valor continua sendo
    # salvo como texto simples aqui, só validamos contra a lista na hora de
    # popular o dropdown no frontend.
    cargo       = models.CharField(max_length=50, blank=True)
    is_active   = models.BooleanField(default=True)
    is_staff    = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=False)  # Aprovado por admin
    criado_em   = models.DateTimeField(auto_now_add=True)

    # Permissões granulares (replicando o sistema Firebase)
    perms = models.JSONField(default=dict, blank=True)

    # Preenchido pelo script de migração — referência ao UID do Firebase Auth,
    # útil para conferência e para vincular dados históricos. Não é mais usado
    # para autenticação (isso agora é feito via email/senha no Django).
    firebase_uid = models.CharField(max_length=128, blank=True, null=True, db_index=True)

    objects = UsuarioManager()

    USERNAME_FIELD  = 'email'
    REQUIRED_FIELDS = ['nome']

    class Meta:
        verbose_name        = 'Usuário'
        verbose_name_plural = 'Usuários'

    def __str__(self):
        return f'{self.nome} <{self.email}>'

    def nome_completo(self):
        return f'{self.nome} {self.sobrenome}'.strip()


class Cargo(models.Model):
    """
    Cargos configuráveis pela tela de Usuários & Permissões — substitui a
    lista fixa que existia antes. `is_gestao` marca os cargos que devem
    receber notificação quando algo sai do armazém (MG) deles.
    """
    nome        = models.CharField(max_length=50, unique=True)
    is_gestao   = models.BooleanField(default=False)
    criado_em   = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Cargo'
        verbose_name_plural = 'Cargos'
        ordering             = ['nome']

    def __str__(self):
        return self.nome


class SolicitacaoAcesso(models.Model):
    """Pedido de acesso ao sistema — aguarda aprovação do admin."""
    STATUS = [
        ('pendente', 'Pendente'),
        ('aprovado', 'Aprovado'),
        ('recusado', 'Recusado'),
    ]
    nome        = models.CharField(max_length=100)
    sobrenome   = models.CharField(max_length=100, blank=True)
    email       = models.EmailField()
    matricula   = models.CharField(max_length=50, blank=True)
    senha_hash  = models.CharField(max_length=128)        # armazenada temporariamente
    setor       = models.CharField(max_length=20, blank=True)
    cargo       = models.CharField(max_length=50, blank=True)
    status      = models.CharField(max_length=10, choices=STATUS, default='pendente')
    criado_em   = models.DateTimeField(auto_now_add=True)
    avaliado_em = models.DateTimeField(null=True, blank=True)
    avaliado_por= models.ForeignKey(
        'accounts.Usuario', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='solicitacoes_avaliadas'
    )

    class Meta:
        verbose_name        = 'Solicitação de acesso'
        verbose_name_plural = 'Solicitações de acesso'
        ordering            = ['-criado_em']

    def __str__(self):
        return f'{self.nome} ({self.email}) — {self.status}'
