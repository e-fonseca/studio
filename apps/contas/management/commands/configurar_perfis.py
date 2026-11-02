from django.core.management.base import BaseCommand

from apps.contas.servicos import configurar_perfis


class Command(BaseCommand):
    help = ("Cria os perfis que vêm com o sistema e entrega a cada um o padrão dele, uma vez só. "
            "Não desfaz o que a gerência mudou na tela Perfis e permissões. Roda a cada "
            "atualização, depois do migrate; rodar de novo não duplica nada.")

    def handle(self, *args, **opcoes):
        for nome, total in configurar_perfis().items():
            self.stdout.write(f"{nome}: {total} permissões")
