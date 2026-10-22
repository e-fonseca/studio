"""Contas a pagar, contas a receber e a projeção de caixa.

Tudo sai da foto da última importação concluída, então os números são os do SET na data
do backup: nada aqui é digitado de novo, exceto o pagamento previsto, que a loja registra
quando sabe de uma despesa que ainda não foi lançada no SET.

A pergunta que estas telas respondem é a mesma do painel de compras, do outro lado: quanto
dinheiro já está comprometido e quando ele sai do caixa. É esse número que diz se dá para
comprar agora ou não.
"""

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.core import procura
from apps.core.texto import regex_sem_acento

from .models import Lancamento, PagamentoPrevisto

ZERO = Decimal("0")
# Faixas da projeção de caixa, em dias a partir de hoje. Três semanas e o mês cheio: é o
# horizonte em que a loja ainda consegue adiar ou antecipar uma compra.
FAIXAS = ((7, "nos próximos 7 dias"), (15, "em até 15 dias"), (30, "em até 30 dias"), (90, "em até 90 dias"))
MESES_DE_HISTORICO = 12


@dataclass
class Totais:
    quantidade: int = 0
    valor: Decimal = ZERO


@dataclass
class ResumoFinanceiro:
    """O que a gerência precisa ver antes de autorizar uma compra."""

    vencidas: Totais = field(default_factory=Totais)
    a_pagar: Totais = field(default_factory=Totais)
    a_receber: Totais = field(default_factory=Totais)
    previstos: Totais = field(default_factory=Totais)
    # Conta em aberto no SET SEM data de vencimento. Existe de verdade: o importador copia
    # a data como ela está no SET, e lá ela pode estar vazia. Como "venceu" e "vai vencer"
    # são os dois lados de uma comparação com hoje, e comparação com data vazia não é
    # verdadeira nem falsa, essa conta ficava fora das duas — e, por isso, fora do
    # compromisso total. O dinheiro que a loja deve aparecia menor do que é, e o teto de
    # compra de "Antes de comprar", que desconta o compromisso do caixa, aparecia maior.
    sem_data: Totais = field(default_factory=Totais)
    por_faixa: list = field(default_factory=list)
    despesa_media_mensal: Decimal = ZERO

    @property
    def compromisso_total(self):
        """Tudo o que ainda sai do caixa: o que venceu, o que vai vencer, o que não tem
        data marcada no SET, e o previsto lançado aqui."""
        return (self.vencidas.valor + self.a_pagar.valor + self.sem_data.valor
                + self.previstos.valor)


def _abertos(importacao, tipo):
    return Lancamento.objects.filter(importacao=importacao, tipo=tipo, pagamento__isnull=True)


def _totais(consulta):
    dados = consulta.aggregate(q=Count("id"), v=Sum("valor"))
    return Totais(quantidade=dados["q"] or 0, valor=dados["v"] or ZERO)


def previstos_em_aberto():
    return PagamentoPrevisto.objects.filter(lancado_no_set=False)


def resumir(importacao, hoje=None):
    """Os números do topo da tela de contas a pagar."""
    resumo = ResumoFinanceiro()
    if importacao is None:
        return resumo
    hoje = hoje or timezone.localdate()

    pagar = _abertos(importacao, Lancamento.Tipo.PAGAR)
    resumo.vencidas = _totais(pagar.filter(vencimento__lt=hoje))
    resumo.a_pagar = _totais(pagar.filter(vencimento__gte=hoje))
    resumo.sem_data = _totais(pagar.filter(vencimento__isnull=True))
    resumo.a_receber = _totais(_abertos(importacao, Lancamento.Tipo.RECEBER))
    resumo.previstos = Totais(
        quantidade=previstos_em_aberto().count(),
        valor=previstos_em_aberto().aggregate(v=Sum("valor"))["v"] or ZERO,
    )

    for dias, rotulo in FAIXAS:
        limite = hoje + timedelta(days=dias)
        do_set = pagar.filter(vencimento__gte=hoje, vencimento__lte=limite).aggregate(v=Sum("valor"))["v"] or ZERO
        previsto = previstos_em_aberto().filter(
            vencimento__gte=hoje, vencimento__lte=limite
        ).aggregate(v=Sum("valor"))["v"] or ZERO
        resumo.por_faixa.append({"dias": dias, "rotulo": rotulo, "valor": do_set + previsto,
                                 "previsto": previsto})

    meses = despesas_por_mes(importacao)
    # O último mês é o do corte e ainda está correndo: entrar na média puxaria o número
    # para baixo todo dia 1º.
    fechados = meses[:-1] if len(meses) > 1 else meses
    if fechados:
        # O divisor é a quantidade de meses do CALENDÁRIO entre o primeiro e o último mês
        # fechado, e não a quantidade de meses que tiveram pagamento. Mês em que a loja
        # não pagou nada é zero de verdade e tem que entrar na média; contando só os
        # meses com pagamento, ele desaparecia do divisor e empurrava a "despesa média
        # por mês" para cima — e é esse número que a gerência usa para dizer se o mês
        # está caro.
        primeiro, ultimo = fechados[0], fechados[-1]
        quantos = ((ultimo["ano"] - primeiro["ano"]) * 12
                   + (ultimo["mes"] - primeiro["mes"])) + 1
        resumo.despesa_media_mensal = sum((m["pago"] for m in fechados), ZERO) / quantos
    return resumo


