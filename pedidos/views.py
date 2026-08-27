from datetime import datetime, time as dtime

from rest_framework import generics, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.http import HttpResponse

from .models import Pedido, Estudio, LOCALIZACAO_TIPO_CHOICES
from .serializers import PedidoSerializer, PedidoCreateSerializer, EstudioSerializer
from .relatorio import gerar_relatorio_xlsx
from notificacoes.services import (
    notificar_novo_pedido, notificar_aprovado, notificar_recusado,
    notificar_devolvido, notificar_devolucao_registrada, notificar_prazo_estendido,
    notificar_ocorrencia_aberta, notificar_cobranca_devolucao,
)

TIPOS_OCORRENCIA_VALIDOS = {'Avaria', 'Perda', 'Atraso', 'Incompleto', 'Outro'}
TONS_COBRANCA_VALIDOS    = {'gentil', 'formal', 'urgente'}


def _visivel_para(user, qs):
    """Restringe a visibilidade de pedidos por MG (armazém/setor): cada
    pessoa só vê os pedidos que envolvem o MG dela — como solicitante ou
    concedente — ou dos quais ela é diretamente uma das partes. Ex.: alguém
    do MG3 que emprestou material para o MG1 continua vendo esse pedido (ela
    é a concedente, tem o MG dela envolvido), e quem está no MG1 também vê
    (é o solicitante). Administradores (is_staff) sempre veem tudo.
    """
    if not user or not getattr(user, 'is_authenticated', False) or user.is_staff:
        return qs
    from django.db.models import Q
    setor  = getattr(user, 'setor', '') or ''
    filtro = Q(solicitante=user) | Q(concedente=user) | Q(criado_por=user)
    if setor:
        filtro |= Q(mg_solicitante=setor) | Q(mg_concedente=setor)
    return qs.filter(filtro)


def _filtro_intervalo_datas(qs, data_inicio_str, data_fim_str):
    """Filtra `qs` pelo intervalo de datas do calendário (Dashboard/
    Relatórios), comparando `criado_em` contra o início do dia de
    `data_inicio` até o fim do dia de `data_fim`, ambos no fuso horário do
    projeto (America/Sao_Paulo).

    Antes isso usava `criado_em__date__gte`/`__lte`, que depende do Django
    converter o datetime pro fuso corrente "por baixo dos panos" antes de
    extrair a data — e um pedido registrado hoje mesmo podia ficar de fora
    do filtro "hoje" dependendo de como esse lookup se comporta no banco em
    produção. Aqui a conversão é feita explicitamente: monta o instante exato
    de 00:00:00 do dia de início e 23:59:59,999999 do dia de fim, os dois já
    como datetime "aware" no fuso do projeto, e compara `criado_em`
    diretamente contra esse intervalo — sem depender de nenhuma conversão
    implícita.
    """
    di, df = parse_date(data_inicio_str), parse_date(data_fim_str)
    if not di or not df:
        return qs
    fuso = timezone.get_current_timezone()
    inicio_dt = timezone.make_aware(datetime.combine(di, dtime.min), fuso)
    fim_dt    = timezone.make_aware(datetime.combine(df, dtime.max), fuso)
    return qs.filter(criado_em__gte=inicio_dt, criado_em__lte=fim_dt)


class PedidoListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/pedidos/        — lista com filtros: status, busca, mg, período
    POST /api/pedidos/        — cria novo pedido
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        return PedidoCreateSerializer if self.request.method == 'POST' else PedidoSerializer

    def get_queryset(self):
        qs = Pedido.objects.select_related('solicitante', 'concedente', 'criado_por')
        qs = _visivel_para(self.request.user, qs)
        # Filtro por status
        s = self.request.query_params.get('status')
        if s:
            qs = qs.filter(status=s)
        # Busca livre
        q = self.request.query_params.get('q', '').strip()
        if q:
            from django.db.models import Q
            qs = qs.filter(
                Q(produto__icontains=q)           |
                Q(solicitante_nome__icontains=q)  |
                Q(solicitante_email__icontains=q) |
                Q(concedente_nome__icontains=q)   |
                Q(concedente_email__icontains=q)  |
                Q(numero_pedido__icontains=q)     |
                Q(codigo__icontains=q)
            )
        # Filtro por MG (armazém) — usado pelo filtro avançado dos Relatórios.
        # Considera tanto o MG solicitante quanto o concedente, pois um
        # empréstimo entre dois MGs diferentes deve aparecer pros dois.
        mg = self.request.query_params.get('mg')
        if mg:
            from django.db.models import Q
            qs = qs.filter(Q(mg_solicitante=mg) | Q(mg_concedente=mg))
        # Filtro por intervalo de datas explícito (calendário dos Relatórios)
        # — tem prioridade sobre o filtro de período em dias, se os dois
        # vierem preenchidos o intervalo explícito é o que vale.
        data_inicio = self.request.query_params.get('data_inicio')
        data_fim    = self.request.query_params.get('data_fim')
        if data_inicio and data_fim:
            qs = _filtro_intervalo_datas(qs, data_inicio, data_fim)
        else:
            # Filtro por período (dias), só se não veio um intervalo explícito.
            periodo = self.request.query_params.get('periodo')
            if periodo:
                try:
                    dias = int(periodo)
                    desde = timezone.now() - timezone.timedelta(days=dias)
                    qs = qs.filter(criado_em__gte=desde)
                except (TypeError, ValueError):
                    pass
        return qs.order_by('-criado_em')

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['request'] = self.request
        return ctx

    def perform_create(self, serializer):
        pedido = serializer.save()
        notificar_novo_pedido(pedido)


class PedidoDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET/PATCH/DELETE /api/pedidos/<id>/

    Depois de criado, um pedido não pode mais ter seus dados de controle
    alterados por aqui (solicitante, concedente, MG, datas, materiais…) —
    essa é uma regra de negócio, não só de UI. As mudanças de status
    (aprovar/recusar/devolver/estender) continuam acontecendo pelas views
    próprias abaixo, que não passam por este PATCH. O único campo editável
    livremente é o número do pedido (identificador externo/manual).
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = PedidoSerializer

    def get_queryset(self):
        return _visivel_para(self.request.user, Pedido.objects.all())

    def patch(self, request, *args, **kwargs):
        allowed = ['numero_pedido']
        data    = {k: v for k, v in request.data.items() if k in allowed}
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, *args, **kwargs):
        # Só admin pode excluir — usado pra limpar pedidos de teste sem
        # deixar qualquer usuário apagar histórico real.
        if not request.user.is_staff:
            return Response({'detail': 'Só administradores podem excluir pedidos.'}, status=403)
        return super().delete(request, *args, **kwargs)


class AprovarPedidoView(APIView):
    """PATCH /api/pedidos/<id>/aprovar/"""
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        try:
            pedido = _visivel_para(request.user, Pedido.objects.all()).get(pk=pk)
        except Pedido.DoesNotExist:
            return Response({'detail': 'Não encontrado.'}, status=404)
        pedido.status  = 'aprovado'
        # request.data['devISO'] chega como string ('YYYY-MM-DD') — precisa
        # converter pra date de verdade, senão o campo fica com uma string
        # "solta" no model até o próximo reload do banco, e qualquer código
        # que espere um date (ex.: .strftime() no e-mail de notificação)
        # quebra com AttributeError.
        nova_data = request.data.get('devISO')
        if nova_data:
            pedido.dev_iso = parse_date(nova_data) or pedido.dev_iso
        if request.data.get('observacao'):
            pedido.observacao = request.data['observacao']
        pedido.save()
        notificar_aprovado(pedido)
        return Response(PedidoSerializer(pedido).data)


class RecusarPedidoView(APIView):
    """PATCH /api/pedidos/<id>/recusar/"""
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        try:
            pedido = _visivel_para(request.user, Pedido.objects.all()).get(pk=pk)
        except Pedido.DoesNotExist:
            return Response({'detail': 'Não encontrado.'}, status=404)
        pedido.status    = 'recusado'
        pedido.observacao = request.data.get('motivo', '')
        pedido.save()
        notificar_recusado(pedido)
        return Response(PedidoSerializer(pedido).data)


