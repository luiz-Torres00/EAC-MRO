"""
Migra dados do Firebase (Auth + Firestore) para o PostgreSQL via Django ORM.

USO
---
1. Baixe a chave de service account do Firebase:
   Console Firebase → Configurações do projeto → Contas de serviço →
   "Gerar nova chave privada" → salve como firebase-service-account.json
   (NUNCA versione esse arquivo — já está no .gitignore).

2. Instale a dependência (só é necessária para rodar esta migração):
   pip install firebase-admin

3. Rode com o banco de destino já migrado (`python manage.py migrate`):
   python manage.py migrar_firestore \
       --service-account firebase-service-account.json \
       --senha-temporaria "TrocarSenha123!"

   Todos os usuários migrados recebem essa senha temporária e devem trocá-la
   no primeiro login (nenhuma senha do Firebase Auth pode ser recuperada —
   o Firebase só guarda o hash com o algoritmo scrypt proprietário do Google,
   incompatível com o Django).

4. Opções úteis:
   --apenas usuarios,produtos,pedidos,notificacoes   (roda só alguns passos)
   --dry-run                                          (não grava nada, só mostra o que faria)
   --limite 50                                        (importa só os N primeiros de cada coleção,
                                                        útil para testar antes de rodar tudo)

O script é IDEMPOTENTE: pode ser rodado mais de uma vez. Usuários são casados
por e-mail; pedidos, produtos e notificações usam o campo `firebase_id`
(ID do documento original) para não duplicar em reimportações.
"""
import sys

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.hashers import make_password
from django.utils.dateparse import parse_datetime

from accounts.models import Usuario, SolicitacaoAcesso
from produtos.models import Produto
from pedidos.models import Pedido
from notificacoes.models import Notificacao


def _to_datetime(value):
    """Converte Timestamp do Firestore (ou string ISO) para datetime do Python."""
    if value is None:
        return None
    if hasattr(value, 'ToDatetime'):        # google.protobuf Timestamp
        return value.ToDatetime()
    if hasattr(value, 'timestamp'):          # google.cloud.firestore Timestamp / datetime
        try:
            import datetime
            if isinstance(value, datetime.datetime):
                return value
        except Exception:
            pass
    if isinstance(value, str):
        return parse_datetime(value)
    return None


def _get(doc, *keys, default=None):
    """Busca a primeira chave existente entre várias variações de nome (camelCase/snake_case)."""
    for k in keys:
        if k in doc and doc[k] not in (None, ''):
            return doc[k]
    return default


