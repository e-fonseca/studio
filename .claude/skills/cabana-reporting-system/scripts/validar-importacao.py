#!/usr/bin/env python3
"""Confere a última importação concluída: só de leitura, não grava nada.

Responde, sem abrir tela nenhuma: a foto está inteira? o que o SET deixou de gravar? a
foto anterior continua separada desta? É o primeiro script a rodar quando alguém
desconfia de um número.

    python3 .claude/skills/cabana-reporting-system/scripts/validar-importacao.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import Placar, ligar, linha, reais, titulo  # noqa: E402

ligar()

from django.db.models import Count, Sum  # noqa: E402

from apps.importacao import servicos  # noqa: E402
from apps.importacao.models import (CompraImportada, Importacao, ItemVendaImportada,  # noqa: E402
                                    ProdutoImportado, VendaImportada)

placar = Placar()

titulo("A última importação concluída")
ultima = servicos.ultima_concluida()
if ultima is None:
    print("  Nenhuma importação concluída. Rode a importação antes de conferir relatório.")
    raise SystemExit(1)

linha("quando", f"{ultima.concluida_em:%d/%m/%Y %H:%M}")
linha("dia dos dados", f"{ultima.data_corte:%d/%m/%Y}" if ultima.data_corte else "—")
linha("arquivo", ultima.arquivo or "—")
linha("forçada", "sim" if getattr(ultima, "forcada", False) else "não")

titulo("A foto está inteira?")
produtos = ProdutoImportado.objects.filter(importacao=ultima).count()
vendas = VendaImportada.objects.filter(importacao=ultima).count()
itens = ItemVendaImportada.objects.filter(venda__importacao=ultima).count()
compras = CompraImportada.objects.filter(importacao=ultima).count()
placar.conferir(ultima.data_corte is not None, "a importação tem dia dos dados")
placar.conferir(produtos > 0, "tem produto", f"{produtos:,}".replace(",", "."))
placar.conferir(vendas > 0, "tem venda", f"{vendas:,}".replace(",", "."))
placar.conferir(itens > 0, "tem item de venda (a relação do dia depende dele)",
                f"{itens:,}".replace(",", "."))
placar.conferir(compras > 0, "tem compra", f"{compras:,}".replace(",", "."))
placar.conferir(
    ProdutoImportado.objects.filter(importacao=ultima, codigo="").count() == 0,
    "nenhum produto sem código")

titulo("O que o SET deixou de gravar")
sem_custo = ItemVendaImportada.objects.filter(venda__importacao=ultima,
                                              custo_total__isnull=True).count()
linha("itens de venda sem custo", f"{sem_custo} de {itens}")
if itens:
    fatia = sem_custo * 100 / itens
    linha("fatia sem custo", f"{fatia:.1f}%")
    placar.conferir(fatia < 25, "menos de um quarto dos itens sem custo",
                    "acima disso o lucro do dia vira estimativa")
produtos_sem_custo = ProdutoImportado.objects.filter(importacao=ultima, custo__lte=0).count()
linha("produtos com custo zerado no cadastro", produtos_sem_custo)

titulo("A foto anterior continua separada?")
anteriores = list(Importacao.objects.filter(
    situacao=Importacao.Situacao.CONCLUIDA).order_by("-concluida_em")[:2])
if len(anteriores) < 2:
    placar.avisar("só existe uma importação", "não há com o que comparar ainda")
else:
    nova, velha = anteriores
    por_foto = (VendaImportada.objects.filter(importacao__in=[nova, velha])
                .values("importacao").annotate(n=Count("id"), soma=Sum("valor")))
    for registro in por_foto:
        qual = "nova" if registro["importacao"] == nova.pk else "anterior"
        linha(f"vendas na foto {qual}", f"{registro['n']} somando {reais(registro['soma'])}")
    itens_velhos = ItemVendaImportada.objects.filter(venda__importacao=velha).count()
    itens_novos = ItemVendaImportada.objects.filter(venda__importacao=nova).count()
    if itens_velhos or not VendaImportada.objects.filter(importacao=velha).exists():
        placar.conferir(True, "a foto anterior guarda os itens dela",
                        f"{itens_velhos} lá, {itens_novos} aqui")
    else:
        # Acontece uma vez, na primeira importação depois da 1.24.0: a foto de antes foi
        # lida por um sistema que ainda não trazia item de venda.
        placar.avisar("a foto anterior não tem item de venda",
                      "normal se ela foi importada antes da versão 1.24.0")

titulo("LGPD: nada de cliente na venda")
campos = {c.name for c in VendaImportada._meta.get_fields()}
campos |= {c.name for c in ItemVendaImportada._meta.get_fields()}
proibidos = sorted(c for c in campos
                   if any(p in c for p in ("cpf", "comprador", "cliente", "nomecli")))
placar.conferir(not proibidos, "nenhum campo de cliente em venda ou item",
                ", ".join(proibidos) or "")

raise SystemExit(placar.fechar())