class DevolverPedidoView(APIView):
    """PATCH /api/pedidos/<id>/devolver/

    Passo 1 da devolução: o SOLICITANTE (quem estava com o material) registra
    que está devolvendo. Isso não fecha o pedido — só move o status para
    'aguardando_devolucao', esperando o concedente conferir o material e
    confirmar (ver ConfirmarDevolucaoView). A palavra final de que o material
    realmente voltou é de quem emprestou.
    """
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        try:
            pedido = _visivel_para(request.user, Pedido.objects.all()).get(pk=pk)
        except Pedido.DoesNotExist:
            return Response({'detail': 'Não encontrado.'}, status=404)

        if pedido.solicitante_id != request.user.id and not request.user.is_staff:
            return Response({'detail': 'Só quem solicitou o material pode registrar a devolução.'}, status=403)

        if pedido.status != 'aprovado':
            return Response({'detail': 'Só é possível registrar devolução de pedidos aprovados.'}, status=400)

        pedido.status = 'aguardando_devolucao'
        if request.data.get('observacao'):
            pedido.observacao = request.data['observacao']
        if request.data.get('ocorrencia'):
            pedido.ocorrencia = request.data['ocorrencia']
        pedido.save()
        notificar_devolucao_registrada(pedido)
        return Response(PedidoSerializer(pedido).data)


class ConfirmarDevolucaoView(APIView):
    """PATCH /api/pedidos/<id>/confirmar-devolucao/

    Passo 2 (final) da devolução: o CONCEDENTE confere o material que voltou
    e confirma — só aí o pedido vira 'devolvido' de verdade.
    """
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        try:
            pedido = _visivel_para(request.user, Pedido.objects.all()).get(pk=pk)
        except Pedido.DoesNotExist:
            return Response({'detail': 'Não encontrado.'}, status=404)

        if pedido.concedente_id != request.user.id and not request.user.is_staff:
            return Response({'detail': 'Só quem emprestou o material (concedente) pode confirmar a devolução.'}, status=403)

        if pedido.status != 'aguardando_devolucao':
            return Response({'detail': 'Este pedido não está aguardando confirmação de devolução.'}, status=400)

        pedido.status       = 'devolvido'
        pedido.devolvido_em = timezone.now()
        if request.data.get('observacao'):
            pedido.observacao = (pedido.observacao + '\n' if pedido.observacao else '') + request.data['observacao']
        if request.data.get('ocorrencia'):
            pedido.ocorrencia = request.data['ocorrencia']
        pedido.save()
        notificar_devolvido(pedido)
        return Response(PedidoSerializer(pedido).data)


class EstenderPedidoView(APIView):
    """PATCH /api/pedidos/<id>/estender/"""
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        try:
            pedido = _visivel_para(request.user, Pedido.objects.all()).get(pk=pk)
        except Pedido.DoesNotExist:
            return Response({'detail': 'Não encontrado.'}, status=404)

        prazo_anterior = pedido.dev_iso

        # Aceita tanto "dias" (quantos dias extras a partir do prazo atual —
        # usado pelo formulário novo) quanto "devISO" (data exata, mantido
        # por compatibilidade com chamadas antigas).
        dias = request.data.get('dias')
        nova_data_str = request.data.get('devISO')

        if dias not in (None, ''):
            try:
                dias_int = int(dias)
            except (TypeError, ValueError):
                return Response({'detail': '"dias" deve ser um número inteiro.'}, status=400)
            if dias_int < 1:
                return Response({'detail': '"dias" deve ser maior que zero.'}, status=400)
            base = pedido.dev_iso or timezone.now().date()
            data_convertida = base + timezone.timedelta(days=dias_int)
        elif nova_data_str:
            data_convertida = parse_date(nova_data_str)
            if not data_convertida:
                return Response({'detail': 'devISO inválido, use o formato AAAA-MM-DD.'}, status=400)
        else:
            return Response({'detail': 'Informe "dias" ou "devISO".'}, status=400)

        motivo = (request.data.get('motivo') or '').strip()

        pedido.dev_iso = data_convertida
        pedido.save()
        notificar_prazo_estendido(pedido, motivo=motivo, prazo_anterior=prazo_anterior)
        return Response(PedidoSerializer(pedido).data)


