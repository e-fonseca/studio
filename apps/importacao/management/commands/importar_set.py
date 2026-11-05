"""Importa os dados do SET a partir da cópia do backup.

É este comando que a tarefa automática do Windows roda toda noite, depois do
backup do SET. Rodar à mão é igual: o resultado aparece no painel do sistema.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.importacao import servicos
from apps.importacao.models import Importacao


class Command(BaseCommand):
    help = ("Lê uma cópia do backup do banco do SET e atualiza os números do painel. "
            "Não escreve nada no SET: copia o arquivo e lê a cópia.")

    def add_arguments(self, parser):
        parser.add_argument(
            "--arquivo",
            help="Backup a importar (.FDB ou .FBK), ou a pasta onde ele é salvo. "
                 "Sem isto, usa STUDIO_SET_BACKUP.",
        )
        parser.add_argument("--automatica", action="store_true",
                            help="Marca a importação como executada pela tarefa agendada.")
        parser.add_argument("--forcar", action="store_true",
                            help="Lê o backup mais recente de novo mesmo sendo o mesmo da "
                                 "importação anterior, em vez de terminar como Sem backup novo. "
                                 "Não passa por cima de arquivo quebrado.")
        parser.add_argument("--sem-log", action="store_true",
                            help="Não repete o log passo a passo na saída do comando.")

    def handle(self, *args, arquivo=None, automatica=False, sem_log=False, forcar=False, **opcoes):
        importacao = servicos.executar(arquivo=arquivo, automatica=automatica, forcar=forcar)
        # O log também vai para a saída do comando: assim a tarefa agendada o guarda
        # em logs\importacao.log e a mesma informação fica no arquivo e na tela.
        if not sem_log:
            for linha in importacao.linhas_do_log:
                self.stdout.write(linha)
        if importacao.situacao == Importacao.Situacao.SEM_NOVIDADE:
            self.stdout.write(importacao.mensagem)
            return
        if importacao.situacao != Importacao.Situacao.CONCLUIDA:
            raise CommandError(f"Importação falhou: {importacao.mensagem}")
        self.stdout.write(
            f"Importação concluída: {importacao.produtos} produtos, "
            f"dados até {importacao.data_corte:%d/%m/%Y}, "
            f"{importacao.dias_abertos_12m} dias com venda em 12 meses "
            f"({importacao.duracao_segundos}s)."
        )
