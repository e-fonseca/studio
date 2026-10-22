from django.core.management.base import BaseCommand
from django.db import transaction

from apps.auditoria.servicos import registrar
from apps.processos.models import Processo
from apps.processos.roteiro import PROCESSOS_INICIAIS


class Command(BaseCommand):
    help = "Cria no quadro os processos a levantar (estado “A levantar”). Pode rodar mais de uma vez."

    def add_arguments(self, parser):
        parser.add_argument("--fonte", default="Bárbara", help="Quem conhece o processo hoje.")
        parser.add_argument("--prazo", default=None, help="Prazo de coleta (AAAA-MM-DD), ex.: último dia do aviso.")

    @transaction.atomic
    def handle(self, *args, fonte, prazo, **opcoes):
        criados = 0
        for titulo, area, criticidade in PROCESSOS_INICIAIS:
            processo, novo = Processo.objects.get_or_create(
                titulo=titulo, area=area,
                defaults={"criticidade": criticidade, "fonte_conhecimento": fonte, "prazo_coleta": prazo},
            )
            if novo:
                criados += 1
                registrar("processo.criado", servico="carregar_roteiro", recurso=processo,
                          depois={"titulo": titulo, "area": area, "criticidade": criticidade})
        self.stdout.write(f"{criados} processo(s) criado(s); {len(PROCESSOS_INICIAIS) - criados} já existia(m).")