# Filtros da tela de contas a pagar. A ordem é a da urgência: o que já venceu primeiro,
# a programação futura por último. "Prestes a vencer" é a semana, que é o prazo em que
# ainda dá para remarcar uma compra para não apertar o caixa.
DIAS_PRESTES_A_VENCER = 7
FILTROS = (
    ("todas", "Todas em aberto", "Tudo o que ainda não foi pago."),
    ("atrasados", "Atrasados", "Venceram e continuam em aberto."),
    ("do_dia", "Do dia", "Vencem hoje."),
    ("prestes", "Prestes a vencer", f"Vencem nos próximos {DIAS_PRESTES_A_VENCER} dias."),
    ("a_vencer", "A vencer", "Vencem de hoje em diante."),
    ("futura", "Programação futura", f"Vencem depois dos {DIAS_PRESTES_A_VENCER} dias."),
)
FILTRO_PADRAO = "todas"


# Onde a busca procura. O Edson pediu "campo pesquisa" na tela de contas a pagar em
# 13/10/2026, e o que se procura numa conta é o fornecedor, o que ela é, o número do
# documento ou a classificação do plano de contas do SET.
CAMPOS_DA_BUSCA = ("contraparte", "descricao", "documento", "parcela", "grupo")


def _aplicar_busca(consulta, busca):
    """Filtra pelo que foi digitado, aceitando com acento e sem.

    `iregex` em vez de `icontains` porque o nome vem do SET como está lá
    ("QUITÉRIA FLOR MILHO") e quem procura digita "quiteria". Ver
    `apps.core.texto.regex_sem_acento`.
    """
    padrao = regex_sem_acento(busca)
    if not padrao:
        return consulta
    procura = Q()
    for campo in CAMPOS_DA_BUSCA:
        procura |= Q(**{f"{campo}__iregex": padrao})
    return consulta.filter(procura)


def _aplicar_filtro(consulta, filtro, hoje):
    semana = hoje + timedelta(days=DIAS_PRESTES_A_VENCER)
    if filtro == "atrasados":
        return consulta.filter(vencimento__lt=hoje)
    if filtro == "do_dia":
        return consulta.filter(vencimento=hoje)
    if filtro == "prestes":
        return consulta.filter(vencimento__gte=hoje, vencimento__lte=semana)
    if filtro == "a_vencer":
        return consulta.filter(vencimento__gte=hoje)
    if filtro == "futura":
        return consulta.filter(vencimento__gt=semana)
    return consulta


def filtros_de_contas(importacao, hoje=None, busca=""):
    """Os filtros da tela com quantas contas e quanto dinheiro cada um pega.

    Quando há busca, cada filtro conta só o que a busca achou: senão o número do filtro
    e o número da lista discordariam na tela, e quem lê acreditaria no errado.
    """
    hoje = hoje or timezone.localdate()
    if importacao is None:
        return [{"chave": c, "rotulo": r, "explicacao": e, "quantidade": 0, "valor": ZERO}
                for c, r, e in FILTROS]
    base = _aplicar_busca(_abertos(importacao, Lancamento.Tipo.PAGAR), busca)
    resultado = []
    for chave, rotulo, explicacao in FILTROS:
        totais = _totais(_aplicar_filtro(base, chave, hoje))
        resultado.append({"chave": chave, "rotulo": rotulo, "explicacao": explicacao,
                          "quantidade": totais.quantidade, "valor": totais.valor})
    return resultado


