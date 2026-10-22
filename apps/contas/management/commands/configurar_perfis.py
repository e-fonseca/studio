from django.core.management.base import BaseCommand

from apps.contas.servicos import configurar_perfis


class Command(BaseCommand):
    help = "Cria ou atualiza os perfis (Gerência, Compras, Estoque, Operadores, Consulta) e suas permissões."

    def handle(self, *args, **opcoes):
        for nome, total in configurar_perfis().items():
            self.stdout.write(f"{nome}: {total} permissões")
