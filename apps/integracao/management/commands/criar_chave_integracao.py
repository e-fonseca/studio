"""Cria a chave que o agente da casa usa para falar com o sistema.

    python manage.py criar_chave_integracao agente-da-casa

A chave aparece UMA vez, aqui. O sistema guarda só o resumo dela: perdeu, cria outra e
desliga a velha com --desligar.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.auditoria.servicos import registrar
from apps.integracao.models import ChaveDeIntegracao


class Command(BaseCommand):
    help = "Cria (ou desliga) a chave de integração do agente que opera o Trello e o Kommo."

    def add_arguments(self, parser):
        parser.add_argument("nome")
        parser.add_argument("--desligar", action="store_true", help="Desliga a chave com este nome.")

    def handle(self, nome, desligar=False, **_):
        if desligar:
            if not ChaveDeIntegracao.objects.filter(nome=nome).update(ativa=False):
                raise CommandError(f"Não existe chave com o nome {nome}.")
            registrar("integracao.chave_desligada", servico="linha de comando", recurso_rotulo=nome)
            self.stdout.write(f"Chave {nome} desligada.")
            return
        if ChaveDeIntegracao.objects.filter(nome=nome).exists():
            raise CommandError(f"Já existe chave com o nome {nome}. Desligue-a ou use outro nome.")
        registro, chave = ChaveDeIntegracao.criar(nome)
        registrar("integracao.chave_criada", servico="linha de comando", recurso=registro)
        self.stdout.write("Guarde esta chave no computador do agente. Ela não aparece de novo:\n")
        self.stdout.write(chave)
