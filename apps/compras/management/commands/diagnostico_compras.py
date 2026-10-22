import dataclasses
import hashlib
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.auditoria.servicos import registrar
from apps.compras.calculos import Parametros, calcular, resumir
from apps.compras.planilha import ErroPlanilha, escrever_relatorio, ler


def _reais(valor):
    texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


class Command(BaseCommand):
    help = ("Lê a planilha de diagnóstico (montada a partir dos relatórios do SET) e gera o relatório "
            "de compra inteligente. Só lê o arquivo: não acessa o SET nem grava estoque.")

    def add_arguments(self, parser):
        parser.add_argument("arquivo", help="Planilha CSV ou XLSX no modelo de docs/modelos/.")
        parser.add_argument("--dias", type=int, required=True,
                            help="Dias em que a loja abriu no período de vendas da planilha.")
        parser.add_argument("--data-corte", required=True, help="Data do estoque exportado (AAAA-MM-DD).")
        parser.add_argument("--saida", required=True, help="Arquivo CSV do relatório a gerar.")
        parser.add_argument("--dias-seguranca", default="7")
        parser.add_argument("--revisao-dias", type=int, default=7)
        parser.add_argument("--excesso-dias", type=int, default=180)
        parser.add_argument("--aceitar-com-erros", action="store_true",
                            help="Gera o relatório mesmo com linhas recusadas (o resumo avisa).")

    def handle(self, *args, arquivo, dias, data_corte, saida, dias_seguranca, revisao_dias, excesso_dias,
               aceitar_com_erros, **opcoes):
        if dias <= 0:
            raise CommandError("--dias precisa ser maior que zero.")
        try:
            corte = date.fromisoformat(data_corte)
        except ValueError as erro:
            raise CommandError("--data-corte deve estar no formato AAAA-MM-DD.") from erro
        try:
            itens, erros = ler(arquivo)
        except ErroPlanilha as erro:
            raise CommandError(str(erro)) from erro

        recusadas = [e for e in erros if not e[1].startswith("aviso:")]
        for linha, mensagem in erros:
            self.stderr.write(f"Linha {linha}: {mensagem}")
        if recusadas and not aceitar_com_erros:
            raise CommandError(f"{len(recusadas)} linha(s) recusada(s). Corrija a planilha ou use "
                               "--aceitar-com-erros para gerar um relatório parcial.")

        parametros = Parametros(horizonte_revisao_dias=revisao_dias,
                                dias_seguranca=Decimal(dias_seguranca.replace(",", ".")),
                                excesso_cobertura_dias=excesso_dias)
        hoje = timezone.localdate()
        resultados = [calcular(dataclasses.replace(i, dias_janela=dias), parametros, corte, hoje) for i in itens]
        escrever_relatorio(resultados, saida)
        r = resumir(resultados)

        registrar("compras.diagnostico_gerado", servico="diagnostico_compras", depois={
            "arquivo": Path(arquivo).name,
            "sha256": hashlib.sha256(Path(arquivo).read_bytes()).hexdigest(),
            "data_corte": corte.isoformat(), "dias": dias, "itens": r.itens, "linhas_recusadas": len(recusadas),
        })

        self.stdout.write(f"Diagnóstico de compras. Dados até {corte:%d/%m/%Y}, vendas de {dias} dias.")
        if recusadas:
            self.stdout.write(f"ATENÇÃO: relatório parcial, {len(recusadas)} linha(s) ficaram de fora.")
        self.stdout.write(f"Itens analisados: {r.itens} ({r.itens_sem_custo} sem custo informado, fora dos valores)")
        self.stdout.write(f"Valor em estoque: {_reais(r.valor_estoque)}")
        self.stdout.write(f"Parado sem venda no período: {_reais(r.valor_sem_giro)}")
        self.stdout.write(f"Acima de {excesso_dias} dias de cobertura: {_reais(r.valor_excesso)}")
        self.stdout.write(f"Comprado no período e ainda sobrando: {_reais(r.valor_comprado_acima)}")
        self.stdout.write(f"Itens em falta que vendem: {r.itens_em_falta}")
        self.stdout.write(f"Itens para comprar agora: {r.itens_para_comprar} (custo estimado "
                          f"{_reais(r.valor_compra_sugerida)})")
        for situacao, total in sorted(r.por_situacao.items()):
            self.stdout.write(f"  {situacao}: {total}")
        self.stdout.write(f"Relatório por item: {saida}")
