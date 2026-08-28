"""
Regras de notificação do fluxo de empréstimos.

Centraliza aqui quem recebe notificação em cada evento de um Pedido, para não
espalhar essa lógica pelas views. Chamado a partir de pedidos/views.py.
"""
import html
import logging
import requests
from django.conf import settings
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


def _fmt_data_hora(valor):
    """Formata um datetime (ex.: `criado_em`) pro e-mail, com dia e hora."""
    if not valor:
        return '—'
    if hasattr(valor, 'strftime'):
        return valor.strftime('%d/%m/%Y às %H:%M')
    return str(valor)


def _corpo_liberacao(pedido, papel):
    """Corpo completo do e-mail de liberação do empréstimo — enviado tanto
    pro solicitante quanto pro concedente assim que o pedido é aprovado.

    Detalha TODOS os dados do pedido (datas, as duas partes, produto,
    itens, código…) de propósito — é o e-mail que serve de "combinado por
    escrito" do empréstimo, então não pode deixar brecha pra dúvida ou
    erro sobre o que foi liberado e quando o material precisa voltar.

    `papel` é 'solicitante' ou 'concedente', só pra personalizar a
    abertura pra quem está lendo o e-mail.
    """
    if papel == 'solicitante':
        abertura = (
            f'Olá, {pedido.solicitante_nome or "tudo bem"}!\n\n'
            f'Seu empréstimo foi APROVADO e está liberado. O material pode ser retirado '
            f'com {pedido.concedente_nome or "o concedente"}. Confira abaixo todos os dados '
            f'do pedido — em especial a data de devolução.'
        )
    else:
        abertura = (
            f'Olá, {pedido.concedente_nome or "tudo bem"}!\n\n'
            f'O empréstimo abaixo foi APROVADO e está liberado. O material será retirado por '
            f'{pedido.solicitante_nome or "o solicitante"}. Confira abaixo todos os dados do pedido.'
        )

    status_label = dict(pedido.STATUS_CHOICES).get(pedido.status, pedido.status)

    linhas = [
        abertura, '',
        '=' * 44,
        'DADOS DO EMPRÉSTIMO',
        '=' * 44,
        f'Código:              {pedido.codigo or "—"}',
    ]
    if pedido.numero_pedido:
        linhas.append(f'Número do pedido:    {pedido.numero_pedido}')
    linhas += [
        f'Tipo:                {pedido.tipo or "—"}',
        f'Status:              {status_label}',
        '',
        f'Produto:             {pedido.produto or "—"}',
    ]
    if pedido.produto_concedente:
        linhas.append(f'Produto (concedente):{pedido.produto_concedente}')
    if pedido.materiais:
        linhas.append(f'Itens:               {", ".join(pedido.materiais)}')
    linhas += [
        '',
        f'Solicitante:         {pedido.solicitante_nome or "—"} ({pedido.solicitante_email or "—"})',
        f'MG solicitante:      {pedido.mg_solicitante or "—"}',
        f'Concedente:          {pedido.concedente_nome or "—"} ({pedido.concedente_email or "—"})',
        f'MG concedente:       {pedido.mg_concedente or "—"}',
        '',
        f'Pedido criado em:    {_fmt_data_hora(pedido.criado_em)}',
        f'Início:              {_fmt_data(pedido.inicio_iso)}',
        f'Devolução prevista:  {_fmt_data(pedido.dev_iso)}',
    ]
    if pedido.observacao:
        linhas += ['', f'Observação: {pedido.observacao}']
    if pedido.fotos:
        qtd = len(pedido.fotos)
        linhas += ['', f'Fotos em anexo: {qtd} (registro do material no momento do pedido).']
    linhas += [
        '', '=' * 44,
        'Se alguma dessas informações estiver errada, fale com quem aprovou o pedido '
        'antes de retirar ou entregar o material.',
    ]
    return '\n'.join(linhas)


