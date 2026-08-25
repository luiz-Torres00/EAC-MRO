from django.contrib import admin
from .models import Notificacao

@admin.register(Notificacao)
class NotificacaoAdmin(admin.ModelAdmin):
    list_display  = ('tipo', 'titulo', 'destinatario', 'lida', 'criado_em')
    list_filter   = ('tipo', 'lida')
    search_fields = ('titulo', 'destinatario__email')
