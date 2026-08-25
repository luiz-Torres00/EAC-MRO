from django.contrib import admin
from .models import Pedido


@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display  = ('codigo', 'produto', 'status', 'solicitante_nome', 'concedente_nome', 'criado_em')
    list_filter   = ('status', 'tipo', 'mg_solicitante')
    search_fields = ('codigo', 'produto', 'solicitante_nome', 'concedente_nome', 'numero_pedido')
    readonly_fields = ('codigo', 'criado_em', 'atualizado_em')
    ordering      = ('-criado_em',)