def _corpo_extensao(pedido, papel, motivo='', prazo_anterior=None):
    """Corpo completo do e-mail de extensão de prazo — enviado tanto pro
    solicitante quanto pro concedente quando a data de devolução de um
    pedido já aprovado é adiada. Deixa explícito o prazo anterior e o novo
    prazo, junto com todos os dados do pedido, pra não sobrar dúvida sobre
    até quando o material pode ficar fora."""
    if papel == 'solicitante':
        abertura = (
            f'Olá, {pedido.solicitante_nome or "tudo bem"}!\n\n'
            f'O prazo de devolução do seu empréstimo foi ESTENDIDO. Confira abaixo '
            f'a nova data de devolução e todos os dados do pedido.'
        )
    else:
        abertura = (
            f'Olá, {pedido.concedente_nome or "tudo bem"}!\n\n'
            f'O prazo de devolução do empréstimo abaixo, com {pedido.solicitante_nome or "o solicitante"}, '
            f'foi ESTENDIDO. Confira abaixo a nova data de devolução e todos os dados do pedido.'
        )

    status_label = dict(pedido.STATUS_CHOICES).get(pedido.status, pedido.status)

    linhas = [
        abertura, '',
        '=' * 44,
        'PRAZO DE DEVOLUÇÃO ALTERADO',
        '=' * 44,
        f'Prazo anterior:      {_fmt_data(prazo_anterior)}',
        f'Novo prazo:          {_fmt_data(pedido.dev_iso)}',
    ]
    if motivo:
        linhas.append(f'Motivo:              {motivo}')
    linhas += [
        '',
        '=' * 44,
        'DADOS DO EMPRÉSTIMO',
        '=' * 44,
        f'Código:              {pedido.codigo or "—"}',
    ]
    if pedido.numero_pedido:
        linhas.append(f'Número do pedido:    {pedido.numero_pedido}')
    linhas += [
        f'Tipo:                {pedido.tipo or "—"}',
        f'Status:              {status_label}',
        '',
        f'Produto:             {pedido.produto or "—"}',
    ]
    if pedido.produto_concedente:
        linhas.append(f'Produto (concedente):{pedido.produto_concedente}')
    if pedido.materiais:
        linhas.append(f'Itens:               {", ".join(pedido.materiais)}')
    linhas += [
        '',
        f'Solicitante:         {pedido.solicitante_nome or "—"} ({pedido.solicitante_email or "—"})',
        f'MG solicitante:      {pedido.mg_solicitante or "—"}',
        f'Concedente:          {pedido.concedente_nome or "—"} ({pedido.concedente_email or "—"})',
        f'MG concedente:       {pedido.mg_concedente or "—"}',
        '',
        f'Pedido criado em:    {_fmt_data_hora(pedido.criado_em)}',
        f'Início:              {_fmt_data(pedido.inicio_iso)}',
    ]
    if pedido.observacao:
        linhas += ['', f'Observação: {pedido.observacao}']
    linhas += [
        '', '=' * 44,
        'Se alguma dessas informações estiver errada, fale com quem estendeu o prazo '
        'antes de considerar a nova data válida.',
    ]
    return '\n'.join(linhas)


def _remetente():
    """Extrai nome e e-mail de DEFAULT_FROM_EMAIL (aceita tanto o formato
    "Nome <email>" quanto só "email"), no formato que a API do Brevo espera."""
    from email.utils import parseaddr
    nome, email = parseaddr(settings.DEFAULT_FROM_EMAIL)
    return {'name': nome or 'EAC MRO', 'email': email or settings.DEFAULT_FROM_EMAIL}


def _anexos_de_fotos(pedido):
    """Converte `pedido.fotos` (lista de data URLs, ex.:
    "data:image/jpeg;base64,/9j/4AAQ...", exatamente como o frontend salva ao
    tirar/anexar foto — ver ModalNovoPedido.vue) no formato de anexo que a
    API do Brevo espera (`{"name": ..., "content": <base64 sem o prefixo
    data:...;base64,>"}`).

    Qualquer foto que não estiver nesse formato é simplesmente ignorada —
    anexo é um "a mais" no e-mail, nunca motivo pra travar o envio (a mesma
    filosofia do resto deste arquivo: notificação por e-mail nunca pode
    quebrar o fluxo do pedido).
    """
    anexos = []
    for i, foto in enumerate(pedido.fotos or []):
        if not isinstance(foto, str) or ';base64,' not in foto:
            continue
        cabecalho, conteudo = foto.split(';base64,', 1)
        extensao = cabecalho.split('/')[-1].split('+')[0] if '/' in cabecalho else 'jpg'
        if not extensao.isalnum():
            extensao = 'jpg'
        anexos.append({'name': f'foto-{i + 1}.{extensao}', 'content': conteudo})
    return anexos