# O que a lista de sugestões oferece, nesta ordem: é o fornecedor que quase todo mundo
# procura, e o documento é o que se procura quando se tem o papel na mão.
SUGESTOES_DA_BUSCA = (
    ("contraparte", "Fornecedor"),
    ("descricao", "Conta"),
    ("grupo", "Classificação"),
    ("documento", "Documento"),
)


def sugestoes_da_busca(importacao, termo, quantas=procura.QUANTAS, hoje=None):
    """O que oferecer enquanto a pessoa digita na busca de contas a pagar.

    Sugere o que EXISTE nas contas em aberto, não um dicionário de palavras: cada
    linha é um valor que, escolhido, devolve lista com conta dentro. Sugestão que
    leva a "nenhuma conta encontrada" é pior do que sugestão nenhuma.

    Vem agrupado por valor, com quantas contas cada um tem, porque "GENALDO (4
    contas)" responde antes de clicar.
    """
    if importacao is None or len(termo.strip()) < 2:
        return []
    termo = termo.strip()[:60]
    base = _abertos(importacao, Lancamento.Tipo.PAGAR)
    achados = []
    for campo, rotulo in SUGESTOES_DA_BUSCA:
        consulta = (
            base.filter(procura.filtro(termo, campo))
            .exclude(**{campo: ""})
            .values(campo)
            .annotate(quantas=Count("id"), valor=Sum("valor"))
        )
        for linha in consulta:
            achados.append({
                "texto": linha[campo], "tipo": rotulo,
                "quantas": linha["quantas"], "valor": linha["valor"] or ZERO,
            })
    # O mesmo texto pode casar em dois campos (o nome do fornecedor aparece na
    # descrição de algumas contas); fica o primeiro, que é o campo mais importante.
    vistos = set()
    unicos = []
    for achado in achados:
        chave = achado["texto"].casefold()
        if chave in vistos:
            continue
        vistos.add(chave)
        unicos.append(achado)
    padrao = regex_sem_acento(termo)
    comeco = re.compile(f"^{padrao}", re.IGNORECASE)
    palavra = re.compile(f"[^0-9A-Za-zÀ-ÿ]{padrao}", re.IGNORECASE)

    def perto(achado):
        """Começo vale mais que meio, e mais contas vale mais que menos."""
        texto = achado["texto"]
        if comeco.search(texto):
            return (0, -achado["quantas"], texto)
        if palavra.search(texto):
            return (1, -achado["quantas"], texto)
        return (2, -achado["quantas"], texto)

    unicos.sort(key=perto)
    return unicos[:quantas]


def rotulo_do_filtro(chave):
    """O nome da lista como a tela escreve: "Atrasados", "Programação futura".

    A tela e o PDF chamam a mesma lista pelo mesmo nome, e o botão que gera o PDF
    diz qual lista vai sair no papel.
    """
    return next((rotulo for c, rotulo, _ in FILTROS if c == chave), chave)


def contas_a_pagar(importacao, hoje=None, quantas=None, filtro=FILTRO_PADRAO, busca=""):
    """Contas em aberto, da mais atrasada para a que vence mais longe."""
    if importacao is None:
        return []
    hoje = hoje or timezone.localdate()
    consulta = _aplicar_filtro(
        _aplicar_busca(_abertos(importacao, Lancamento.Tipo.PAGAR), busca), filtro, hoje
    ).order_by("vencimento", "id")
    contas = list(consulta[:quantas] if quantas else consulta)
    for conta in contas:
        conta.atraso = conta.dias_de_atraso(hoje)
    return contas


def somar(contas):
    """O total do que está na lista. A tela e o PDF mostram o mesmo número."""
    return sum((conta.valor or ZERO for conta in contas), ZERO)


def contas_a_receber(importacao, quantas=None):
    if importacao is None:
        return []
    consulta = _abertos(importacao, Lancamento.Tipo.RECEBER).order_by("vencimento", "id")
    return list(consulta[:quantas] if quantas else consulta)


