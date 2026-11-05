#!/usr/bin/env python3
"""Monta os quatro relatórios e confere que eles dizem o mesmo que as telas.

Só de leitura: NÃO manda e-mail, NÃO avisa no Telegram, NÃO grava registro de envio. É o
jeito de ver o conteúdo de cada relatório sem mexer na caixa de entrada de ninguém.

    python3 .claude/skills/cabana-reporting-system/scripts/validar-relatorios.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import Placar, ligar, linha, reais, titulo  # noqa: E402

ligar()

from apps.alertas import relatorios, telegram  # noqa: E402
from apps.alertas.models import Rotina  # noqa: E402
from apps.importacao import servicos  # noqa: E402
from apps.painel import vendas_do_dia  # noqa: E402

placar = Placar()
importacao = servicos.ultima_concluida()

titulo("De onde vêm os números")
if importacao is None:
    print("  Nenhuma importação concluída: os relatórios vão dizer isso e não mandar nada.")
else:
    linha("dia dos dados", f"{importacao.data_corte:%d/%m/%Y}")

for rotina in (Rotina.CONTAS, Rotina.VENDAS, Rotina.ESTOQUE, Rotina.COMPRA):
    titulo(f"{rotina.label}")
    relatorio = relatorios.montar(rotina.value)
    linha("manchete", relatorio.manchete or "—")
    linha("tem notícia", "sim" if relatorio.tem_noticia else "não (não seria mandado hoje)")
    linha("tela", relatorio.caminho)
    if relatorio.aviso:
        linha("aviso no topo", relatorio.aviso)
    for bloco in relatorio.blocos:
        print(f"    · {bloco.titulo}")
        for item in bloco.linhas[:3]:
            print(f"        {item.get('quem', '')} — {item.get('valor', '')}")
        if bloco.escondidas:
            print(f"        (e mais {bloco.escondidas})")
    placar.conferir(bool(relatorio.manchete), f"{rotina.label}: tem manchete")
    placar.conferir(bool(relatorio.resumo), f"{rotina.label}: tem resumo para o registro")
    placar.conferir(relatorio.caminho.startswith("/studio/"),
                    f"{rotina.label}: aponta para uma tela do sistema")
    if relatorio.tem_noticia:
        placar.conferir(bool(relatorio.blocos), f"{rotina.label}: com notícia, tem bloco")

titulo("O número do relatório é o número da tela?")
if importacao is None:
    placar.avisar("sem importação não há o que comparar")
else:
    da_tela = vendas_do_dia.calcular(importacao)
    do_email = relatorios.vendas_do_dia(importacao)
    linha("tela: vendido no dia", reais(da_tela.faturamento))
    linha("tela: sobrou", reais(da_tela.lucro))
    if da_tela.tem_dados:
        placar.conferir(reais(da_tela.faturamento).replace("R$ ", "") in do_email.manchete
                        or relatorios._reais(da_tela.faturamento) in do_email.manchete,
                        "o vendido do dia aparece igual na manchete do e-mail")
        placar.conferir(relatorios._reais(da_tela.lucro) in do_email.manchete,
                        "o que sobrou aparece igual na manchete do e-mail")
    else:
        placar.avisar("o último dia importado não tem venda")

titulo("Como o aviso do Telegram sai")
aviso = telegram.texto_do_relatorio(relatorios.montar("vendas"))
for pedaco in aviso.splitlines()[:12]:
    print(f"  {pedaco}")
placar.conferir(len(aviso) <= telegram.MAXIMO + 100, "o aviso cabe numa mensagem do Telegram",
                f"{len(aviso)} caracteres")
placar.conferir("https://" in aviso, "o aviso leva o endereço do sistema inteiro")

raise SystemExit(placar.fechar())
