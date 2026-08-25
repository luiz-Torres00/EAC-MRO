# EAC MRO — Backend Django

API REST para o sistema de controle de empréstimos EAC da MRO.

## Stack
- **Python 3.11+** + **Django 4.2**
- **Django REST Framework** — endpoints REST
- **SimpleJWT** — autenticação via Bearer token
- **PostgreSQL** — banco de dados (Railway)
- **Gunicorn** — servidor WSGI (produção)
- **WhiteNoise** — arquivos estáticos

## Setup local

```bash
# 1. Clone e crie venv
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 2. Instale dependências
pip install -r requirements.txt

# 3. Configure variáveis
cp .env.example .env
# Edite .env com sua DATABASE_URL e SECRET_KEY

# 4. Migrações
python manage.py migrate

# 5. Crie superusuário
python manage.py createsuperuser

# 6. Rode o servidor
python manage.py runserver
```

## Deploy no Railway

1. Crie um novo projeto no Railway
2. Adicione um serviço **PostgreSQL** — o Railway injeta `DATABASE_URL` automaticamente
3. Conecte este repositório
4. Adicione as variáveis de ambiente (veja `.env.example`)
5. O `Procfile` configura o start automático com Gunicorn

## Endpoints principais

| Método | URL | Descrição |
|--------|-----|-----------|
| POST | `/api/auth/login/` | Login — retorna JWT |
| POST | `/api/auth/refresh/` | Renova o token |
| GET | `/api/auth/me/` | Dados do usuário logado |
| POST | `/api/auth/solicitar/` | Solicitar acesso (público) |
| GET | `/api/auth/usuarios/` | Lista de usuários |
| GET/POST | `/api/pedidos/` | Listar / criar pedidos |
| GET/PATCH | `/api/pedidos/<id>/` | Detalhe / atualizar pedido |
| PATCH | `/api/pedidos/<id>/aprovar/` | Aprovar pedido |
| PATCH | `/api/pedidos/<id>/recusar/` | Recusar pedido |
| PATCH | `/api/pedidos/<id>/devolver/` | Devolver pedido |
| PATCH | `/api/pedidos/<id>/estender/` | Estender prazo |
| GET | `/api/produtos/` | Lista de produtos |
| GET | `/api/notificacoes/` | Notificações do usuário |

## Admin Django
Acesse `/admin/` para gerenciar usuários, pedidos e produtos via interface Django Admin.

## Migrando dados do Firebase

O projeto antigo usava Firebase Auth (login) + Firestore (`usuarios`, `produtos` e,
possivelmente, `pedidos`/`notificacoes` conforme a API Node). Para trazer esses dados
para o Postgres:

```bash
pip install -r requirements-migracao.txt

# baixe a chave da service account no Console do Firebase
# (Configurações do projeto → Contas de serviço → Gerar nova chave privada)
# e salve como firebase-service-account.json na raiz do projeto
# (o arquivo já está no .gitignore — nunca commite essa chave)

# rode primeiro em modo de teste, sem gravar nada:
python manage.py migrar_firestore --service-account firebase-service-account.json --dry-run

# se o preview parecer correto, rode de verdade:
python manage.py migrar_firestore \
  --service-account firebase-service-account.json \
  --senha-temporaria "TrocarSenha123!"
```

Pontos importantes:
- **Senhas não são recuperáveis.** O Firebase Auth guarda os hashes com o algoritmo
  scrypt proprietário do Google, incompatível com o Django. Todo usuário migrado recebe
  a senha temporária informada em `--senha-temporaria` e deve trocá-la no primeiro
  login — avise a equipe antes de divulgar o novo sistema.
- O script é **idempotente**: pode ser rodado de novo sem duplicar dados (usuários são
  casados por e-mail; pedidos/produtos/notificações usam o ID do documento original do
  Firestore, salvo no campo `firebase_id`/`firebase_uid`).
- Use `--apenas usuarios,produtos` para rodar só algumas etapas, e `--limite 20` para
  testar com poucos registros antes de importar tudo.
- Os nomes de coleção no Firestore podem variar conforme o código antigo (`pedidos` vs
  `emprestimos`, por exemplo) — o script tenta algumas variações automaticamente; se a
  sua coleção tiver outro nome, edite `_iter_collection(...)` em
  `accounts/management/commands/migrar_firestore.py`.