def inicio_da_janela(corte, meses=MESES_DE_HISTORICO):
    """O dia 1º de onde começa uma janela de tantos meses, contada do mês do corte.

    Devolve o primeiro dia do mês que está `meses` meses antes do mês do corte. Com
    `meses=12` e corte em 14/10/2026, a janela vai de 01/10/2025 a 14/10/2026: doze meses
    INTEIROS mais o mês do corte, que ainda está correndo.

    Por que não contar dias: "para onde o dinheiro foi" contava 30 dias por mês (360) e o
    mês a mês contava 31 (372), as duas na MESMA tela de Despesas e as duas chamadas de
    doze meses — somar uma coluna e conferir com a outra deixava uma diferença de doze
    dias de pagamento sem explicação nenhuma. E qualquer uma das duas começava no meio de
    um mês, então o mês mais antigo entrava com um terço dos dias e puxava a média para
    baixo. É a mesma régua da comparação mês a mês (1.30.0): mês inteiro, começando no
    dia 1º.
    """
    ano, mes = corte.year, corte.month - meses
    while mes <= 0:
        mes += 12
        ano -= 1
    return date(ano, mes, 1)


def despesas_por_grupo(importacao, meses=MESES_DE_HISTORICO, hoje=None):
    """Para onde o dinheiro foi, pela classificação do próprio SET, do maior para o menor."""
    if importacao is None:
        return []
    desde = inicio_da_janela(hoje or importacao.data_corte or timezone.localdate(), meses)
    linhas = (
        Lancamento.objects.filter(
            importacao=importacao, tipo=Lancamento.Tipo.PAGAR, pagamento__gte=desde
        )
        .values("grupo")
        .annotate(quantidade=Count("id"), valor=Sum("valor_pago"))
        .order_by("-valor")
    )
    total = sum((linha["valor"] or ZERO for linha in linhas), ZERO)
    resultado = []
    for linha in linhas:
        valor = linha["valor"] or ZERO
        resultado.append({
            "grupo": linha["grupo"] or "SEM CLASSIFICAÇÃO",
            "quantidade": linha["quantidade"],
            "valor": valor,
            "fatia": (valor / total * 100) if total else ZERO,
        })
    return resultado


def despesas_por_mes(importacao, meses=MESES_DE_HISTORICO):
    """Pago e recebido mês a mês, do mais antigo para o mais novo."""
    if importacao is None:
        return []
    corte = importacao.data_corte or timezone.localdate()
    desde = inicio_da_janela(corte, meses)
    por_mes = {}
    for tipo, chave in ((Lancamento.Tipo.PAGAR, "pago"), (Lancamento.Tipo.RECEBER, "recebido")):
        linhas = (
            Lancamento.objects.filter(importacao=importacao, tipo=tipo, pagamento__gte=desde)
            .values("pagamento__year", "pagamento__month")
            .annotate(valor=Sum("valor_pago"))
        )
        for linha in linhas:
            chave_mes = (linha["pagamento__year"], linha["pagamento__month"])
            por_mes.setdefault(chave_mes, {"ano": chave_mes[0], "mes": chave_mes[1],
                                           "pago": ZERO, "recebido": ZERO})
            por_mes[chave_mes][chave] = linha["valor"] or ZERO
    meses_ordenados = [por_mes[chave] for chave in sorted(por_mes)]
    for mes in meses_ordenados:
        mes["sobra"] = mes["recebido"] - mes["pago"]
    return meses_ordenados


def pagamentos_a_fornecedores(importacao, meses=MESES_DE_HISTORICO, quantas=None):
    """Quanto a loja já pagou a cada fornecedor, do maior para o menor."""
    if importacao is None:
        return []
    corte = importacao.data_corte or timezone.localdate()
    desde = inicio_da_janela(corte, meses)
    linhas = (
        Lancamento.objects.filter(
            importacao=importacao, tipo=Lancamento.Tipo.PAGAR, pagamento__gte=desde
        )
        .exclude(contraparte="")
        .values("contraparte")
        .annotate(quantidade=Count("id"), valor=Sum("valor_pago"))
        .order_by("-valor")
    )
    return list(linhas[:quantas] if quantas else linhas)


def pagamentos_recentes(importacao, quantos=30):
    """Os últimos pagamentos feitos, para conferir lançamento por lançamento."""
    if importacao is None:
        return []
    return list(
        Lancamento.objects.filter(importacao=importacao, tipo=Lancamento.Tipo.PAGAR,
                                  pagamento__isnull=False)
        .order_by("-pagamento", "-id")[:quantos]
    )
