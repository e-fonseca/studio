"""Limpa o que o sistema acumula sozinho: cópia do SET, fotos antigas e registros.

Sem argumento, só CONFERE e mostra o que achou: pode rodar a qualquer hora, não
apaga nada. Com --fazer, limpa. Quem roda sozinho é a tarefa \\Studio\\StudioHigienizacao,
todo dia de madrugada, pelo scripts\\higienizar.ps1.
"""

from django.core.management.base import BaseCommand

from apps.auditoria.servicos import registrar
from apps.core import higiene


class Command(BaseCommand):
    help = "Mostra o que o sistema tem para limpar e, com --fazer, limpa."

    def add_arguments(self, parser):
        parser.add_argument("--fazer", action="store_true",
                            help="Limpa de verdade. Sem isto, o comando só mostra o que achou.")
        parser.add_argument("--sem-arrumar", action="store_true",
                            help="Não roda o VACUUM no fim (o espaço só volta a ser usado na próxima vez).")

    def handle(self, *args, fazer=False, sem_arrumar=False, **opcoes):
        self.stdout.write("Higienização do sistema do Studio Industrial")
        if fazer:
            self.stdout.write("Limpando.")
        else:
            self.stdout.write("Conferindo: nada vai ser apagado. Para limpar de verdade, use --fazer.")
        self.stdout.write("")

        resultado = higiene.levantar(fazer=fazer, arrumar=not sem_arrumar)

        for tarefa in resultado.tarefas:
            if tarefa.tem_o_que_limpar:
                tamanho = f", {higiene.quanto(tarefa.bytes)}" if tarefa.bytes else ""
                marca = "limpo" if tarefa.feito else ("parado" if tarefa.aviso else "a limpar")
                self.stdout.write(f"{tarefa.nome}: {tarefa.quantos}{tamanho} ({marca})")
            else:
                self.stdout.write(f"{tarefa.nome}: nada a limpar")
            self.stdout.write(f"    {tarefa.explicacao}")
            if tarefa.detalhe:
                self.stdout.write(f"    {tarefa.detalhe}")
            if tarefa.aviso:
                self.stdout.write(f"    {tarefa.aviso}")

        self.stdout.write("")
        if resultado.banco_antes:
            # Sem comparar antes com depois de propósito: o arquivo do banco não
            # encolhe quando se apaga linha, e ele chega a ficar alguns MB maior
            # depois do VACUUM, que grava as contas novas. Quem lê "182 MB antes,
            # 183 MB depois" conclui que a limpeza não funcionou, e funcionou.
            self.stdout.write(
                f"Banco do sistema: {higiene.quanto(resultado.banco_depois or resultado.banco_antes)}. "
                "O arquivo não encolhe: o espaço que sai volta a ser usado pelo próprio banco."
            )
        self.stdout.write(
            "Não entra nesta limpeza: auditoria, ficha de fornecedor, pagamento previsto, "
            "inventário, extrato conferido e o backup do próprio sistema. Nada aqui toca no SET."
        )

        if not resultado.tem_o_que_limpar:
            self.stdout.write("Sistema limpo: não achei nada para apagar.")
            return
        if not fazer:
            espaco = f" e liberar {higiene.quanto(resultado.total_de_bytes)}" if resultado.total_de_bytes else ""
            quantos = higiene.numero(resultado.total_de_registros)
            self.stdout.write(f"Daria para apagar {quantos} registros{espaco}.")
            return

        registrar("sistema.higienizado", servico="core", depois={
            "registros": resultado.total_de_registros,
            "bytes": resultado.total_de_bytes,
            "banco_antes": resultado.banco_antes,
            "banco_depois": resultado.banco_depois,
            "tarefas": [t.nome for t in resultado.tarefas if t.feito],
        })
        for tarefa in resultado.avisos:
            self.stdout.write(self.style.WARNING(f"{tarefa.nome}: {tarefa.aviso}"))
        if resultado.aviso_do_banco:
            self.stdout.write(self.style.WARNING(resultado.aviso_do_banco))
        self.stdout.write(self.style.SUCCESS("Limpeza concluída."))
