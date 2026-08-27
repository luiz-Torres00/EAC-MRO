from django.db import models, transaction, IntegrityError
from django.conf import settings


# Fora da classe pra poder ser usado tanto por Pedido quanto por Estudio
# (Estudio precisa saber a que MG pertence, com as mesmas opções).
MG_CHOICES = [
    ('', '—'), ('MG1','MG1'), ('MG2','MG2'), ('MG3','MG3'), ('MG4','MG4'),
    ('Cenografia','Cenografia'), ('Arte','Arte'),
]

LOCALIZACAO_TIPO_CHOICES = [
    ('armazenagem', 'Armazenagem'),
    ('externa',     'Externa'),
    ('cc',          'CC'),
    ('estudio',     'Estúdio'),
]


def gerar_codigo():
    """Gera código EAC-ANO-NNN único.

    Usa o MAIOR número já usado no ano, não a quantidade de pedidos — contar
    linhas (`count()`) quebra se a sequência tiver algum buraco (um pedido
    apagado, ou um código migrado do Firebase fora de ordem): por exemplo,
    se só existem os códigos 001, 002, 003, 004 e 006 (faltando o 005), a
    contagem dá 5 e "count+1" vira 006 — que já existe, e o Postgres recusa
    (erro 500). Pegando o maior número já usado e somando 1, sempre anda pra
    frente e nunca tenta repetir um código existente.
    """
    from django.utils import timezone
    ano     = timezone.now().year
    prefixo = f'EAC-{ano}-'
    maior   = 0
    for codigo in Pedido.objects.filter(codigo__startswith=prefixo).values_list('codigo', flat=True):
        sufixo = codigo[len(prefixo):]
        if sufixo.isdigit():
            maior = max(maior, int(sufixo))
    return f'{prefixo}{maior + 1:03d}'


class Estudio(models.Model):
    """Estúdio de um MG, cadastrado pelo admin (botão "Vincular estúdios aos
    MGs" na tela Usuários). Usado como sub-opção quando a localização do
    material de um pedido é "Estúdio": ao escolher essa opção, só aparecem
    os estúdios cujo `mg` bate com o MG concedente do pedido — cada MG
    enxerga só os estúdios dele.
    """
    nome      = models.CharField(max_length=100)
    mg        = models.CharField(max_length=20, choices=MG_CHOICES)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Estúdio'
        verbose_name_plural = 'Estúdios'
        ordering            = ['mg', 'nome']
        unique_together     = [('nome', 'mg')]

    def __str__(self):
        return f'{self.nome} ({self.mg})'


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
    # Mantido acessível como Pedido.MG_CHOICES (era definido aqui antes).
    MG_CHOICES = MG_CHOICES

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
    localizacao       = models.CharField(max_length=255, blank=True)  # legado (import Firestore)

    # Localização estruturada do material (Armazenagem/Externa/CC/Estúdio).
    # Separado do campo `localizacao` acima (texto livre, só usado pelos
    # registros antigos importados do Firestore) pra não misturar os dois.
    localizacao_tipo  = models.CharField(max_length=20, choices=LOCALIZACAO_TIPO_CHOICES, blank=True)
    estudio           = models.ForeignKey(
        'Estudio', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='pedidos'
    )

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
            # `gerar_codigo()` conta quantos pedidos já existem no ano e usa
            # count+1 — se duas requisições chegarem quase juntas (ex.: duplo
            # clique em "Salvar", ou um clique novo enquanto a página ainda
            # está reenviando a anterior), as duas podem contar o mesmo total
            # e tentar salvar o MESMO código, e o banco recusa a segunda por
            # já existir (erro 500 "duplicate key ... codigo"). Em vez de
            # deixar isso quebrar o pedido do usuário, tenta de novo com um
            # código novo (o savepoint do transaction.atomic garante que a
            # tentativa que falhou não deixa a transação num estado quebrado
            # para a próxima tentativa nem para o resto da requisição).
            for _tentativa in range(5):
                self.codigo = gerar_codigo()
                try:
                    with transaction.atomic():
                        super().save(*args, **kwargs)
                    return
                except IntegrityError:
                    continue
            # Depois de 5 tentativas ainda colidindo (bem improvável), deixa
            # a última subir de verdade em vez de tentar pra sempre.
            self.codigo = gerar_codigo()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.codigo} — {self.produto} ({self.status})'