class Command(BaseCommand):
    help = 'Migra usuários, solicitações, produtos, pedidos e notificações do Firebase para o Postgres.'

    PASSOS = ['usuarios', 'solicitacoes', 'produtos', 'pedidos', 'notificacoes']

    def add_arguments(self, parser):
        parser.add_argument(
            '--service-account', required=True,
            help='Caminho para o JSON da service account do Firebase.',
        )
        parser.add_argument(
            '--senha-temporaria', default='TrocarSenha123!',
            help='Senha temporária atribuída a todos os usuários migrados (padrão: TrocarSenha123!).',
        )
        parser.add_argument(
            '--apenas', default=None,
            help='Lista separada por vírgula dos passos a rodar: ' + ','.join(self.PASSOS),
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Não grava nada no banco, apenas mostra o que seria importado.',
        )
        parser.add_argument(
            '--limite', type=int, default=None,
            help='Limita quantos documentos importar por coleção (útil para testar).',
        )

    def handle(self, *args, **opts):
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore
        except ImportError:
            raise CommandError(
                'firebase-admin não instalado. Rode: pip install firebase-admin'
            )

        cred_path = opts['service_account']
        if not firebase_admin._apps:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
        self.db = firestore.client()

        self.dry_run  = opts['dry_run']
        self.limite   = opts['limite']
        self.senha_temp = opts['senha_temporaria']
        passos = opts['apenas'].split(',') if opts['apenas'] else self.PASSOS

        self.stdout.write(self.style.WARNING(
            f"{'[DRY-RUN] ' if self.dry_run else ''}Migrando: {', '.join(passos)}"
        ))

        self.stats = {p: {'ok': 0, 'pulados': 0, 'erros': 0} for p in passos}
        self.emails_migrados = []

        if 'usuarios' in passos:
            self.migrar_usuarios()
        if 'solicitacoes' in passos:
            self.migrar_solicitacoes()
        if 'produtos' in passos:
            self.migrar_produtos()
        if 'pedidos' in passos:
            self.migrar_pedidos()
        if 'notificacoes' in passos:
            self.migrar_notificacoes()

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('── Resumo ──'))
        for passo, s in self.stats.items():
            self.stdout.write(f"  {passo:15s} ok={s['ok']:4d}  pulados={s['pulados']:4d}  erros={s['erros']:4d}")

        if self.emails_migrados and not self.dry_run:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                f"{len(self.emails_migrados)} usuário(s) migrado(s) com a senha temporária "
                f"'{self.senha_temp}'. Oriente-os a trocar a senha no primeiro login."
            ))

    # ── coleções ──────────────────────────────────────────────

    def _iter_collection(self, nomes):
        """Tenta várias grafias possíveis do nome da coleção até achar uma que exista."""
        for nome in nomes:
            docs = list(self.db.collection(nome).stream())
            if docs:
                self.stdout.write(f"  → coleção '{nome}': {len(docs)} documento(s)")
                return docs
        self.stdout.write(self.style.WARNING(
            f"  → nenhuma coleção encontrada entre: {nomes} (pulando)"
        ))
        return []

    def migrar_usuarios(self):
        self.stdout.write(self.style.MIGRATE_HEADING('Usuários'))
        docs = self._iter_collection(['usuarios', 'users'])
        if self.limite:
            docs = docs[:self.limite]

        for doc in docs:
            d = doc.to_dict() or {}
            email = _get(d, 'email')
            if not email:
                self.stats['usuarios']['erros'] += 1
                self.stderr.write(f'    doc {doc.id} sem email, pulando')
                continue

            nome      = _get(d, 'nome', 'name', default='')
            sobrenome = _get(d, 'sobrenome', 'lastName', default='')
            matricula = _get(d, 'matricula', default='')
            setor     = _get(d, 'setor', 'sector', default='')
            cargo     = _get(d, 'cargo', 'role', default='')
            is_staff  = bool(_get(d, 'isAdmin', 'is_staff', default=(cargo == 'Admin')))
            perms     = _get(d, 'perms', 'permissoes', default={}) or {}

            existe = Usuario.objects.filter(email=email).exists()
            if existe:
                self.stats['usuarios']['pulados'] += 1
                self.stdout.write(f'    já existe: {email}')
                continue

            self.stdout.write(f'    + {email} ({nome} {sobrenome}) setor={setor} cargo={cargo}')
            if not self.dry_run:
                Usuario.objects.create(
                    email=email,
                    nome=nome,
                    sobrenome=sobrenome,
                    matricula=matricula,
                    setor=setor,
                    cargo=cargo,
                    is_staff=is_staff,
                    is_approved=True,
                    perms=perms if isinstance(perms, dict) else {},
                    firebase_uid=doc.id,
                    password=make_password(self.senha_temp),
                )
                self.emails_migrados.append(email)
            self.stats['usuarios']['ok'] += 1

    def migrar_solicitacoes(self):
        self.stdout.write(self.style.MIGRATE_HEADING('Solicitações de acesso pendentes'))
        docs = self._iter_collection(['solicitacoes', 'solicitacoesAcesso', 'access_requests'])
        if self.limite:
            docs = docs[:self.limite]

        for doc in docs:
            d = doc.to_dict() or {}
            email = _get(d, 'email')
            status = _get(d, 'status', default='pendente')
            if not email or status != 'pendente':
                self.stats['solicitacoes']['pulados'] += 1
                continue
            if SolicitacaoAcesso.objects.filter(email=email, status='pendente').exists():
                self.stats['solicitacoes']['pulados'] += 1
                continue

            self.stdout.write(f'    + {email} (pendente)')
            if not self.dry_run:
                SolicitacaoAcesso.objects.create(
                    nome=_get(d, 'nome', default=''),
                    sobrenome=_get(d, 'sobrenome', default=''),
                    email=email,
                    matricula=_get(d, 'matricula', default=''),
                    senha_hash=make_password(self.senha_temp),
                    setor=_get(d, 'setor', default=''),
                    cargo=_get(d, 'cargo', default=''),
                    status='pendente',
                )
            self.stats['solicitacoes']['ok'] += 1

    def migrar_produtos(self):
        self.stdout.write(self.style.MIGRATE_HEADING('Produtos'))
        docs = self._iter_collection(['produtos', 'products'])
        if self.limite:
            docs = docs[:self.limite]

        for doc in docs:
            d = doc.to_dict() or {}
            nome = _get(d, 'nome', 'name')
            if not nome:
                self.stats['produtos']['erros'] += 1
                continue
            if Produto.objects.filter(firebase_id=doc.id).exists() or Produto.objects.filter(nome=nome).exists():
                self.stats['produtos']['pulados'] += 1
                continue

            self.stdout.write(f'    + {nome}')
            if not self.dry_run:
                Produto.objects.create(
                    nome=nome,
                    ativo=bool(_get(d, 'ativo', 'active', default=True)),
                    firebase_id=doc.id,
                )
            self.stats['produtos']['ok'] += 1

    def migrar_pedidos(self):
        self.stdout.write(self.style.MIGRATE_HEADING('Pedidos'))
        docs = self._iter_collection(['pedidos', 'emprestimos', 'loans'])
        if self.limite:
            docs = docs[:self.limite]

        usuarios_por_email = {u.email: u for u in Usuario.objects.all()}

        for doc in docs:
            d = doc.to_dict() or {}
            if Pedido.objects.filter(firebase_id=doc.id).exists():
                self.stats['pedidos']['pulados'] += 1
                continue

            sol_email = _get(d, 'solicitanteEmail', 'solicitante_email', default='')
            con_email = _get(d, 'concedenteEmail', 'concedente_email', default='')
            solicitante = usuarios_por_email.get(sol_email)
            concedente  = usuarios_por_email.get(con_email)

            produto = _get(d, 'produto', 'produtoNome', default='(sem nome)')
            self.stdout.write(f"    + {_get(d, 'codigo', default=doc.id)} — {produto}")

            if not self.dry_run:
                Pedido.objects.create(
                    codigo=_get(d, 'codigo', default='') or '',   # se vazio, save() gera um novo
                    numero_pedido=_get(d, 'numeroPedido', 'numero_pedido', default=''),
                    tipo=_get(d, 'tipo', default='Empréstimo'),
                    status=_get(d, 'status', default='pendente'),
                    produto=produto,
                    produto_concedente=_get(d, 'produtoConcedente', 'produto_concedente', default=''),
                    mg_solicitante=_get(d, 'mgSolicitante', 'mg_solicitante', default=''),
                    mg_concedente=_get(d, 'mgConcedente', 'mg_concedente', default=''),
                    localizacao=_get(d, 'localizacao', default=''),
                    solicitante=solicitante,
                    concedente=concedente,
                    solicitante_nome=_get(d, 'solicitanteNome', 'solicitante_nome', default=''),
                    solicitante_email=sol_email,
                    concedente_nome=_get(d, 'concedenteNome', 'concedente_nome', default=''),
                    concedente_email=con_email,
                    inicio_iso=_get(d, 'inicioISO', 'inicio_iso', default=None),
                    dev_iso=_get(d, 'devISO', 'dev_iso', default=None),
                    devolvido_em=_to_datetime(_get(d, 'devolvidoEm', 'devolvido_em')),
                    observacao=_get(d, 'observacao', default=''),
                    materiais=_get(d, 'materiais', default=[]) or [],
                    fotos=_get(d, 'fotos', default=[]) or [],
                    pdfs=_get(d, 'pdfs', default=[]) or [],
                    ocorrencia=_get(d, 'ocorrencia', default=None),
                    firebase_id=doc.id,
                )
            self.stats['pedidos']['ok'] += 1

    def migrar_notificacoes(self):
        self.stdout.write(self.style.MIGRATE_HEADING('Notificações'))
        docs = self._iter_collection(['notificacoes', 'notifications'])
        if self.limite:
            docs = docs[:self.limite]

        usuarios_por_email = {u.email: u for u in Usuario.objects.all()}

        for doc in docs:
            d = doc.to_dict() or {}
            if Notificacao.objects.filter(firebase_id=doc.id).exists():
                self.stats['notificacoes']['pulados'] += 1
                continue

            dest_email = _get(d, 'destinatarioEmail', 'destinatario_email', 'email', default='')
            destinatario = usuarios_por_email.get(dest_email)
            if not destinatario:
                self.stats['notificacoes']['erros'] += 1
                self.stderr.write(f'    doc {doc.id}: destinatário {dest_email!r} não encontrado, pulando')
                continue

            self.stdout.write(f"    + {_get(d, 'titulo', default=doc.id)} → {dest_email}")
            if not self.dry_run:
                Notificacao.objects.create(
                    destinatario=destinatario,
                    tipo=_get(d, 'tipo', default='sistema'),
                    titulo=_get(d, 'titulo', default=''),
                    mensagem=_get(d, 'mensagem', default=''),
                    lida=bool(_get(d, 'lida', 'read', default=False)),
                    pedido_id=_get(d, 'pedidoId', 'pedido_id', default=None),
                    firebase_id=doc.id,
                )
            self.stats['notificacoes']['ok'] += 1