class AbrirOcorrenciaView(APIView):
    """PATCH /api/pedidos/<id>/ocorrencia/

    Registra uma ocorrência (atraso, avaria, perda, item incompleto…) num
    pedido a qualquer momento — diferente do registro de ocorrência feito
    junto da devolução (ModalDevolver), este pode ser usado enquanto o
    material ainda está em posse do solicitante, ex.: pra sinalizar
    formalmente que passou do prazo. Alimenta a "Taxa de ocorrência" do
    relatório, que já lê o campo `ocorrencia` do pedido.
    """
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        try:
            pedido = _visivel_para(request.user, Pedido.objects.all()).get(pk=pk)
        except Pedido.DoesNotExist:
            return Response({'detail': 'Não encontrado.'}, status=404)

        if pedido.concedente_id != request.user.id and not request.user.is_staff:
            return Response({'detail': 'Só quem emprestou o material (concedente) pode abrir ocorrência.'}, status=403)

        if pedido.status in ('recusado', 'cancelado'):
            return Response({'detail': 'Não é possível registrar ocorrência num pedido recusado/cancelado.'}, status=400)

        tipo = (request.data.get('tipo') or '').strip()
        if tipo not in TIPOS_OCORRENCIA_VALIDOS:
            return Response({'detail': f'"tipo" deve ser um de: {", ".join(sorted(TIPOS_OCORRENCIA_VALIDOS))}.'}, status=400)
        descricao = (request.data.get('descricao') or '').strip()

        pedido.ocorrencia = {'tipo': tipo, 'descricao': descricao}
        pedido.save()
        notificar_ocorrencia_aberta(pedido)
        return Response(PedidoSerializer(pedido).data)


