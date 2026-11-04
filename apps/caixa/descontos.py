"""Os descontos de cada venda contra as regras da loja, e as metas do fim de semana.

Pedido do Edson em 02/11/2026, junto com as regras que a gerência passa à equipe: "no
financeiro do caixa, tentar buscar os descontos de cada produto seguindo as regras. ideia
é controlar os desconto para que os funcionarios dê desconto sem parâmetros só
objetivando a premiação. A empresa nao pode se prejudicar financeiro."

As regras ficam em `RegraDeDesconto` (a gerência muda pela tela). Este arquivo faz a
conta: o desconto de cada venda e de cada produto dela, o que a regra deixava, quem
recebeu no caixa, e a meta de cada sábado, domingo e feriado.

Onde o desconto está no SET
---------------------------
Em dois lugares, e só um deles aparece como "desconto":

1. **No fechamento** (VENDAS.TOTALDESC): o caixa tira um valor da venda inteira. É o
   desconto que o SET mostra, 1.344 das 16.361 vendas de 12 meses.
2. **No preço do produto**: o caixa muda o preço do item antes de fechar
   (IVENDAS.VALORPROD abaixo do preço de tabela). A venda sai com desconto zero e o
   produto mais barato. É por aqui que passa o desconto que ninguém vê.

O desconto da venda é a soma dos dois, e a porcentagem é sobre o que ela daria pelo preço
de tabela. O desconto do fechamento é dividido entre os produtos na proporção do valor de
cada um (como o próprio SET faz no rateio), e é assim que cada produto tem o seu.

O que a regra deixa
-------------------
Depende de como o cliente pagou, parte por parte (FATVENDAS): no Pix ou no dinheiro,
7%; no crédito e no débito, nada. A venda paga metade no Pix e metade no cartão pode ter
desconto só na metade do Pix. Forma que não é nenhuma dessas (a prazo) é "condição
diferente", que pela regra precisa de aprovação mesmo sem desconto.

A venda sai da regra quando o desconto passa do permitido por mais do que a folga de
arredondamento (R$ 1,00 no começo): quem fecha R$ 107,50 em R$ 100,00 no Pix deu 6,98%.

O que não entra no corte de preço:

- produto vendido a peso ("KG" ou "KL" na descrição): o caixa digita o preço do pedaço,
  que não se compara com o preço do quilo;
- o DIVERSOS, que no SET tem preço de R$ 1,00 de mentira;
- produto sem preço de tabela.

O preço de tabela é o que o SET gravou no item. Desde julho de 2026 ele quase nunca grava,
e aí vale o preço do cadastro no dia da importação: se o preço do produto mudou depois da
venda, o corte é estimativa, e a tela diz.

Quem
----
O VENDEDOR do SET está vazio desde abril de 2026. Quem aparece aqui é quem registrou o
recebimento no caixa (ICAIXA.USUARIO), que é quem fecha a venda e dá o desconto do
fechamento, mas nem sempre quem negociou com o cliente. A tela diz isso.

As metas
--------
Sábado e feriado, R$ 12.000; domingo, R$ 15.000 (era R$ 18.000 até 04/11/2026, quando o
Edson baixou, na 1.47.0). Batida, cada funcionário que trabalhou
no dia ganha R$ 30, e mais R$ 10 a cada R$ 1.000 acima. O SET não sabe quem trabalhou
(freela não tem usuário), então o prêmio sai POR PESSOA, e a tela mostra quem passou
venda no caixa naquele dia.

O que liga as duas coisas, e é a razão do pedido: o dia que só bateu a meta por causa de
venda fora da regra. A conta tira do dia as vendas fora da regra que ninguém aprovou e
diz se a meta ainda teria sido batida.
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal

from django.db.models import Prefetch

from apps.core.templatetags.cabana import reais
from apps.importacao.models import ItemVendaImportada, VendaImportada

from . import dinheiro
from . import feriados as calendario
from .models import CaixaImportado, DescontoAprovado, RegraDeDesconto

ZERO = Decimal("0")
CENTAVO = Decimal("0.01")
CEM = Decimal("100")

# (valor na URL, rótulo na tela)
PERIODOS = (
    ("7d", "7 dias"),
    ("30d", "30 dias"),
    ("mes", "Este mês"),
    ("mes_passado", "Mês passado"),
)
PERIODO_PADRAO = "7d"
ROTULO_DO_PERIODO = dict(PERIODOS)

# A lista de vendas fora da regra mostra no máximo isto na tela; o resto vira "e mais N".
FORA_NA_TELA = 100
PRODUTOS_NA_TELA = 15

A_VISTA, DEBITO, CREDITO, OUTRA = "a_vista", "debito", "credito", "outra"

# "PEDRA 1KG", "CARVAO 5 KG", "AREIA KL": vendido a peso.
_A_PESO = re.compile(r"\d\s*K[GL]\b|\bK[GL]\b")


def vendido_a_peso(descricao):
    return bool(_A_PESO.search((descricao or "").upper()))


def produto_generico(descricao):
    return (descricao or "").strip().upper().startswith("DIVERSOS")


def categoria(forma):
    """Em qual regra a forma de pagamento cai: à vista, débito, crédito ou outra."""
    chave = dinheiro._chave(forma)
    if not chave:
        return ""
    if dinheiro.classificar(forma) == "dinheiro" or chave == "PIX" or chave.startswith("PIX "):
        return A_VISTA
    palavras = chave.split()
    if "DEBITO" in palavras:
        return DEBITO
    if "CREDITO" in palavras:
        return CREDITO
    return OUTRA


def porcentagem_permitida(regra, qual):
    return {A_VISTA: regra.desconto_a_vista, DEBITO: regra.desconto_no_debito,
            CREDITO: regra.desconto_no_credito}.get(qual, ZERO)


def porcentagem(valor):
    """"7%", "12,3%": sem ",0" sobrando."""
    if valor is None:
        return "—"
    numero = Decimal(valor).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    if numero == numero.to_integral():
        return f"{numero:.0f}%"
    return f"{numero}%".replace(".", ",")


def nome_de_quem(usuario):
    """"CAIXA TESTE" do SET vira "Caixa Teste"; vazio vira "sem nome no caixa"."""
    texto = " ".join((usuario or "").split())
    return texto.title() if texto else "sem nome no caixa"


@dataclass
class ItemAvaliado:
    """Um produto da venda: o que daria pela tabela, o que saiu e o desconto que levou."""

    codigo: str
    descricao: str
    quantidade: Decimal
    cobrado: Decimal          # o que o item somou na venda, antes do desconto do fechamento
    tabela: Decimal           # o que daria pelo preço de tabela (= cobrado quando não se compara)
    corte: Decimal            # preço mudado no caixa
    rateio: Decimal = ZERO    # a parte dele no desconto do fechamento
    custo: Decimal = None
    tabela_estimada: bool = False
    sem_comparar: str = ""    # por que o preço não foi comparado: "a peso", "genérico", "sem tabela"

    @property
    def desconto(self):
        return self.corte + self.rateio

    @property
    def pago(self):
        return self.cobrado - self.rateio

    @property
    def percentual(self):
        if self.tabela <= 0:
            return ZERO
        return (self.desconto * CEM / self.tabela).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    @property
    def abaixo_do_custo(self):
        return self.custo is not None and self.custo > 0 and self.pago < self.custo


def avaliar_item(item):
    cobrado = item.valor_total or ZERO
    quantidade = item.quantidade or ZERO
    custo = item.custo_usado
    avaliado = ItemAvaliado(codigo=item.codigo, descricao=item.descricao, quantidade=quantidade,
                            cobrado=cobrado, tabela=cobrado, corte=ZERO, custo=custo)
    if vendido_a_peso(item.descricao):
        avaliado.sem_comparar = "vendido a peso"
    elif produto_generico(item.descricao):
        avaliado.sem_comparar = "produto genérico"
    elif not item.preco_tabela or item.preco_tabela <= 0 or quantidade <= 0:
        avaliado.sem_comparar = "sem preço de tabela"
    else:
        pela_tabela = (item.preco_tabela * quantidade).quantize(CENTAVO, rounding=ROUND_HALF_UP)
        if pela_tabela > cobrado:
            avaliado.tabela = pela_tabela
            avaliado.corte = pela_tabela - cobrado
            avaliado.tabela_estimada = item.preco_tabela_do_cadastro
    return avaliado


@dataclass
class VendaAvaliada:
    """Uma venda contra a regra."""

    id_set: int
    numero: str
    dia: object
    hora: str
    valor: Decimal
    quem: str
    partes: list               # [(nome da forma como a loja fala, valor)]
    tabela: Decimal
    desconto_no_fechamento: Decimal
    corte_nos_itens: Decimal
    permitido: Decimal
    condicao_diferente: list
    fora: bool
    limite_texto: str = ""     # "no Pix ela deixa até 7% (R$ 16,52)."
    corte_texto: str = ""      # "R$ 34,00 foi preço mudado no caixa (1 produto)..."
    itens: list = field(default_factory=list)
    aprovacao: object = None

    @property
    def regra_texto(self):
        """O que a regra diz desta venda, numa frase."""
        if self.condicao_diferente:
            return (f"{' e '.join(self.condicao_diferente)} é condição fora das regras: precisa "
                    "da aprovação do grupo.")
        if not self.fora:
            return "Dentro da regra."
        return _sem_quebra(f"Passou {reais(self.passou)} da regra: {self.limite_texto}")

    @property
    def motivo(self):
        """A frase inteira, para o e-mail: forma, desconto, regra e preço mudado no caixa."""
        partes = [self.regra_texto, self.corte_texto]
        if self.tem_desconto:
            partes.insert(0, f"{self.formas}, {porcentagem(self.percentual)} de desconto "
                             f"({reais(self.desconto)}).")
        return _sem_quebra(" ".join(parte for parte in partes if parte))

    @property
    def desconto(self):
        return self.desconto_no_fechamento + self.corte_nos_itens

    @property
    def tem_desconto(self):
        return self.desconto > 0

    @property
    def percentual(self):
        if self.tabela <= 0:
            return ZERO
        return (self.desconto * CEM / self.tabela).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    @property
    def passou(self):
        """Quanto o desconto passou do que a regra deixava."""
        return max(self.desconto - self.permitido, ZERO)

    @property
    def aprovada(self):
        return self.aprovacao is not None

    @property
    def sem_aprovacao(self):
        return self.fora and not self.aprovada

    @property
    def tabela_estimada(self):
        return any(item.tabela_estimada for item in self.itens)

    @property
    def custo(self):
        if not self.itens or any(item.custo is None for item in self.itens):
            return None
        return sum((item.custo for item in self.itens), ZERO)

    @property
    def abaixo_do_custo(self):
        custo = self.custo
        return custo is not None and custo > 0 and self.valor < custo

    @property
    def formas(self):
        return " e ".join(nome for nome, _ in self.partes) or "sem forma gravada"

    @property
    def itens_com_desconto(self):
        return [item for item in self.itens if item.desconto > 0]


def _partes(venda):
    """As partes do pagamento, ou a forma da venda inteira quando o SET não as gravou."""
    partes = []
    for nome, valor in (venda.formas_pagas or {}).items():
        try:
            numero = Decimal(str(valor))
        except ArithmeticError:
            continue
        if numero > 0:
            partes.append((nome, numero))
    if not partes:
        partes = [(venda.forma_pagamento, venda.valor if venda.valor > 0 else Decimal("1"))]
    return sorted(partes, key=lambda parte: -parte[1])


def avaliar(venda, regra, itens=None):
    """Confere uma venda contra a regra. `itens` são os ItemVendaImportada dela."""
    if itens is None:
        itens = list(venda.itens.all())
    avaliados = [avaliar_item(item) for item in itens]
    cobrado = sum((item.cobrado for item in avaliados), ZERO)
    corte = sum((item.corte for item in avaliados), ZERO)

    # O desconto do fechamento dividido entre os produtos, o último leva o arredondamento.
    resto = venda.desconto or ZERO
    if avaliados and cobrado > 0 and resto > 0:
        for posicao, item in enumerate(avaliados):
            if posicao == len(avaliados) - 1:
                item.rateio = resto
            else:
                item.rateio = (venda.desconto * item.cobrado / cobrado).quantize(CENTAVO, rounding=ROUND_HALF_UP)
                resto -= item.rateio

    produtos = venda.total_produtos or cobrado or ((venda.valor or ZERO) + (venda.desconto or ZERO))
    tabela = produtos + corte
    partes = _partes(venda)
    total_das_partes = sum((valor for _, valor in partes), ZERO)

    permitido = ZERO
    diferente = []
    for nome, valor in partes:
        qual = categoria(nome)
        if qual == OUTRA:
            diferente.append(dinheiro.nome_da_forma(nome))
        permitido += tabela * (valor / total_das_partes) * porcentagem_permitida(regra, qual) / CEM
    permitido = permitido.quantize(CENTAVO, rounding=ROUND_FLOOR)

    desconto = (venda.desconto or ZERO) + corte
    fora = bool(diferente) or desconto > permitido + regra.folga
    avaliada = VendaAvaliada(
        id_set=venda.id_set, numero=venda.numero, dia=venda.data, hora=venda.hora,
        valor=venda.valor or ZERO, quem=nome_de_quem(venda.recebido_por),
        partes=[(dinheiro.nome_da_forma(nome), valor) for nome, valor in partes],
        tabela=tabela, desconto_no_fechamento=venda.desconto or ZERO, corte_nos_itens=corte,
        permitido=permitido, condicao_diferente=diferente, fora=fora, itens=avaliados,
    )
    _explicar(avaliada, partes, regra)
    return avaliada


def _sem_quebra(texto):
    """Espaço que não quebra entre o R$ e o número: a frase vai para cartão estreito."""
    return texto.replace("R$ ", "R$\u00a0")


def _na_forma(nome):
    """"no Pix", "no cartão de crédito": a forma de pagamento como se fala numa frase."""
    qual = categoria(nome)
    if qual == A_VISTA:
        return "no Pix" if dinheiro._chave(nome).startswith("PIX") else "no dinheiro"
    if qual == DEBITO:
        return "no cartão de débito"
    if qual == CREDITO:
        return "no cartão de crédito"
    return f"em {dinheiro.nome_da_forma(nome)}"


def _explicar(venda, partes, regra):
    """As duas frases do cartão: o limite da regra e o preço mudado no caixa."""
    com_desconto = [(nome, porcentagem_permitida(regra, categoria(nome))) for nome, _ in partes]
    deixam = [(nome, pct) for nome, pct in com_desconto if pct > 0]
    if len(partes) == 1:
        nome, pct = com_desconto[0]
        if pct > 0:
            venda.limite_texto = f"{_na_forma(nome)} ela deixa até {porcentagem(pct)} ({reais(venda.permitido)})."
        else:
            venda.limite_texto = f"{_na_forma(nome)} ela é sem desconto."
    elif deixam:
        onde = " e ".join(dict.fromkeys(_na_forma(nome) for nome, _ in deixam))
        venda.limite_texto = f"ela deixa até {reais(venda.permitido)}, só na parte paga {onde}."
    else:
        venda.limite_texto = "nenhuma das formas desta venda tem desconto na regra."
    if venda.corte_nos_itens > 0:
        quantos = sum(1 for item in venda.itens if item.corte > 0)
        venda.corte_texto = (
            f"{reais(venda.corte_nos_itens)} foi preço mudado no caixa "
            f"({quantos} produto{'s' if quantos != 1 else ''})"
            f"{', comparado ao preço do cadastro' if venda.tabela_estimada else ''}.")
    venda.limite_texto = _sem_quebra(venda.limite_texto)
    venda.corte_texto = _sem_quebra(venda.corte_texto)


# ---------------------------------------------------------------------------------------
# A tela


@dataclass
class Pessoa:
    """Quem recebeu no caixa, somado no período."""

    nome: str
    vendas: int = 0
    com_desconto: int = 0
    desconto: Decimal = ZERO
    fora: int = 0
    passou: Decimal = ZERO
    maior: Decimal = ZERO


@dataclass
class ProdutoComDesconto:
    codigo: str
    descricao: str
    vezes: int = 0
    tabela: Decimal = ZERO
    desconto: Decimal = ZERO
    corte: Decimal = ZERO
    fora: int = 0
    abaixo_do_custo: int = 0
    estimado: bool = False

    @property
    def percentual(self):
        if self.tabela <= 0:
            return ZERO
        return (self.desconto * CEM / self.tabela).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


@dataclass
class DiaDeMeta:
    dia: object
    tipo: str            # "sabado", "domingo" ou "feriado"
    feriado: str
    meta: Decimal
    vendido: Decimal = ZERO
    vendas: int = 0
    quem: list = field(default_factory=list)
    fora: int = 0
    vendido_fora: Decimal = ZERO
    passou_fora: Decimal = ZERO
    premio_base: Decimal = ZERO
    premio_a_mais: Decimal = ZERO
    passo: Decimal = Decimal("1000")

    @property
    def rotulo(self):
        if self.tipo == "domingo":
            return f"Domingo, {self.feriado}" if self.feriado else "Domingo"
        if self.tipo == "sabado":
            return f"Sábado, {self.feriado}" if self.feriado else "Sábado"
        return self.feriado or "Feriado"

    def premio_com(self, vendido):
        if vendido < self.meta:
            return ZERO
        passos = ((vendido - self.meta) / self.passo).to_integral_value(rounding=ROUND_FLOOR) if self.passo > 0 else 0
        return self.premio_base + self.premio_a_mais * passos

    @property
    def proximo_degrau(self):
        """(quanto vender, o prêmio por pessoa lá) do próximo degrau; None sem degrau.

        Antes da meta, o próximo degrau é a própria meta. Serve ao aviso do grupo das metas
        (1.47.0): "o próximo é R$ 14.000, R$ 50 por pessoa" diz onde está o prêmio maior.
        """
        if not self.bateu:
            return self.meta, self.premio_base
        if self.passo <= 0 or self.premio_a_mais <= 0:
            return None
        passos = ((self.vendido - self.meta) / self.passo).to_integral_value(rounding=ROUND_FLOOR)
        alvo = self.meta + self.passo * (passos + 1)
        return alvo, self.premio_com(alvo)

    @property
    def bateu(self):
        return self.vendido >= self.meta

    @property
    def premio(self):
        return self.premio_com(self.vendido)

    @property
    def falta(self):
        return max(self.meta - self.vendido, ZERO)

    @property
    def vendido_sem_fora(self):
        return self.vendido - self.vendido_fora

    @property
    def premio_sem_fora(self):
        return self.premio_com(self.vendido_sem_fora)

    @property
    def dependeu_de_fora(self):
        """A meta só bateu (ou o prêmio só subiu) por causa de venda fora da regra."""
        return self.fora > 0 and self.premio_sem_fora < self.premio

    @property
    def nivel(self):
        if self.dependeu_de_fora:
            return "ruim"
        if self.bateu and self.fora:
            return "atencao"
        return "bom" if self.bateu else ""


@dataclass
class Tela:
    importacao: object = None
    regra: object = None
    periodo: str = PERIODO_PADRAO
    rotulo_periodo: str = ""
    desde: object = None
    ate: object = None
    filtro_quem: str = ""
    nomes: list = field(default_factory=list)
    vendas: int = 0
    vendido: Decimal = ZERO
    com_desconto: int = 0
    desconto: Decimal = ZERO
    corte_nos_itens: Decimal = ZERO
    vendas_com_corte: int = 0
    fora: list = field(default_factory=list)
    aprovadas: list = field(default_factory=list)
    abaixo_do_custo: int = 0
    pessoas: list = field(default_factory=list)
    produtos: list = field(default_factory=list)
    metas: list = field(default_factory=list)
    falta_importar: bool = False
    tem_estimativa: bool = False
    tem_dados: bool = False

    @property
    def sem_aprovacao(self):
        return [venda for venda in self.fora if not venda.aprovada]

    @property
    def passou_sem_aprovacao(self):
        return sum((venda.passou for venda in self.sem_aprovacao), ZERO)

    @property
    def desconto_aprovado(self):
        return sum((venda.desconto for venda in self.aprovadas), ZERO)

    @property
    def fora_na_tela(self):
        return self.sem_aprovacao[:FORA_NA_TELA]

    @property
    def fora_escondidas(self):
        return max(len(self.sem_aprovacao) - FORA_NA_TELA, 0)

    @property
    def metas_batidas(self):
        return sum(1 for dia in self.metas if dia.bateu)

    @property
    def metas_que_dependeram(self):
        return [dia for dia in self.metas if dia.dependeu_de_fora]

    @property
    def premio_por_pessoa(self):
        return sum((dia.premio for dia in self.metas), ZERO)

    @property
    def fatia_com_desconto(self):
        if not self.vendas:
            return ZERO
        return (Decimal(self.com_desconto) * CEM / self.vendas).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    @property
    def filtrou(self):
        return bool(self.filtro_quem) or self.periodo != PERIODO_PADRAO


def janela(ultimo_dia, periodo):
    """O primeiro e o último dia do período, terminando no último dia com venda."""
    if periodo == "30d":
        return ultimo_dia - timedelta(days=29), ultimo_dia
    if periodo == "mes":
        return ultimo_dia.replace(day=1), ultimo_dia
    if periodo == "mes_passado":
        fim = ultimo_dia.replace(day=1) - timedelta(days=1)
        return fim.replace(day=1), fim
    return ultimo_dia - timedelta(days=6), ultimo_dia


def vendas_avaliadas(importacao, desde, ate, regra):
    """Todas as vendas do período, cada uma conferida contra a regra, com a aprovação."""
    vendas = (VendaImportada.objects
              .filter(importacao=importacao, data__gte=desde, data__lte=ate)
              .order_by("data", "hora", "id_set")
              .prefetch_related(Prefetch("itens", queryset=ItemVendaImportada.objects.order_by("id"))))
    aprovacoes = {aprovacao.id_venda: aprovacao for aprovacao in
                  DescontoAprovado.objects.filter(desfeito_em__isnull=True, dia__gte=desde, dia__lte=ate)
                  .select_related("registrado_por")}
    resultado = []
    for venda in vendas:
        avaliada = avaliar(venda, regra, list(venda.itens.all()))
        if avaliada.fora:
            avaliada.aprovacao = aprovacoes.get(venda.id_set)
        resultado.append(avaliada)
    return resultado


def montar(importacao, periodo=PERIODO_PADRAO, quem=""):
    """A tela inteira. Sem importação concluída, devolve a tela vazia."""
    regra = RegraDeDesconto.atual()
    tela = Tela(importacao=importacao, regra=regra)
    if periodo not in ROTULO_DO_PERIODO:
        periodo = PERIODO_PADRAO
    tela.periodo = periodo
    tela.rotulo_periodo = ROTULO_DO_PERIODO[periodo]
    if importacao is None or not importacao.data_corte:
        return tela
    tela.desde, tela.ate = janela(importacao.data_corte, periodo)

    todas = vendas_avaliadas(importacao, tela.desde, tela.ate, regra)
    tela.nomes = sorted({venda.quem for venda in todas})
    tela.filtro_quem = quem if quem in tela.nomes else ""
    tela.falta_importar = bool(todas) and _importacao_antiga(importacao)
    _metas(tela, todas, regra)

    escolhidas = [venda for venda in todas if not tela.filtro_quem or venda.quem == tela.filtro_quem]
    tela.tem_dados = bool(escolhidas)
    pessoas = {}
    produtos = {}
    for venda in escolhidas:
        tela.vendas += 1
        tela.vendido += venda.valor
        pessoa = pessoas.setdefault(venda.quem, Pessoa(nome=venda.quem))
        pessoa.vendas += 1
        if venda.tem_desconto:
            tela.com_desconto += 1
            tela.desconto += venda.desconto
            pessoa.com_desconto += 1
            pessoa.desconto += venda.desconto
            pessoa.maior = max(pessoa.maior, venda.percentual)
        if venda.corte_nos_itens > 0:
            tela.vendas_com_corte += 1
            tela.corte_nos_itens += venda.corte_nos_itens
        if venda.abaixo_do_custo:
            tela.abaixo_do_custo += 1
        if venda.fora:
            if venda.aprovada:
                tela.aprovadas.append(venda)
            else:
                tela.fora.append(venda)
                pessoa.fora += 1
                pessoa.passou += venda.passou
        if venda.tabela_estimada:
            tela.tem_estimativa = True
        for item in venda.itens_com_desconto:
            produto = produtos.setdefault(item.codigo, ProdutoComDesconto(item.codigo, item.descricao))
            produto.vezes += 1
            produto.tabela += item.tabela
            produto.desconto += item.desconto
            produto.corte += item.corte
            produto.estimado = produto.estimado or item.tabela_estimada
            if venda.sem_aprovacao:
                produto.fora += 1
            if item.abaixo_do_custo:
                produto.abaixo_do_custo += 1
    # A lista que pede ação: do que mais passou da regra para o que menos passou.
    tela.fora.sort(key=lambda venda: (-venda.passou, venda.dia, venda.hora))
    tela.aprovadas.sort(key=lambda venda: (venda.dia, venda.hora), reverse=True)
    tela.pessoas = sorted(pessoas.values(), key=lambda p: (-p.passou, -p.fora, -p.desconto, p.nome))
    tela.produtos = sorted(produtos.values(), key=lambda p: (-p.desconto, p.descricao))[:PRODUTOS_NA_TELA]
    return tela


def _importacao_antiga(importacao):
    """A importação veio de antes da 1.46.0 e não trouxe preço de tabela nem partes."""
    vendas = VendaImportada.objects.filter(importacao=importacao)
    return not vendas.exclude(total_produtos=0).exists() and not vendas.exclude(formas_pagas={}).exists()


def _metas(tela, todas, regra):
    """Os sábados, domingos e feriados do período, com a meta, o vendido e o prêmio."""
    feriados = calendario.feriados_entre(tela.desde, tela.ate, regra.outros_feriados)
    por_dia = defaultdict(list)
    for venda in todas:
        por_dia[venda.dia].append(venda)
    operadores = defaultdict(set)
    for dia, operador, fechou in (CaixaImportado.objects
                                  .filter(importacao=tela.importacao, dia__gte=tela.desde, dia__lte=tela.ate)
                                  .values_list("dia", "operador", "operador_fechamento")):
        for nome in (operador, fechou):
            if nome and nome.strip():
                operadores[dia].add(nome_de_quem(nome))
    dia = tela.desde
    while dia <= tela.ate:
        tipo, feriado = calendario.tipo_de_dia(dia, feriados)
        if tipo:
            meta = regra.meta_domingo if tipo == "domingo" else regra.meta_sabado
            registro = DiaDeMeta(dia=dia, tipo=tipo, feriado=feriado, meta=meta,
                                 premio_base=regra.premio, premio_a_mais=regra.premio_a_mais,
                                 passo=regra.passo)
            nomes = set(operadores.get(dia, ()))
            for venda in por_dia.get(dia, ()):
                registro.vendas += 1
                registro.vendido += venda.valor
                if venda.quem != nome_de_quem(""):
                    nomes.add(venda.quem)
                if venda.sem_aprovacao:
                    registro.fora += 1
                    registro.vendido_fora += venda.valor
                    registro.passou_fora += venda.passou
            registro.quem = sorted(nomes)
            if registro.vendas:
                tela.metas.append(registro)
        dia += timedelta(days=1)
    tela.metas.reverse()


def do_dia(importacao, dia):
    """Para o e-mail do dia: as vendas fora da regra sem aprovação e a meta, se o dia tem."""
    regra = RegraDeDesconto.atual()
    todas = vendas_avaliadas(importacao, dia, dia, regra)
    fora = sorted((venda for venda in todas if venda.sem_aprovacao), key=lambda venda: -venda.passou)
    tela = Tela(importacao=importacao, regra=regra, desde=dia, ate=dia)
    _metas(tela, todas, regra)
    return fora, (tela.metas[0] if tela.metas else None), regra
