from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Usuario, SolicitacaoAcesso


@admin.register(Usuario)
class UsuarioAdmin(BaseUserAdmin):
    list_display  = ('email', 'nome', 'setor', 'cargo', 'is_approved', 'is_staff')
    list_filter   = ('is_approved', 'is_staff', 'setor')
    search_fields = ('email', 'nome', 'matricula')
    ordering      = ('nome',)
    fieldsets = (
        (None,          {'fields': ('email', 'password')}),
        ('Dados',       {'fields': ('nome', 'sobrenome', 'matricula', 'setor', 'cargo')}),
        ('Permissões',  {'fields': ('is_approved', 'is_active', 'is_staff', 'is_superuser', 'perms')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields':  ('email', 'nome', 'password1', 'password2', 'is_approved'),
        }),
    )


@admin.register(SolicitacaoAcesso)
class SolicitacaoAdmin(admin.ModelAdmin):
    list_display  = ('nome', 'email', 'setor', 'status', 'criado_em')
    list_filter   = ('status', 'setor')
    search_fields = ('email', 'nome')
    readonly_fields = ('senha_hash', 'criado_em', 'avaliado_em')
