import os

from django.core.management.base import BaseCommand

from accounts.models import Usuario


class Command(BaseCommand):
    help = "Cria/atualiza o usuario admin a partir de ADMIN_EMAIL / ADMIN_PASSWORD / ADMIN_NOME."

    def handle(self, *args, **options):
        email = os.environ.get("ADMIN_EMAIL")
        senha = os.environ.get("ADMIN_PASSWORD")
        nome  = os.environ.get("ADMIN_NOME", "Administrador")

        if not email or not senha:
            self.stdout.write("ADMIN_EMAIL / ADMIN_PASSWORD nao configurados - pulando criacao do admin.")
            return

        usuario, criado = Usuario.objects.get_or_create(
            email=email,
            defaults={"nome": nome},
        )
        usuario.nome         = usuario.nome or nome
        usuario.is_staff     = True
        usuario.is_superuser = True
        usuario.is_approved  = True
        usuario.is_active    = True
        usuario.set_password(senha)
        usuario.save()

        if criado:
            self.stdout.write(self.style.SUCCESS(f"Admin criado: {email}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Admin ja existia - senha/permissoes atualizadas: {email}"))
