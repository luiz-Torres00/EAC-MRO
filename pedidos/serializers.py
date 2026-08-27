from rest_framework import serializers
from .models import Pedido, Estudio
from accounts.serializers import UsuarioSerializer


class EstudioSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Estudio
        fields = ['id', 'nome', 'mg', 'criado_em']
        read_only_fields = ['id', 'criado_em']

    def validate_mg(self, value):
        if not value:
            raise serializers.ValidationError('Selecione o MG do estúdio.')
        return value


def _checar_mg(attrs, instance=None):
    """Garante que o MG marcado no formulário é o MG real (do cadastro) da
    pessoa marcada como solicitante/concedente. Sem essa checagem, dava pra
    marcar qualquer MG no formulário mesmo escolhendo uma pessoa de outro
    MG — o que fura a regra de visibilidade por MG (a pessoa 'errada' do MG
    marcado passaria a enxergar um pedido que não é dela). Por isso essa
    regra vale tanto na criação quanto em qualquer edição, e não depende do
    frontend: mesmo que a pessoa tente forçar via API diretamente, o backend
    recusa.
    """
    def valor(campo):
        if campo in attrs:
            return attrs[campo]
        return getattr(instance, campo, None) if instance else None

    erros = {}
    for campo_pessoa, campo_mg, rotulo in [
        ('solicitante', 'mg_solicitante', 'solicitante'),
        ('concedente',  'mg_concedente',  'concedente'),
    ]:
        pessoa = valor(campo_pessoa)
        mg     = valor(campo_mg)
        if not pessoa or not mg:
            continue
        setor_real = getattr(pessoa, 'setor', '') or ''
        nome = getattr(pessoa, 'nome', '') or getattr(pessoa, 'email', '') or 'a pessoa selecionada'
        if not setor_real:
            erros[campo_mg] = (
                f'{nome} não tem MG configurado no cadastro. '
                f'Configure o MG dela em Usuários antes de marcá-la como {rotulo}.'
            )
        elif setor_real != mg:
            erros[campo_mg] = (
                f'{nome} é do {setor_real}, não do {mg}. '
                f'O MG marcado no formulário precisa ser o MG real da pessoa como {rotulo}.'
            )
    return erros


class PedidoSerializer(serializers.ModelSerializer):
    solicitante_obj  = UsuarioSerializer(source='solicitante', read_only=True)
    concedente_obj   = UsuarioSerializer(source='concedente',  read_only=True)
    criado_por_obj   = UsuarioSerializer(source='criado_por',  read_only=True)
    estudio_obj      = EstudioSerializer(source='estudio', read_only=True)
    solicitante_setor= serializers.SerializerMethodField()

    class Meta:
        model  = Pedido
        fields = '__all__'
        read_only_fields = ['id', 'codigo', 'criado_em', 'atualizado_em']

    def get_solicitante_setor(self, obj):
        return obj.solicitante.setor if obj.solicitante_id and obj.solicitante else ''

    def validate(self, attrs):
        # Usado nas edições (PATCH/PUT via PedidoDetailView) — mesma regra de
        # MG-real-da-pessoa aplicada na criação, pra não dar pra burlar
        # editando um pedido já existente.
        erros = _checar_mg(attrs, instance=self.instance)
        if erros:
            raise serializers.ValidationError(erros)
        return attrs


class PedidoCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Pedido
        exclude = ['codigo', 'criado_em', 'atualizado_em']

    def validate(self, attrs):
        # Regra de negócio, não só de UI: os dados que servem pro controle do
        # empréstimo são obrigatórios na criação — só o número do pedido é
        # livre. Validamos aqui pra não depender só do frontend.
        erros = {}
        if not attrs.get('solicitante'):
            erros['solicitante'] = 'Obrigatório.'
        if not attrs.get('concedente'):
            erros['concedente'] = 'Obrigatório.'
        if not attrs.get('mg_solicitante'):
            erros['mg_solicitante'] = 'Obrigatório.'
        if not (attrs.get('produto') or '').strip():
            erros['produto'] = 'Obrigatório.'
        if not attrs.get('inicio_iso'):
            erros['inicio_iso'] = 'Obrigatório.'
        if not attrs.get('dev_iso'):
            erros['dev_iso'] = 'Obrigatório.'
        erros.update(_checar_mg(attrs))
        if erros:
            raise serializers.ValidationError(erros)
        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        if request and not validated_data.get('criado_por'):
            validated_data['criado_por'] = request.user
        # Preenche campos de nome/email a partir dos FKs
        sol = validated_data.get('solicitante')
        con = validated_data.get('concedente')
        if sol:
            validated_data.setdefault('solicitante_nome',  sol.nome)
            validated_data.setdefault('solicitante_email', sol.email)
        if con:
            validated_data.setdefault('concedente_nome',  con.nome)
            validated_data.setdefault('concedente_email', con.email)
        return super().create(validated_data)
