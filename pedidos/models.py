from django.db import models
from django.conf import settings


def gerar_codigo():
    """Gera código EAC-ANO-NNN único."""
    from django.utils import timezone
    ano  = timezone.now().year
    last = Pedido.objects.filter(codigo__startswith=f'EAC-{ano}-').count()
    return f'EAC-{ano}-{last + 1:03d}'


class Pedido(models.Model):
    STATUS_CHOICES = [
        ('pendente',             'Aguardando aprovação'),
        ('aprovado',             'Aprovado / Liberado'),
        ('aguardando_devolucao', 'Aguard. confirmação devolução'),
        ('devolvido',            'Devolvido'),
        ('cancelado',            'Cancelado'),
        ('recusado',             'Recusado'),
    ]
    TIPO_CHOICES = [
        ('Empréstimo',  'Empréstimo'),
        ('Cessão',      'Cessão'),
        ('Reserva',     'Reserva'),
    ]
    MG_CHOICES = [
        ('', '—'), ('MG1','MG1'), ('MG2','MG2'), ('MG3','MG3'), ('MG4','MG4'),
        ('Cenografia','Cenografia'), ('Arte','Arte'),
    ]

    # Identificação
    codigo          = models.CharField(max_length=30, unique=True, blank=True)
    numero_pedido   = models.CharField(max_length=50, blank=True, db_column='numeroPedido')
    tipo            = models.CharField(max_length=20, choices=TIPO_CHOICES, default='Empréstimo')
    status          = models.CharField(max_length=25, choices=STATUS_CHOICES, default='pendente')

    # Produto
    produto           = models.CharField(max_length=255)
    produto_concedente= models.CharField(max_length=255, blank=True)
    mg_solicitante    = models.CharField(max_length=20, choices=MG_CHOICES, blank=True)
    mg_concedente     = models.CharField(max_length=20, choices=MG_CHOICES, blank=True)
    localizacao       = models.CharField(max_length=255, blank=True)

    # Partes (FK + campos de texto para compatibilidade)
    solicitante       = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='pedidos_solicitados'
    )
    concedente        = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='pedidos_concedidos'
    )
    solicitante_nome  = models.CharField(max_length=200, blank=True)
    solicitante_email = models.CharField(max_length=200, blank=True)
    concedente_nome   = models.CharField(max_length=200, blank=True)
    concedente_email  = models.CharField(max_length=200, blank=True)

    # Datas
    inicio_iso       = models.DateField(null=True, blank=True)
    dev_iso          = models.DateField(null=True, blank=True)
    devolvido_em     = models.DateTimeField(null=True, blank=True)

    # Conteúdo
    observacao       = models.TextField(blank=True)
    materiais        = models.JSONField(default=list, blank=True)  # lista de strings
    fotos            = models.JSONField(default=list, blank=True)  # lista de base64
    pdfs             = models.JSONField(default=list, blank=True)  # [{nome, data}]
    ocorrencia       = models.JSONField(null=True, blank=True)     # {tipo, descricao}

    # Metadados
    criado_por       = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='pedidos_criados'
    )
    criado_em        = models.DateTimeField(auto_now_add=True)
    atualizado_em    = models.DateTimeField(auto_now=True)

    # Preenchido pelo script de migração — ID do documento original no
    # Firestore, usado só para evitar duplicar registros em reimportações.
    firebase_id      = models.CharField(max_length=128, blank=True, null=True, db_index=True)

    class Meta:
        verbose_name        = 'Pedido'
        verbose_name_plural = 'Pedidos'
        ordering            = ['-criado_em']

    def save(self, *args, **kwargs):
        if not self.codigo:
            self.codigo = gerar_codigo()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.codigo} — {self.produto} ({self.status})'
