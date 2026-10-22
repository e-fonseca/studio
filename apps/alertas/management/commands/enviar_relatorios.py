"""Manda os relatórios por e-mail e avisa no Telegram. É o que a tarefa agendada chama.

A tarefa roda **de hora em hora** com `--rotina devido`, e é o sistema que decide o que
já passou da hora e ainda não saiu (ver apps/alertas/agenda.py). Assim o horário mora na
tela de alertas e em nenhum outro lugar: mudar a hora ali vale no mesmo dia, e servidor
desligado às 7h entrega o relatório quando ligar em vez de pular o dia.

Os outros valores de `--rotina` existem para rodar à mão no servidor quando alguém
reclamar que não recebeu — é daí que vem o `--forcar` e o `--mesmo-desligado`.

Desde a 1.24.0 são dois canais, pedido do Edson em 11/10/2026. Eles são independentes:
o Telegram sai com o e-mail desligado e vice-versa, cada um tem o seu interruptor na
tela, e cada um fica devendo por conta própria (apps/alertas/agenda.py). O relatório é
montado uma vez e serve aos dois: algumas contas passam por onze mil produtos.

Sai com código 0 mesmo quando o e-mail falha: a tarefa agendada marcada como "com erro"
no Windows não diz nada a ninguém, e quem precisa saber do erro é a tela de alertas,
onde ele fica escrito em português. Só erro de uso (rotina que não existe) devolve
código diferente.
"""

import logging

from django.core.management.base import BaseCommand, CommandError

from apps.alertas import agenda, envio, relatorios, telegram
from apps.alertas.models import (DIARIAS, SEMANAIS, Canal, ConfiguracaoDeEmail,
                                 ConfiguracaoDeTelegram, Rotina)

GRUPOS = {
    "diaria": [r.value for r in DIARIAS],
    "semanal": [r.value for r in SEMANAIS],
    "todas": [r.value for r in DIARIAS + SEMANAIS],
}
DEVIDO = "devido"

