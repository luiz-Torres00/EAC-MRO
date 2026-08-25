"""
Regras de notificação do fluxo de empréstimos.

Centraliza aqui quem recebe notificação em cada evento de um Pedido, para não
espalhar essa lógica pelas views. Chamado a partir de pedidos/views.py.
"""
import logging
from django.conf import settings
from django.core.mail import send_mail
from .models import Notificacao

logger = logging.getLogger(__name__)

# Fallback usado só se a tabela de Cargos estiver vazia (ex.: banco recém
# criado antes da migração de seed rodar). Na prática, quem controla quais
# cargos recebem aviso de gestão é o campo `is_gestao` do Cargo, editável na
# tela Usuários & Permissões.
CARGOS_GESTAO = [
    'Encarregado', 'Supervisor', 'Coordenador', 'Gerente', 'Gerente Geral',
]


def _fmt_data(valor):
    """Formata uma data pro e-mail sem quebrar se, por qualquer motivo (ex.:
    dado antigo importado do Firebase), o valor tiver sido salvo como string
    em vez de um date de verdade."""
    if not valor:
        return '—'
    if hasattr(valor, 'strftime'):
        return valor.strftime('%d/%m/%Y')
    return str(valor)


def _corpo_email(pedido, mensagem):
    """Monta um corpo de e-mail simples com os dados do formulário do pedido."""
    if not pedido:
        return mensagem
    linhas = [
        mensagem, '',
        '—' * 30,
        f'Produto: {pedido.produto or "—"}',
        f'Solicitante: {pedido.solicitante_nome or "—"} ({pedido.solicitante_email or "—"})',
        f'Concedente: {pedido.concedente_nome or "—"} ({pedido.concedente_email or "—"})',
        f'MG solicitante: {pedido.mg_solicitante or "—"}',
        f'MG concedente: {pedido.mg_concedente or "—"}',
        f'Início: {_fmt_data(pedido.inicio_iso)}',
        f'Devolução prevista: {_fmt_data(pedido.dev_iso)}',
        f'Código EAC: {pedido.codigo or "—"}',
    ]
    if pedido.numero_pedido:
        linhas.append(f'Número do pedido: {pedido.numero_pedido}')
    if pedido.materiais:
        linhas.append(f'Itens: {", ".join(pedido.materiais)}')
    if pedido.observacao:
        linhas.append(f'Observação: {pedido.observacao}')
    return '\n'.join(linhas)


def _enviar_email(destinatario, titulo, mensagem, pedido=None):
    if not destinatario or not destinatario.email:
        return
    try:
        send_mail(
            subject=titulo,
            message=_corpo_email(pedido, mensagem),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[destinatario.email],
            fail_silently=True,
        )
    except Exception:
        # Nunca deixa um problema de e-mail (SMTP fora do ar, credencial
        # errada etc.) quebrar o fluxo de criação/aprovação do pedido — a
        # notificação in-app já foi criada, o e-mail é um "a mais".
        logger.exception('Falha ao enviar e-mail de notificação para %s', destinatario.email)


def _criar(destinatario, tipo, titulo, mensagem, pedido_id=None, pedido=None):
    if not destinatario:
        return
    Notificacao.objects.create(
        destinatario=destinatario,
        tipo=tipo,
        titulo=titulo,
        mensagem=mensagem,
        pedido_id=pedido_id,
    )
    _enviar_email(destinatario, titulo, mensagem, pedido)


def _gestores_do_mg(mg):
    """Usuários aprovados cujo setor bate com o MG informado e têm cargo de gestão."""
    from accounts.models import Usuario, Cargo
    if not mg:
        return Usuario.objects.none()
    cargos_gestao = list(Cargo.objects.filter(is_gestao=True).values_list('nome', flat=True))
    if not cargos_gestao:
        cargos_gestao = CARGOS_GESTAO
    return Usuario.objects.filter(
        setor=mg, cargo__in=cargos_gestao, is_approved=True, is_active=True,
    )


def notificar_novo_pedido(pedido):
    """Dispara ao criar um pedido: avisa o concedente (se cadastrado) e os
    gestores do MG concedente — é o armazém deles que está emprestando."""
    titulo = f'Novo pedido — {pedido.produto}'
    msg    = f'{pedido.solicitante_nome or "Alguém"} solicitou "{pedido.produto}"' + (
        f' do armazém {pedido.mg_concedente}.' if pedido.mg_concedente else '.'
    )

    ja_notificados = set()

    if pedido.concedente_id:
        _criar(pedido.concedente, 'pedido_novo', titulo, msg, pedido.id, pedido=pedido)
        ja_notificados.add(pedido.concedente_id)

    for gestor in _gestores_do_mg(pedido.mg_concedente):
        if gestor.id in ja_notificados:
            continue
        _criar(
            gestor, 'pedido_novo',
            f'Empréstimo do seu armazém — {pedido.mg_concedente}',
            f'{pedido.solicitante_nome or "Alguém"} solicitou "{pedido.produto}" do armazém {pedido.mg_concedente}.',
            pedido.id, pedido=pedido,
        )
        ja_notificados.add(gestor.id)


def notificar_aprovado(pedido):
    _criar(
        pedido.solicitante, 'pedido_aprovado',
        f'Pedido aprovado — {pedido.produto}',
        f'Seu pedido de "{pedido.produto}" foi aprovado.' + (
            f' Devolução prevista para {_fmt_data(pedido.dev_iso)}.' if pedido.dev_iso else ''
        ),
        pedido.id, pedido=pedido,
    )


def notificar_recusado(pedido):
    _criar(
        pedido.solicitante, 'pedido_recusado',
        f'Pedido recusado — {pedido.produto}',
        f'Seu pedido de "{pedido.produto}" foi recusado.' + (
            f' Motivo: {pedido.observacao}' if pedido.observacao else ''
        ),
        pedido.id, pedido=pedido,
    )


def notificar_devolvido(pedido):
    """Ao devolver, avisa quem pediu (confirmação) e os gestores do MG
    concedente (o material voltou pro armazém deles)."""
    _criar(
        pedido.solicitante, 'pedido_devolvido',
        f'Devolução registrada — {pedido.produto}',
        f'A devolução de "{pedido.produto}" foi registrada.',
        pedido.id, pedido=pedido,
    )
    ja_notificados = {pedido.solicitante_id}
    if pedido.concedente_id and pedido.concedente_id not in ja_notificados:
        _criar(
            pedido.concedente, 'pedido_devolvido',
            f'Material devolvido — {pedido.produto}',
            f'"{pedido.produto}" foi devolvido.',
            pedido.id, pedido=pedido,
        )
        ja_notificados.add(pedido.concedente_id)
    for gestor in _gestores_do_mg(pedido.mg_concedente):
        if gestor.id in ja_notificados:
            continue
        _criar(
            gestor, 'pedido_devolvido',
            f'Material devolvido ao seu armazém — {pedido.mg_concedente}',
            f'"{pedido.produto}" voltou para o armazém {pedido.mg_concedente}.',
            pedido.id, pedido=pedido,
        )
        ja_notificados.add(gestor.id)


def notificar_prazo_estendido(pedido):
    _criar(
        pedido.solicitante, 'sistema',
        f'Prazo estendido — {pedido.produto}',
        f'A devolução de "{pedido.produto}" foi adiada' + (
            f' para {_fmt_data(pedido.dev_iso)}.' if pedido.dev_iso else '.'
        ),
        pedido.id, pedido=pedido,
    )