def _enviar_via_brevo(email_destino, nome_destino, titulo, corpo, anexos=None):
    """Envia o e-mail pela API HTTP do Brevo (https://api.brevo.com/v3/smtp/email)
    em vez de por SMTP.

    A Render bloqueia todo tráfego de saída pelas portas de SMTP (25, 465 e
    587) nos serviços do plano gratuito desde set/2025 — então tentar usar
    SMTP (mesmo com host/senha corretos) trava a conexão até estourar o
    timeout, sem nunca conseguir enviar. A API do Brevo funciona por HTTPS
    (porta 443, a mesma usada por qualquer site), que não é bloqueada —
    então é o jeito de continuar mandando e-mail sem precisar de um plano
    pago no Render. Precisa da variável BREVO_API_KEY configurada (é a
    "API Key" do Brevo, na aba SMTP & API — diferente da "chave SMTP" usada
    antes).

    `anexos`, quando informado, é uma lista no formato de `_anexos_de_fotos`
    — vai no campo `attachment` da própria chamada de API do Brevo, sem
    custo nem serviço adicional (o plano gratuito do Brevo já aceita anexo).
    """
    if not email_destino:
        return
    if not settings.BREVO_API_KEY:
        logger.warning(
            'BREVO_API_KEY não configurada — e-mail "%s" não enviado para %s.',
            titulo, email_destino,
        )
        return
    corpo_html = (
        '<pre style="font-family: monospace; white-space: pre-wrap; font-size: 14px">'
        + html.escape(corpo) + '</pre>'
    )
    payload = {
        'sender':      _remetente(),
        'to':          [{'email': email_destino, 'name': nome_destino or email_destino}],
        'subject':     titulo,
        'textContent': corpo,
        'htmlContent': corpo_html,
    }
    if anexos:
        payload['attachment'] = anexos
    try:
        resp = requests.post(
            'https://api.brevo.com/v3/smtp/email',
            headers={
                'accept':       'application/json',
                'api-key':      settings.BREVO_API_KEY,
                'content-type': 'application/json',
            },
            json=payload,
            # Com anexo o corpo da chamada fica maior (fotos em base64), então
            # dá mais fôlego que os 10s padrão antes de desistir.
            timeout=20 if anexos else 10,
        )
        if resp.status_code >= 300:
            logger.error(
                'Brevo recusou o e-mail "%s" para %s: %s %s',
                titulo, email_destino, resp.status_code, resp.text,
            )
    except Exception:
        # Nunca deixa um problema de e-mail (Brevo fora do ar, chave errada
        # etc.) quebrar o fluxo de criação/aprovação do pedido — a
        # notificação in-app já foi criada, o e-mail é um "a mais".
        logger.exception('Falha ao enviar e-mail (Brevo API) para %s', email_destino)