registrador = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Manda por e-mail os relatórios de alertas (contas, estoque, sugestão de compra)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--rotina", default=DEVIDO,
            help=f"{DEVIDO} (o que já passou da hora na tela), diaria, semanal, todas, "
                 "ou o nome de um relatório: " + ", ".join(GRUPOS["todas"]),
        )
        parser.add_argument(
            "--forcar", action="store_true",
            help="Manda mesmo sem notícia. Sem isto, dia sem novidade não gera e-mail.",
        )
        parser.add_argument(
            "--mesmo-desligado", action="store_true",
            help="Ignora a chave 'mandar os relatórios' da tela. Para conferência no servidor.",
        )

    def _conferir(self, rotina):
        """Nome errado é erro de uso, e tem que estourar antes de qualquer envio.

        Conferido aqui, separado de `_nomes`, porque `_nomes` passou a ser chamado uma
        vez por canal e depois dos interruptores: um nome inválido com os dois canais
        desligados sairia como "nada enviado", escondendo o erro de digitação.
        """
        if rotina != DEVIDO and rotina not in GRUPOS and rotina not in GRUPOS["todas"]:
            raise CommandError(
                f"Não conheço a rotina '{rotina}'. Use {DEVIDO}, diaria, semanal, todas, ou um de: "
                + ", ".join(GRUPOS["todas"])
            )

    def _nomes(self, rotina, configuracao, canal=Canal.EMAIL):
        if rotina == DEVIDO:
            return agenda.devidas(configuracao, canal=canal)
        if rotina in GRUPOS:
            return GRUPOS[rotina]
        return [rotina]

    def _cuidar_do_backup(self):
        """Reenvia o código quando a cópia no GitHub ficou velha, e lê a validade do token.

        Mora aqui porque esta é a única tarefa do Windows que acorda de hora em hora, e
        porque ela roda ANTES dos interruptores de e-mail e Telegram: o reenvio é
        automação, não aviso, e tem que acontecer mesmo numa loja que nunca configurou
        e-mail nenhum. Nada aqui levanta erro — derrubar esta tarefa por causa do GitHub
        deixaria a loja sem os relatórios.
        """
        from apps.backup import vigia  # noqa: PLC0415

        vigia.anotar_validade_do_token()
        resultado = vigia.reenviar_se_atrasado()
        if resultado is not None:
            self.stdout.write(f"Backup no GitHub: {resultado.mensagem}")

    def _adiantar_as_contas_da_abertura(self):
        """Deixa a tela de abertura pronta, para quem entrar no sistema não esperar por ela.

        Mora aqui pelo mesmo motivo que `_cuidar_do_backup`: esta é a única tarefa do
        Windows que acorda de hora em hora, e ela roda ANTES dos interruptores de e-mail
        e Telegram, porque adiantar conta é automação, não aviso.

        A chave do cache carrega o DIA (apps/painel/servicos.py), porque a Visão geral
        conta conta vencida e conta a vencer, e isso vira à meia-noite sem ninguém tocar
        em nada. A sincronização das 08:30 já adianta a conta do dia, mas quem abre o
        sistema ANTES dela pagaria os ~2 s. Como aqui a conta já está feita em 23 das 24
        voltas, isto custa uma leitura de arquivo; só a primeira volta depois da
        meia-noite calcula de verdade, e quem espera é a tarefa, não a pessoa.

        Nada aqui levanta erro: derrubar esta tarefa por causa de um cálculo de tela
        deixaria a loja sem os relatórios.
        """
        try:
            from apps.painel.aquecer import aquecer_a_foto_de_hoje  # noqa: PLC0415

            gasto = aquecer_a_foto_de_hoje()
        except Exception:  # noqa: BLE001 - ver o último parágrafo acima
            registrador.exception("Não consegui adiantar as contas da abertura")
            return
        if gasto:
            self.stdout.write(f"Contas da abertura adiantadas em {gasto:.1f}s.")

    def handle(self, *args, rotina, forcar, mesmo_desligado, **opcoes):
        self._conferir(rotina)
        self._cuidar_do_backup()
        self._adiantar_as_contas_da_abertura()
        configuracao = ConfiguracaoDeEmail.atual()
        no_telegram = ConfiguracaoDeTelegram.atual()
        por_email = configuracao.ativo or mesmo_desligado
        por_telegram = no_telegram.ativo or mesmo_desligado

        if not por_email and not por_telegram:
            self.stdout.write(
                "O envio de relatórios está desligado na tela de alertas, por e-mail e por "
                "Telegram. Nada foi enviado.")
            return
        if por_email and configuracao.o_que_falta:
            self.stdout.write(
                "Falta preencher na tela de alertas, para o e-mail: "
                + ", ".join(configuracao.o_que_falta) + "."
            )
        if por_telegram and no_telegram.o_que_falta:
            self.stdout.write(
                "Falta preencher na tela de alertas, para o Telegram: "
                + ", ".join(no_telegram.o_que_falta) + "."
            )

        # Um relatório montado serve aos dois canais. `_nomes` responde por canal, porque
        # cada um fica devendo por conta própria.
        por_email = self._nomes(rotina, configuracao, Canal.EMAIL) if por_email else []
        por_telegram = self._nomes(rotina, configuracao, Canal.TELEGRAM) if por_telegram else []
        if not por_email and not por_telegram:
            self.stdout.write("Nenhum relatório devido agora.")
            return

        montados = {}
        for nome in dict.fromkeys(list(por_email) + list(por_telegram)):
            montados[nome] = relatorios.montar(nome)

        for nome in por_email:
            self._contar("E-mail", Rotina(nome).label, envio.enviar_rotina(
                nome, configuracao, disparado_por=f"tarefa {rotina}", forcar=forcar,
                relatorio=montados[nome],
            ))
        for nome in por_telegram:
            self._contar("Telegram", Rotina(nome).label, telegram.enviar_rotina(
                nome, no_telegram, disparado_por=f"tarefa {rotina}", forcar=forcar,
                relatorio=montados[nome],
            ))

    def _contar(self, canal, rotulo, registro):
        """Uma linha por tentativa, no texto que fica no log da tarefa agendada."""
        if registro.deu_certo:
            self.stdout.write(f"{canal} · {rotulo}: enviado para {registro.destinatarios}. {registro.resumo}")
        elif registro.sem_noticia:
            self.stdout.write(f"{canal} · {rotulo}: sem novidade hoje, não foi mandado. {registro.resumo}")
        else:
            self.stdout.write(f"{canal} · {rotulo}: não enviado. {registro.erro}")
