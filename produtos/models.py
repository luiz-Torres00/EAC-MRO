from django.db import models


class Produto(models.Model):
    nome    = models.CharField(max_length=255, unique=True)
    ativo   = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    firebase_id = models.CharField(max_length=128, blank=True, null=True, db_index=True)

    class Meta:
        verbose_name        = 'Produto'
        verbose_name_plural = 'Produtos'
        ordering            = ['nome']

    def __str__(self):
        return self.nome