def _enviar_email_bruto(destinatario, titulo, corpo, anexos=None):
    """Como `_enviar_email`, mas envia `corpo` exatamente como veio — sem
    passar pelo `_corpo_email` genérico. Usado quando o corpo já foi
    montado sob medida pro evento (ex.: liberação do empréstimo)."""
    if not destinatario or not destinatario.email:
        return
    _enviar_via_brevo(destinatario.email, destinatario.nome, titulo, corpo, anexos=anexos)


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
        f'Código Empréstimos: {pedido.codigo or "—"}',
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
    _enviar_via_brevo(destinatario.email, destinatario.nome, titulo, _corpo_email(pedido, mensagem))


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
    """Ao aprovar/liberar um pedido, avisa as DUAS pessoas marcadas nele —
    solicitante e concedente — cada uma com um e-mail completo (todos os
    dados do empréstimo) pro e-mail de login dela. Não é só um aviso
    genérico: o corpo do e-mail (`_corpo_liberacao`) lista produto, itens,
    as duas partes, MGs, data do pedido, início e devolução prevista, pra
    não sobrar brecha pra dúvida ou erro sobre o que foi combinado."""
    titulo = f'Empréstimo liberado — {pedido.produto}'

    # As fotos anexadas pelo solicitante na criação do pedido (registro do
    # estado do material) vão junto nos dois e-mails, como anexo de
    # verdade — não só citadas em texto. Monta uma vez só e reusa nos dois
    # envios, pra não converter a mesma lista de fotos duas vezes.
    anexos = _anexos_de_fotos(pedido)

    ja_notificados = set()

    if pedido.solicitante_id:
        Notificacao.objects.create(
            destinatario=pedido.solicitante, tipo='pedido_aprovado',
            titulo=titulo,
            mensagem=f'Seu pedido de "{pedido.produto}" foi aprovado.' + (
                f' Devolução prevista para {_fmt_data(pedido.dev_iso)}.' if pedido.dev_iso else ''
            ),
            pedido_id=pedido.id,
        )
        _enviar_email_bruto(pedido.solicitante, titulo, _corpo_liberacao(pedido, 'solicitante'), anexos=anexos)
        ja_notificados.add(pedido.solicitante_id)

    if pedido.concedente_id and pedido.concedente_id not in ja_notificados:
        Notificacao.objects.create(
            destinatario=pedido.concedente, tipo='pedido_aprovado',
            titulo=titulo,
            mensagem=f'O empréstimo de "{pedido.produto}" para {pedido.solicitante_nome or "—"} foi liberado.',
            pedido_id=pedido.id,
        )
        _enviar_email_bruto(pedido.concedente, titulo, _corpo_liberacao(pedido, 'concedente'), anexos=anexos)
        ja_notificados.add(pedido.concedente_id)


def notificar_recusado(pedido):
    _criar(
        pedido.solicitante, 'pedido_recusado',
        f'Pedido recusado — {pedido.produto}',
        f'Seu pedido de "{pedido.produto}" foi recusado.' + (
            f' Motivo: {pedido.observacao}' if pedido.observacao else ''
        ),
        pedido.id, pedido=pedido,
    )


def notificar_devolucao_registrada(pedido):
    """Passo 1 da devolução: o solicitante registrou que está devolvendo,
    mas ainda falta o concedente conferir o material e confirmar. Avisa o
    concedente e os gestores do MG concedente — são eles que vão bater o
    olho no material e apertar "Confirmar devolução"."""
    ja_notificados = set()
    if pedido.concedente_id:
        _criar(
            pedido.concedente, 'pedido_devolvido',
            f'Devolução registrada, confirme — {pedido.produto}',
            f'{pedido.solicitante_nome or "O solicitante"} registrou a devolução de "{pedido.produto}". '
            f'Confira o material e confirme a devolução para fechar o pedido.',
            pedido.id, pedido=pedido,
        )
        ja_notificados.add(pedido.concedente_id)
    for gestor in _gestores_do_mg(pedido.mg_concedente):
        if gestor.id in ja_notificados:
            continue
        _criar(
            gestor, 'pedido_devolvido',
            f'Devolução registrada no seu armazém — {pedido.mg_concedente}',
            f'"{pedido.produto}" foi marcado como devolvido por {pedido.solicitante_nome or "o solicitante"}, '
            f'aguardando confirmação do concedente.',
            pedido.id, pedido=pedido,
        )
        ja_notificados.add(gestor.id)


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


