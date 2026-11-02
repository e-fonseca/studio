from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.contas.autorizacao import NaoPode
from apps.contas.servicos import desligar_usuario


class Command(BaseCommand):
    help = "Bloqueia um usuário desligado e encerra suas sessões abertas."

    def add_arguments(self, parser):
        parser.add_argument("usuario")
        parser.add_argument("--motivo", required=True)

    def handle(self, *args, usuario, motivo, **opcoes):
        try:
            alvo = get_user_model().objects.get(username=usuario)
        except get_user_model().DoesNotExist as erro:
            raise CommandError(f"Usuário {usuario} não encontrado.") from erro
        try:
            sessoes = desligar_usuario(alvo, motivo=motivo)
        except NaoPode as erro:
            raise CommandError(str(erro)) from erro
        self.stdout.write(f"{usuario} bloqueado; {sessoes} sessão(ões) encerrada(s).")
