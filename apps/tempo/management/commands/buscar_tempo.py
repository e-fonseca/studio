"""Busca o tempo dos últimos dias e grava no sistema.

É este comando que a tarefa agendada do Windows roda uma vez por dia. Rodar à mão é
igual. Nunca escreve por cima do que alguém da loja anotou na tela.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.auditoria.servicos import registrar
from apps.tempo import servicos
from apps.tempo.fonte import ErroDoTempo, FaltaOLugar
from apps.tempo.models import ConfiguracaoDoTempo


class Command(BaseCommand):
    help = ("Busca o tempo dos últimos dias num serviço aberto de meteorologia e grava "
            "no sistema, para cruzar com a venda de cada dia.")

    def add_arguments(self, parser):
        parser.add_argument("--dias", type=int, default=7,
                            help="Quantos dias para trás buscar (padrão 7).")
        parser.add_argument("--forcar", action="store_true",
                            help="Busca mesmo com a busca automática desligada na tela.")

    def handle(self, *args, dias=7, forcar=False, **opcoes):
        configuracao = ConfiguracaoDoTempo.atual()
        if not configuracao.ativo and not forcar:
            self.stdout.write("A busca automática do tempo está desligada na tela de "
                              "Tempo e venda. Nada a fazer.")
            return
        try:
            novos, atualizados, respeitados = servicos.atualizar(configuracao, dias=dias)
        except FaltaOLugar as erro:
            # Campo em branco não é falha: a tarefa termina bem e a tela diz o que falta.
            # Terminando em erro, o Windows marcaria a tarefa como quebrada todo dia.
            self.stdout.write(str(erro))
            return
        except ErroDoTempo as erro:
            registrar("tempo.busca", servico="tempo", resultado="falha",
                      depois={"erro": str(erro)[:200]})
            raise CommandError(str(erro)) from erro
        registrar("tempo.busca", servico="tempo",
                  depois={"novos": novos, "atualizados": atualizados,
                          "escritos_a_mao_respeitados": respeitados})
        self.stdout.write(
            f"Tempo atualizado: {novos} dia(s) novo(s), {atualizados} atualizado(s), "
            f"{respeitados} mantido(s) como alguém da loja escreveu."
        )
