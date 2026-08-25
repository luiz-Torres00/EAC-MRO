from django.db import models
from django.conf import settings


class Notificacao(models.Model):
    TIPO_CHOICES = [
        ('pedido_novo',      'Novo pedido'),
        ('pedido_aprovado',  'Pedido aprovado'),
        ('pedido_recusado',  'Pedido recusado'),
        ('pedido_devolvido', 'Pedido devolvido'),
        ('atraso',           'Prazo em atraso'),
        ('sistema',          'Sistema'),
    ]
    destinatario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='notificacoes'
    )
    tipo         = models.CharField(max_length=30, choices=TIPO_CHOICES)
    titulo       = models.CharField(max_length=200)
    mensagem     = models.TextField(blank=True)
    lida         = models.BooleanField(default=False)
    criado_em    = models.DateTimeField(auto_now_add=True)
    pedido_id    = models.IntegerField(null=True, blank=True)  # referência opcional
    firebase_id  = models.CharField(max_length=128, blank=True, null=True, db_index=True)

    class Meta:
        verbose_name        = 'Notificação'
        verbose_name_plural = 'Notificações'
        ordering            = ['-criado_em']

    def __str__(self):
        return f'[{self.tipo}] {self.titulo} → {self.destinatario.email}'