def notificar_prazo_estendido(pedido, motivo='', prazo_anterior=None):
    """Ao estender o prazo de devolução: avisa as DUAS pessoas marcadas no
    pedido — solicitante e concedente — cada uma com um e-mail completo
    (prazo anterior, novo prazo, motivo e todos os dados do empréstimo)
    pro e-mail de login dela. Também avisa os gestores do MG concedente,
    que seguem aguardando o material de volta."""
    titulo = f'Prazo de devolução estendido — {pedido.produto}'

    ja_notificados = set()

    if pedido.solicitante_id:
        msg_curta = f'A devolução de "{pedido.produto}" foi adiada' + (
            f' para {_fmt_data(pedido.dev_iso)}.' if pedido.dev_iso else '.'
        )
        if motivo:
            msg_curta += f' Motivo: {motivo}.'
        Notificacao.objects.create(
            destinatario=pedido.solicitante, tipo='sistema',
            titulo=titulo, mensagem=msg_curta, pedido_id=pedido.id,
        )
        _enviar_email_bruto(
            pedido.solicitante, titulo,
            _corpo_extensao(pedido, 'solicitante', motivo=motivo, prazo_anterior=prazo_anterior),
        )
        ja_notificados.add(pedido.solicitante_id)

    if pedido.concedente_id and pedido.concedente_id not in ja_notificados:
        Notificacao.objects.create(
            destinatario=pedido.concedente, tipo='sistema',
            titulo=titulo,
            mensagem=f'O prazo de devolução de "{pedido.produto}" ({pedido.solicitante_nome or "—"}) foi estendido' + (
                f' para {_fmt_data(pedido.dev_iso)}.' if pedido.dev_iso else '.'
            ),
            pedido_id=pedido.id,
        )
        _enviar_email_bruto(
            pedido.concedente, titulo,
            _corpo_extensao(pedido, 'concedente', motivo=motivo, prazo_anterior=prazo_anterior),
        )
        ja_notificados.add(pedido.concedente_id)

    for gestor in _gestores_do_mg(pedido.mg_concedente):
        if gestor.id in ja_notificados:
            continue
        _criar(
            gestor, 'sistema',
            f'Prazo estendido — {pedido.mg_concedente}',
            f'O prazo de devolução de "{pedido.produto}" ({pedido.solicitante_nome or "—"}) foi estendido' + (
                f' para {_fmt_data(pedido.dev_iso)}.' if pedido.dev_iso else '.'
            ),
            pedido.id, pedido=pedido,
        )
        ja_notificados.add(gestor.id)


def notificar_ocorrencia_aberta(pedido):
    """Ao registrar uma ocorrência (avaria, perda, atraso, incompleto…) —
    seja junto da devolução ou, agora, a qualquer momento pelo botão
    "Abrir ocorrência" — avisa os gestores do MG concedente, já que é o
    armazém deles que fica no prejuízo/atraso."""
    tipo      = (pedido.ocorrencia or {}).get('tipo', '—')
    descricao = (pedido.ocorrencia or {}).get('descricao', '')
    msg = f'Ocorrência registrada em "{pedido.produto}" ({pedido.solicitante_nome or "—"}): {tipo}.'
    if descricao:
        msg += f' {descricao}'

    ja_notificados = set()
    for gestor in _gestores_do_mg(pedido.mg_concedente):
        _criar(
            gestor, 'sistema',
            f'Ocorrência — {pedido.mg_concedente}',
            msg, pedido.id, pedido=pedido,
        )
        ja_notificados.add(gestor.id)

    if pedido.concedente_id and pedido.concedente_id not in ja_notificados:
        _criar(pedido.concedente, 'sistema', f'Ocorrência — {pedido.produto}', msg, pedido.id, pedido=pedido)


def notificar_cobranca_devolucao(pedido, tom='gentil', mensagem=''):
    """Envia a cobrança de devolução (mensagem redigida no modal, com o tom
    escolhido) pro solicitante, e avisa os gestores do MG concedente que a
    cobrança foi enviada — visibilidade de que o material ainda não voltou."""
    TITULO_TOM = {
        'gentil':  'Lembrete de devolução',
        'formal':  'Cobrança de devolução',
        'urgente': 'Cobrança urgente de devolução',
    }
    titulo = f'{TITULO_TOM.get(tom, "Cobrança de devolução")} — {pedido.produto}'

    _criar(pedido.solicitante, 'sistema', titulo, mensagem, pedido.id, pedido=pedido)

    ja_notificados = {pedido.solicitante_id} if pedido.solicitante_id else set()
    for gestor in _gestores_do_mg(pedido.mg_concedente):
        if gestor.id in ja_notificados:
            continue
        _criar(
            gestor, 'sistema',
            f'Cobrança de devolução enviada — {pedido.mg_concedente}',
            f'Foi enviada uma cobrança de devolução para {pedido.solicitante_nome or "—"} referente a "{pedido.produto}", que ainda não foi devolvido.',
            pedido.id, pedido=pedido,
        )
        ja_notificados.add(gestor.id)
