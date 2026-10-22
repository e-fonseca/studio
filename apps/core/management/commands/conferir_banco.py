"""Confere se o banco tem todas as colunas que o programa espera.

Existe por causa de um erro real: uma migração já aplicada no servidor foi
editada depois para ganhar duas colunas. O Django guarda a migração pelo nome,
deu a migração como aplicada, nunca criou as colunas, e as telas quebravam com
'column ... does not exist' só quando alguém abria o painel.

O instalador roda este comando no fim da atualização: assim a diferença aparece
na hora, e não na primeira vez que a gerência abre a tela.
"""

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Compara as colunas de cada tabela com os campos do programa e lista o que falta."

    def add_arguments(self, parser):
        parser.add_argument("--falhar", action="store_true",
                            help="Termina com erro quando faltar alguma coluna (para o instalador).")

    def handle(self, *args, falhar=False, **opcoes):
        faltando = []
        with connection.cursor() as cursor:
            tabelas = set(connection.introspection.table_names(cursor))
            for modelo in apps.get_models():
                tabela = modelo._meta.db_table
                if tabela not in tabelas:
                    continue
                existentes = {c.name for c in connection.introspection.get_table_description(cursor, tabela)}
                esperadas = {
                    campo.column for campo in modelo._meta.local_fields if campo.concrete
                }
                for coluna in sorted(esperadas - existentes):
                    faltando.append(f"{tabela}.{coluna}")

        if not faltando:
            self.stdout.write("Banco conferido: todas as colunas esperadas existem.")
            return 0
        self.stdout.write("FALTAM COLUNAS NO BANCO:")
        for item in faltando:
            self.stdout.write(f"  {item}")
        self.stdout.write("Avise quem cuida do sistema: as telas que usam essas colunas vão dar erro.")
        if falhar:
            raise SystemExit(1)
        return 0
