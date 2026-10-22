#!/usr/bin/env python3
"""Cruza os números das telas entre si e procura o que não fecha. Só de leitura.

A pergunta: o que a tela de vendas do dia diz bate com o Dashboard, com a Visão geral e
com o que está gravado? Divergência aqui é defeito de cálculo ou consulta sem filtro de
importação — os dois erros que mais custam neste sistema.

    python3 .claude/skills/cabana-reporting-system/scripts/checar-consistencia.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import Placar, ligar, linha, reais, titulo  # noqa: E402

ligar()

from decimal import Decimal  # noqa: E402

from django.db.models import Count, Q, Sum  # noqa: E402

from apps.importacao import servicos  # noqa: E402
from apps.importacao.models import ItemVendaImportada, VendaImportada  # noqa: E402
from apps.painel import dashboard, vendas_do_dia  # noqa: E402

placar = Placar()
importacao = servicos.ultima_concluida()
if importacao is None:
    print("Nenhuma importação concluída.")
    raise SystemExit(1)

titulo("Toda consulta filtra pela importação?")
fotos = VendaImportada.objects.values("importacao").annotate(n=Count("id")).count()
linha("fotos de venda no banco", fotos)
do_dia = vendas_do_dia.calcular(importacao)
if do_dia.dia is None:
    print("  A importação não tem venda nenhuma.")
    raise SystemExit(placar.fechar())

solto = ItemVendaImportada.objects.filter(venda__data=do_dia.dia).aggregate(
    soma=Sum("valor_total"))["soma"] or Decimal("0")
desta = ItemVendaImportada.objects.filter(
    venda__importacao=importacao, venda__data=do_dia.dia).aggregate(
    soma=Sum("valor_total"))["soma"] or Decimal("0")
linha(f"itens de {do_dia.dia:%d/%m/%Y} em todas as fotos", reais(solto))
linha("itens do mesmo dia nesta foto", reais(desta))
placar.conferir(do_dia.faturamento == desta,
                "a tela soma só a foto da última importação",
                f"tela {reais(do_dia.faturamento)}")
com_itens = (ItemVendaImportada.objects.filter(venda__data=do_dia.dia)
             .values("venda__importacao").distinct().count())
if com_itens > 1:
    placar.conferir(solto > desta,
                    "as fotos com item estão separadas no banco", f"{com_itens} fotos")
else:
    placar.avisar("só uma foto tem item de venda",
                  "normal logo depois de atualizar para a 1.24.0")

titulo(f"O dia {do_dia.dia:%d/%m/%Y}, como a tela mostra")
linha("vendido", reais(do_dia.faturamento))
linha("custo", f"{reais(do_dia.custo)} (da venda {reais(do_dia.custo_do_dia)}, "
               f"estimado {reais(do_dia.custo_estimado)})")
linha("sobrou", reais(do_dia.lucro))
linha("margem", f"{do_dia.margem}%" if do_dia.margem is not None else "—")
linha("cupons", f"{do_dia.cupons} somando {reais(do_dia.total_dos_cupons)}")
if do_dia.tem_estimativa:
    linha("estimado pelo cadastro",
          f"{do_dia.produtos_estimados} de {do_dia.itens} itens, {do_dia.fatia_estimada}% do dia")
if do_dia.produtos_sem_custo:
    linha("sem custo nenhum",
          f"{do_dia.produtos_sem_custo} itens, {reais(do_dia.valor_sem_custo)}")

titulo("As contas fecham entre si?")
soma_das_linhas = sum((l.valor for l in do_dia.linhas), Decimal("0"))
placar.conferir(soma_das_linhas == do_dia.faturamento,
                "a soma das linhas é igual ao faturamento do dia",
                f"{reais(soma_das_linhas)}")
placar.conferir(do_dia.valor_do_dia + do_dia.valor_estimado + do_dia.valor_sem_custo
                == do_dia.faturamento,
                "as três bases de custo cobrem o dia inteiro")
placar.conferir(do_dia.lucro == do_dia.valor_com_custo - do_dia.custo,
                "sobrou = vendido com custo − custo")
negativos = [l for l in do_dia.linhas if l.margem is not None and l.margem > 100]
placar.conferir(not negativos, "nenhuma margem acima de 100%",
                "margem acima de 100% é custo zerado entrando na conta")
if do_dia.desconto_no_fechamento:
    placar.avisar(
        "a soma dos itens e o total dos cupons diferem",
        f"{reais(do_dia.desconto_no_fechamento)} de desconto ou acréscimo no fechamento")

titulo("A margem do dia conversa com a margem de 12 meses?")
painel = dashboard.montar(importacao)
margens = [k for k in painel.kpis_do_estoque + painel.kpis_da_venda if k.chave == "margem"]
if margens and do_dia.margem is not None:
    da_loja = margens[0].valor
    linha("margem de 12 meses (Dashboard)", f"{da_loja}%")
    linha("margem do dia", f"{do_dia.margem}%")
    placar.conferir(abs(Decimal(str(do_dia.margem)) - Decimal(str(da_loja))) < 40,
                    "a margem do dia não está num mundo diferente da do ano",
                    "diferença grande pede olhar o custo estimado")
else:
    placar.avisar("sem margem para comparar")

titulo("Prejuízo: o que é real e o que é estimativa")
confirmado = [l for l in do_dia.linhas if l.prejuizo_confirmado]
estimado = [l for l in do_dia.linhas if l.prejuizo and not l.prejuizo_confirmado]
linha("vendidos abaixo do custo da venda", len(confirmado))
linha("prejuízo só na estimativa (não vira alarme)", len(estimado))
for item in confirmado[:5]:
    print(f"    {item.descricao[:40]}: vendeu {reais(item.valor)}, custou {reais(item.custo)}")

raise SystemExit(placar.fechar())