class CobrarDevolucaoView(APIView):
    """POST /api/pedidos/<id>/cobrar/

    Envia uma cobrança de devolução ao solicitante — só permitido quando o
    pedido está de fato em atraso (ainda em posse de alguém e com o prazo
    de devolução já vencido), pra não virar um botão de "lembrete" genérico
    e sim algo com peso de cobrança real.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            pedido = _visivel_para(request.user, Pedido.objects.all()).get(pk=pk)
        except Pedido.DoesNotExist:
            return Response({'detail': 'Não encontrado.'}, status=404)

        if pedido.concedente_id != request.user.id and not request.user.is_staff:
            return Response({'detail': 'Só quem emprestou o material (concedente) pode cobrar a devolução.'}, status=403)

        if pedido.status != 'aprovado':
            return Response({'detail': 'Só é possível cobrar devolução de pedidos que ainda estão em posse do solicitante.'}, status=400)
        if not pedido.dev_iso or pedido.dev_iso >= timezone.now().date():
            return Response({'detail': 'Este pedido ainda não está em atraso.'}, status=400)

        tom = (request.data.get('tom') or 'gentil').strip().lower()
        if tom not in TONS_COBRANCA_VALIDOS:
            tom = 'gentil'
        mensagem = (request.data.get('mensagem') or '').strip()
        if not mensagem:
            return Response({'detail': 'Informe a mensagem da cobrança.'}, status=400)

        notificar_cobranca_devolucao(pedido, tom=tom, mensagem=mensagem)
        return Response(PedidoSerializer(pedido).data)


class LocalizacaoPedidoView(APIView):
    """PATCH /api/pedidos/<id>/localizacao/

    Define onde o material do pedido está guardado: Armazenagem, Externa, CC
    ou Estúdio. Quando é "Estúdio", precisa vir "estudio_id" apontando pra um
    Estudio cadastrado — e esse estúdio só é aceito se for do mesmo MG
    concedente do pedido (a ideia é sempre localizar o material dentro do MG
    de quem emprestou). Solicitante, concedente ou admin podem alterar —
    localização não é uma decisão de uma parte só, é operacional.
    """
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        try:
            pedido = _visivel_para(request.user, Pedido.objects.all()).get(pk=pk)
        except Pedido.DoesNotExist:
            return Response({'detail': 'Não encontrado.'}, status=404)

        eh_parte = request.user.id in (pedido.solicitante_id, pedido.concedente_id)
        if not eh_parte and not request.user.is_staff:
            return Response(
                {'detail': 'Só o solicitante, o concedente ou um administrador podem alterar a localização.'},
                status=403,
            )

        tipos_validos = dict(LOCALIZACAO_TIPO_CHOICES)
        tipo = (request.data.get('localizacao_tipo') or '').strip()
        if tipo not in tipos_validos:
            return Response(
                {'detail': f'"localizacao_tipo" deve ser um de: {", ".join(tipos_validos)}.'},
                status=400,
            )

        if tipo == 'estudio':
            estudio_id = request.data.get('estudio_id') or request.data.get('estudio')
            if not estudio_id:
                return Response({'detail': 'Informe "estudio_id".'}, status=400)
            try:
                estudio = Estudio.objects.get(pk=estudio_id)
            except (Estudio.DoesNotExist, ValueError, TypeError):
                return Response({'detail': 'Estúdio não encontrado.'}, status=404)
            mg_pedido = pedido.mg_concedente or pedido.mg_solicitante
            if mg_pedido and estudio.mg != mg_pedido:
                return Response(
                    {'detail': f'Esse estúdio é do {estudio.mg}, mas o pedido é do {mg_pedido}.'},
                    status=400,
                )
            pedido.estudio = estudio
        else:
            pedido.estudio = None

        pedido.localizacao_tipo = tipo
        pedido.save()
        return Response(PedidoSerializer(pedido, context={'request': request}).data)


class EstudioListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/pedidos/estudios/?mg=MG1 — lista estúdios cadastrados (todo
         usuário autenticado — é o que alimenta a sub-opção "Estúdio" no
         controle de localização de qualquer pedido).
    POST /api/pedidos/estudios/        — cadastra um estúdio novo (só admin:
         botão "Vincular estúdios aos MGs" na tela Usuários).
    """
    serializer_class   = EstudioSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Estudio.objects.all()
        mg = self.request.query_params.get('mg')
        if mg:
            qs = qs.filter(mg=mg)
        return qs

    def create(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return Response({'detail': 'Só administradores podem cadastrar estúdios.'}, status=403)
        return super().create(request, *args, **kwargs)


class EstudioDetailView(generics.DestroyAPIView):
    """DELETE /api/pedidos/estudios/<id>/ — remove um estúdio (só admin).

    Pedidos que já apontavam pra esse estúdio não quebram: o campo
    `estudio` deles vira nulo (on_delete=SET_NULL), mantendo o histórico.
    """
    queryset            = Estudio.objects.all()
    permission_classes  = [permissions.IsAuthenticated]

    def delete(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return Response({'detail': 'Só administradores podem remover estúdios.'}, status=403)
        return super().delete(request, *args, **kwargs)


class RelatorioXlsxView(APIView):
    """
    GET /api/pedidos/relatorio/?periodo=30&status=devolvido
    Gera e devolve a planilha .xlsx do relatório de empréstimos, no mesmo
    formato usado pela equipe (abas Resumo + Pedidos), com os dados reais
    do banco. Aceita os mesmos filtros de período/status da listagem.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = Pedido.objects.select_related('solicitante', 'concedente')
        qs = _visivel_para(request.user, qs)

        s = request.query_params.get('status')
        if s:
            qs = qs.filter(status=s)

        mg = request.query_params.get('mg')
        if mg:
            from django.db.models import Q
            qs = qs.filter(Q(mg_solicitante=mg) | Q(mg_concedente=mg))

        data_inicio = request.query_params.get('data_inicio')
        data_fim    = request.query_params.get('data_fim')
        periodo_label = 'início até hoje'
        if data_inicio and data_fim:
            di, df = parse_date(data_inicio), parse_date(data_fim)
            if di and df:
                qs = _filtro_intervalo_datas(qs, data_inicio, data_fim)
                periodo_label = f'{di.strftime("%d/%m/%Y")} até {df.strftime("%d/%m/%Y")}'
        else:
            periodo = request.query_params.get('periodo')
            if periodo:
                try:
                    dias = int(periodo)
                    desde = timezone.now() - timezone.timedelta(days=dias)
                    qs = qs.filter(criado_em__gte=desde)
                    periodo_label = f'últimos {dias} dias'
                except (TypeError, ValueError):
                    pass

        usuario_nome = getattr(request.user, 'nome_completo', lambda: '')() or request.user.email

        wb = gerar_relatorio_xlsx(qs, periodo_label, usuario_nome)

        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        nome_arquivo = f'relatorio-eac-{timezone.now().strftime("%Y%m%d-%H%M")}.xlsx'
        response['Content-Disposition'] = f'attachment; filename="{nome_arquivo}"'
        wb.save(response)
        return response
