"""Manda o código do sistema para o GitHub. É o que o atualizar.ps1 chama no fim.

Sai sempre com código 0 quando o backup não está configurado ou está desligado: não é
erro, é a loja não ter pedido isso. Só erro de verdade no envio sai com código 1, para
a atualização poder avisar na tela sem deixar de ter terminado.
"""

from django.core.management.base import BaseCommand

from apps.backup import envio
from apps.backup.github import NaoDeuCerto
from apps.backup.models import ConfiguracaoDeBackup


class Command(BaseCommand):
    help = "Envia o código do sistema para o repositório configurado no GitHub."

    def add_arguments(self, analisador):
        analisador.add_argument(
            "--forcar", action="store_true",
            help="Envia mesmo com o envio automático desligado na tela.")

    def handle(self, *args, **opcoes):
        configuracao = ConfiguracaoDeBackup.atual()
        if not configuracao.configurado:
            self.stdout.write("Cópia do programa no GitHub não configurada; nada a enviar.")
            return
        if not configuracao.ativo and not opcoes["forcar"]:
            self.stdout.write("Envio automático desligado na tela Backup; nada a enviar.")
            return
        try:
            resultado = envio.enviar(configuracao=configuracao)
        except NaoDeuCerto as erro:
            self.stderr.write(f"Cópia do programa no GitHub não foi enviada: {erro}")
            raise SystemExit(1) from erro
        self.stdout.write(resultado.mensagem)
