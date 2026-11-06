"""As contas do planejamento financeiro do Studio, num lugar só.

Portado do protótipo da Henriett (painel "Financeiro Studio Industrial", 06/11/2026),
regra por regra, com duas diferenças de propósito:

1. **Dinheiro em Decimal, e a soma das parcelas fecha o total.** O protótipo dividia
   o custo por 3 em ponto flutuante; aqui cada parcela é arredondada ao centavo e a
   última leva a diferença, para a lista bater com o custo.
2. **Pedido entregue sem data de entrega cobra hoje.** No protótipo a 2ª parcela dele
   ficava sem data e sumia das contas; aqui ela entra como devida agora.

Nada aqui grava no banco: as funções leem os pedidos e os Ajustes e devolvem números.
"""

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from apps.projetos.models import Projeto

from .models import (Avulso, Cartao, CustoFixo, Divida, MovimentoEntreEmpresas,
                     Parametros)

ZERO = Decimal("0")
CEM = Decimal("100")
CENTAVO = Decimal("0.01")
MESES = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")


def centavos(valor):
    return (valor or ZERO).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def dividir(total, partes):
    """`partes` valores ao centavo que somam exatamente `total`."""
    partes = max(1, int(partes or 1))
    total = centavos(total)
    cada = centavos(total / partes)
    valores = [cada] * (partes - 1)
    valores.append(total - sum(valores, ZERO))
    return valores


def data_no_mes(ano, mes0, dia):
    """O dia `dia` do mês `mes0` (contado de 0, pode passar de 11 ou ser negativo).

    Mês curto devolve o último dia: dia 30 de fevereiro é 28 (ou 29).
    """
    ano += mes0 // 12
    mes = mes0 % 12 + 1
    return date(ano, mes, min(dia, calendar.monthrange(ano, mes)[1]))


def rotulo_mes(ano, mes):
    return f"{MESES[mes - 1]}/{ano}"


# -----------------------------------------------------------------------------------
# O contexto: os Ajustes lidos uma vez só
# -----------------------------------------------------------------------------------

@dataclass
class Contexto:
    hoje: date
    parametros: Parametros
    cartoes: dict
    fixos: list
    dividas: list
    avulsos: list

    @classmethod
    def carregar(cls, hoje=None):
        return cls(
            hoje=hoje or timezone.localdate(),
            parametros=Parametros.atual(),
            cartoes={c.pk: c for c in Cartao.objects.all()},
            fixos=list(CustoFixo.objects.filter(ativo=True)),
            dividas=list(Divida.objects.filter(ativa=True)),
            avulsos=list(Avulso.objects.filter(pago=False)),
        )

    def pct(self, campo):
        return (getattr(self.parametros, campo) or ZERO) / CEM

    def cartao(self, cartao_id):
        """O cartão do pedido, o padrão, ou um genérico (vence dia 1, fecha 8 dias antes)."""
        if cartao_id and cartao_id in self.cartoes:
            return self.cartoes[cartao_id]
        padrao = self.parametros.cartao_padrao_id
        if padrao and padrao in self.cartoes:
            return self.cartoes[padrao]
        return Cartao(nome="Cartão", vencimento=1, fecha_dias_antes=8)


def pedidos(contexto=None):
    """Os pedidos que entram no dinheiro: vendidos, com a oficina carregada."""
    return list(Projeto.objects.filter(etapa__in=Projeto.VENDIDOS)
                .select_related("oficina", "pg1_cartao").order_by("prazo_entrega", "id"))


def aberto(projeto):
    return projeto.etapa in Projeto.EM_ANDAMENTO


# -----------------------------------------------------------------------------------
# O que sai para a oficina
# -----------------------------------------------------------------------------------

@dataclass
class Saida:
    data: date | None
    valor: Decimal
    tipo: str  # "cartao", "pix", "mensal", "fixo", "emprestimo", "juros", "avulso"
    descricao: str = ""
    parcela: str = ""
    cartao: str = ""
    previsto: bool = False
    projeto: object = None

    @property
    def grupo(self):
        """O nome do bloco no "A pagar": cada cartão separado, depois o resto."""
        if self.tipo == "cartao":
            return f"Cartão {self.cartao}"
        if self.tipo == "mensal":
            oficina = self.projeto.oficina.nome if self.projeto and self.projeto.oficina_id else "Oficina"
            return f"{oficina} (parcelas mensais)"
        return {"pix": "Pix das oficinas", "fixo": "Custos fixos", "emprestimo": "Empréstimos",
                "juros": "Juros", "avulso": "Avulsos"}.get(self.tipo, self.tipo)


def primeira_fatura(compra, cartao):
    """O vencimento da fatura em que cai uma compra feita em `compra`.

    A compra cai na primeira fatura cujo fechamento (vencimento menos os dias) é no
    mesmo dia da compra ou depois dela.
    """
    for i in range(5):
        vence = data_no_mes(compra.year, compra.month - 1 + i, cartao.vencimento)
        if compra <= vence - timedelta(days=cartao.fecha_dias_antes):
            return vence
    return data_no_mes(compra.year, compra.month - 1 + 5, cartao.vencimento)


def parcelas_no_cartao(compra, cartao, vezes, total):
    primeira = primeira_fatura(compra, cartao)
    vezes = max(1, int(vezes or 1))
    return [
        (data_no_mes(primeira.year, primeira.month - 1 + k, cartao.vencimento), valor, f"{k + 1}/{vezes}")
        for k, valor in enumerate(dividir(total, vezes))
    ]


def parcelas_mensais(repasse, oficina, total):
    """Oficina que recebe em N vezes num dia fixo, com corte: o Rogério e o Breno."""
    vezes = (oficina.parcelas_mensais if oficina else None) or 3
    dia = (oficina.dia_pagamento if oficina else None) or 30
    corte = (oficina.dia_corte if oficina else None) or dia
    mes0 = repasse.month - 1 + (1 if repasse.day > corte else 0)
    return [
        (data_no_mes(repasse.year, mes0 + k, dia), valor, f"{k + 1}/{vezes}")
        for k, valor in enumerate(dividir(total, vezes))
    ]


@dataclass
class Agenda:
    saidas: list = field(default_factory=list)
    sem_data: list = field(default_factory=list)


def agenda_oficina(projeto, contexto):
    """Os pagamentos à oficina de um pedido, pela regra dele."""
    agenda = Agenda()
    if not projeto.incluir or not projeto.vendido:
        return agenda
    custo = centavos(projeto.custo_oficina)
    if not custo:
        return agenda
    hoje = contexto.hoje
    regime = projeto.regime_efetivo

    if regime == Projeto.Regime.MENSAL:
        for dia, valor, parcela in parcelas_mensais(projeto.repasse or hoje, projeto.oficina, custo):
            agenda.saidas.append(Saida(dia, valor, "mensal", "parcela mensal", parcela,
                                       previsto=not projeto.repasse, projeto=projeto))
        return agenda

    cartao = contexto.cartao(projeto.pg1_cartao_id)
    vezes = projeto.pg1_parcelas or contexto.parametros.parcelas_padrao
    compra = projeto.pg1_data or hoje

    if regime == Projeto.Regime.CARTAO:
        for dia, valor, parcela in parcelas_no_cartao(compra, cartao, vezes, custo):
            agenda.saidas.append(Saida(dia, valor, "cartao", "custo no cartão", parcela, cartao.nome,
                                       previsto=not projeto.pg1_data, projeto=projeto))
        return agenda

    # Padrão: a 1ª no cartão, a 2ª em Pix na entrega.
    pct = (projeto.primeira_percentual / CEM if projeto.primeira_percentual is not None
           else contexto.pct("pct_primeira"))
    primeira = centavos(custo * pct)
    segunda = custo - primeira
    if primeira:
        for dia, valor, parcela in parcelas_no_cartao(compra, cartao, vezes, primeira):
            agenda.saidas.append(Saida(dia, valor, "cartao", "1ª parcela", parcela, cartao.nome,
                                       previsto=not projeto.pg1_data, projeto=projeto))
    if not segunda:
        return agenda
    if projeto.pg2_data:
        agenda.saidas.append(Saida(projeto.pg2_data, segunda, "pix", "2ª parcela paga", projeto=projeto))
        return agenda
    entrega = projeto.entregue_em or projeto.prazo_entrega
    if not entrega and aberto(projeto):
        agenda.sem_data.append(Saida(None, segunda, "pix", "2ª parcela sem data de entrega",
                                     previsto=True, projeto=projeto))
        return agenda
    # Entrega que já passou (ou entregue sem data) é dívida de agora.
    dia = max(entrega or hoje, hoje)
    agenda.saidas.append(Saida(dia, segunda, "pix", "2ª parcela na entrega",
                               previsto=not projeto.entregue_em, projeto=projeto))
    return agenda


def todas_as_saidas(lista, contexto):
    agenda = Agenda()
    for projeto in lista:
        a = agenda_oficina(projeto, contexto)
        agenda.saidas += a.saidas
        agenda.sem_data += a.sem_data
    return agenda


def saidas_fixas(inicio, fim, contexto):
    """Custos fixos, parcelas de empréstimo, juros e avulsos entre `inicio` e `fim`."""
    saidas = []
    meses = (fim.year - inicio.year) * 12 + fim.month - inicio.month + 1
    for i in range(meses):
        for fixo in contexto.fixos:
            dia = data_no_mes(inicio.year, inicio.month - 1 + i, fixo.dia)
            if inicio <= dia <= fim:
                saidas.append(Saida(dia, centavos(fixo.valor), fixo.tipo, fixo.nome))
        for divida in contexto.dividas:
            dia = data_no_mes(inicio.year, inicio.month - 1 + i, divida.dia)
            if inicio <= dia <= fim and divida.juros_mes:
                saidas.append(Saida(dia, divida.juros_mes, "juros", divida.nome))
    for avulso in contexto.avulsos:
        if inicio <= avulso.data <= fim:
            saidas.append(Saida(avulso.data, centavos(avulso.valor), "avulso", avulso.nome))
    return saidas


def fixos_por_mes(contexto):
    return (sum((centavos(f.valor) for f in contexto.fixos), ZERO)
            + sum((d.juros_mes for d in contexto.dividas), ZERO))


# -----------------------------------------------------------------------------------
# O que o cliente ainda paga, e a margem
# -----------------------------------------------------------------------------------

@dataclass
class SaldoCliente:
    saldo: Decimal
    data: date | None = None
    vencido: bool = False
    sem_data: bool = False
    a_confirmar: bool = False
    projeto: object = None

    @property
    def data_na_conta(self):
        return self.data


def saldo_cliente(projeto, contexto):
    """O saldo em Pix que falta o cliente pagar. None quando não há venda para medir.

    Cartão do cliente entra antecipado: saldo no cartão ou quitado não espera nada.
    """
    venda = projeto.valor_venda or ZERO
    if not projeto.vendido or not venda:
        return None
    if projeto.saldo_forma in (Projeto.SaldoForma.CARTAO, Projeto.SaldoForma.QUITADO):
        return SaldoCliente(ZERO, projeto=projeto)
    saldo = projeto.saldo_pix if projeto.saldo_pix is not None else max(venda - (projeto.recebido or ZERO), ZERO)
    saldo = centavos(saldo)
    if saldo <= Decimal("0.5"):
        return SaldoCliente(ZERO, projeto=projeto)
    entregue = projeto.etapa == Projeto.Etapa.ENTREGUE
    dia = projeto.entregue_em or projeto.prazo_entrega
    return SaldoCliente(saldo, dia, vencido=entregue, sem_data=not dia and not entregue,
                        a_confirmar=not projeto.saldo_forma, projeto=projeto)


@dataclass
class Margem:
    venda: Decimal
    custo: Decimal
    taxa: Decimal
    estimada: bool

    @property
    def lucro(self):
        return self.venda - self.custo - self.taxa

    @property
    def fracao(self):
        return self.lucro / self.venda if self.venda else ZERO

    @property
    def percentual(self):
        return (self.fracao * CEM).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def margem(projeto, contexto):
    """Margem de lucro: (venda − oficina − frete, embalagem, RT, projeto − taxa) ÷ venda."""
    venda = projeto.valor_venda or ZERO
    if not venda:
        return None
    no_cartao = projeto.venda_cartao if projeto.venda_cartao is not None else venda * contexto.pct("pct_cartao")
    taxa = centavos(no_cartao * contexto.pct("taxa_antecipacao"))
    return Margem(venda, projeto.custo_total, taxa, estimada=projeto.venda_cartao is None)


def margem_media(lista, contexto):
    venda = lucro = ZERO
    for projeto in lista:
        m = margem(projeto, contexto) if projeto.incluir else None
        if m:
            venda += m.venda
            lucro += m.lucro
    return lucro / venda if venda else None


def margem_efetiva(contexto):
    """A margem de referência: a do markup alvo, menos a taxa do que vende no cartão."""
    markup = contexto.pct("markup_alvo")
    return (1 - 1 / (1 + markup)) - contexto.pct("pct_cartao") * contexto.pct("taxa_antecipacao")


def ponto_de_equilibrio(lista, contexto):
    """Quanto vender no mês para pagar fixos e juros, com a margem média dos pedidos."""
    m = margem_media(lista, contexto) or margem_efetiva(contexto)
    if not m or m <= 0:
        return None
    return centavos(fixos_por_mes(contexto) / Decimal(m))


def faltando(projeto):
    """O que falta no card para as contas fecharem."""
    if not projeto.incluir:
        return []
    falta = []
    if not projeto.valor_venda:
        falta.append("valor de venda")
    if not projeto.custo_oficina:
        falta.append("custo da oficina")
    if not projeto.oficina_id:
        falta.append("oficina")
    if aberto(projeto) and not projeto.prazo_entrega:
        falta.append("data prevista de entrega")
    if projeto.regime_efetivo == Projeto.Regime.PADRAO and aberto(projeto) and not projeto.pg1_data:
        falta.append("pagamento da 1ª parcela (data e cartão)")
    if not projeto.saldo_forma and projeto.valor_venda:
        falta.append("forma de pagamento do saldo do cliente")
    return falta


# -----------------------------------------------------------------------------------
# O caixa dos próximos dias
# -----------------------------------------------------------------------------------

@dataclass
class Evento:
    data: date
    valor: Decimal  # positivo entra, negativo sai
    tipo: str
    descricao: str = ""
    projeto: object = None


@dataclass
class Projecao:
    pontos: list
    eventos: list
    minimo: Decimal
    dia_minimo: date
    final: Decimal
    entradas: Decimal
    saidas: Decimal


def projecao(lista, contexto, dias=30):
    hoje = contexto.hoje
    fim = hoje + timedelta(days=dias)
    eventos = []
    for s in todas_as_saidas(lista, contexto).saidas:
        if hoje <= s.data <= fim:
            eventos.append(Evento(s.data, -s.valor, s.grupo, s.descricao, s.projeto))
    for s in saidas_fixas(hoje, fim, contexto):
        eventos.append(Evento(s.data, -s.valor, s.grupo, s.descricao))
    for projeto in lista:
        c = saldo_cliente(projeto, contexto)
        if c and c.saldo > 0 and c.data:
            dia = max(c.data, hoje)
            if dia <= fim:
                eventos.append(Evento(dia, c.saldo, "Pix de cliente",
                                      "saldo vencido" if c.vencido else "saldo na entrega", projeto))
    eventos.sort(key=lambda e: (e.data, e.valor))
    por_dia = {}
    for e in eventos:
        por_dia[e.data] = por_dia.get(e.data, ZERO) + e.valor
    saldo = contexto.parametros.saldo_inicial or ZERO
    minimo, dia_minimo, pontos = saldo, hoje, []
    for i in range(dias + 1):
        dia = hoje + timedelta(days=i)
        saldo += por_dia.get(dia, ZERO)
        pontos.append((dia, saldo))
        if saldo < minimo:
            minimo, dia_minimo = saldo, dia
    return Projecao(
        pontos=pontos, eventos=eventos, minimo=minimo, dia_minimo=dia_minimo, final=saldo,
        entradas=sum((e.valor for e in eventos if e.valor > 0), ZERO),
        saidas=-sum((e.valor for e in eventos if e.valor < 0), ZERO),
    )


# -----------------------------------------------------------------------------------
# Alertas
# -----------------------------------------------------------------------------------

@dataclass
class Alerta:
    gravidade: str  # "ruim", "atencao", "info"
    tipo: str
    texto: str
    projeto: object = None


def alertas(lista, contexto, proj=None):
    hoje = contexto.hoje
    p = contexto.parametros
    minimo = contexto.pct("margem_minima")
    saida = []
    for projeto in lista:
        if not projeto.incluir:
            continue
        m = margem(projeto, contexto)
        if m and m.fracao < minimo:
            saida.append(Alerta("ruim", "Margem baixa", f"margem de {_pct_br(m.percentual)}% (mínimo "
                                f"{_pct_br(format(p.margem_minima.normalize(), "f"))}%)", projeto))
        if aberto(projeto) and projeto.prazo_entrega and projeto.prazo_entrega + timedelta(days=p.atraso_dias) < hoje:
            dias = (hoje - projeto.prazo_entrega).days
            saida.append(Alerta("ruim", "Pedido atrasado",
                                f"{dias} dias depois do prazo de {projeto.prazo_entrega:%d/%m/%Y}", projeto))
        c = saldo_cliente(projeto, contexto)
        if c and c.saldo > 0 and projeto.etapa == Projeto.Etapa.ENTREGUE:
            saida.append(Alerta("ruim", "Cliente com saldo depois da entrega",
                                f"falta receber {_reais(c.saldo)}", projeto))
        if (projeto.etapa == Projeto.Etapa.ENTREGUE and projeto.regime_efetivo == Projeto.Regime.PADRAO
                and not projeto.pg2_data and projeto.custo_oficina):
            pct = (projeto.primeira_percentual / CEM if projeto.primeira_percentual is not None
                   else contexto.pct("pct_primeira"))
            segunda = centavos(projeto.custo_oficina) - centavos(projeto.custo_oficina * pct)
            saida.append(Alerta("atencao", "Oficina a pagar depois da entrega",
                                f"2ª parcela de {_reais(segunda)}", projeto))
        falta = faltando(projeto)
        if falta:
            saida.append(Alerta("info", "Card incompleto", "falta " + ", ".join(falta), projeto))
    proj = proj or projecao(lista, contexto, 30)
    if proj.minimo < 0:
        saida.insert(0, Alerta("ruim", "Caixa negativo nos próximos 30 dias",
                               f"pior ponto {_reais(proj.minimo)} em {proj.dia_minimo:%d/%m/%Y}"))
    return saida


def _br(valor):
    """1234.5 vira "1.234,50"; o sinal vai antes do R$, quem chama põe."""
    texto = f"{abs(centavos(valor)):,.2f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _reais(valor):
    return ("−R$ " if valor < 0 else "R$ ") + _br(valor)


def _pct_br(numero):
    return f"{numero}".replace(".", ",").replace("-", "−")


# -----------------------------------------------------------------------------------
# Fechamento do mês: competência e caixa lado a lado
# -----------------------------------------------------------------------------------

@dataclass
class Competencia:
    vendas: Decimal = ZERO
    custo: Decimal = ZERO
    outros: Decimal = ZERO
    taxa: Decimal = ZERO
    fixos: Decimal = ZERO
    pedidos: int = 0
    baixas: list = field(default_factory=list)

    @property
    def margem(self):
        return self.vendas - self.custo - self.outros - self.taxa

    @property
    def margem_percentual(self):
        return (self.margem / self.vendas * CEM).quantize(Decimal("0.1")) if self.vendas else None

    @property
    def resultado(self):
        return self.margem - self.fixos


@dataclass
class Caixa:
    entradas: Decimal = ZERO
    oficinas: Decimal = ZERO
    fixos: Decimal = ZERO
    prolabore: Decimal = ZERO

    @property
    def resultado(self):
        return self.entradas - self.oficinas - self.fixos - self.prolabore


@dataclass
class Fechamento:
    ano: int
    mes: int
    competencia: Competencia
    caixa: Caixa

    @property
    def rotulo(self):
        return rotulo_mes(self.ano, self.mes)


def limites_do_mes(ano, mes):
    return date(ano, mes, 1), date(ano, mes, calendar.monthrange(ano, mes)[1])


def fechar(ano, mes, lista, contexto):
    inicio, fim = limites_do_mes(ano, mes)
    comp = Competencia(fixos=fixos_por_mes(contexto))
    minimo = contexto.pct("margem_minima")
    for projeto in lista:
        if not projeto.incluir or not projeto.data_venda or not (inicio <= projeto.data_venda <= fim):
            continue
        m = margem(projeto, contexto)
        if not m:
            continue
        comp.vendas += m.venda
        comp.custo += projeto.custo_oficina or ZERO
        comp.outros += m.custo - (projeto.custo_oficina or ZERO)
        comp.taxa += m.taxa
        comp.pedidos += 1
        if m.fracao < minimo:
            comp.baixas.append((projeto, m))
    caixa = Caixa()
    caixa.oficinas = sum((s.valor for s in todas_as_saidas(lista, contexto).saidas
                          if inicio <= s.data <= fim), ZERO)
    caixa.fixos = sum((s.valor for s in saidas_fixas(inicio, fim, contexto)), ZERO)
    hoje = contexto.hoje
    for projeto in lista:
        c = saldo_cliente(projeto, contexto)
        if c and c.saldo > 0 and c.data and inicio <= max(c.data, hoje) <= fim:
            caixa.entradas += c.saldo
    caixa.prolabore = sum((m.valor for m in MovimentoEntreEmpresas.objects.filter(
        tipo=MovimentoEntreEmpresas.Tipo.PROLABORE, empresa=MovimentoEntreEmpresas.Empresa.STUDIO,
        cancelado_em__isnull=True, data__gte=inicio, data__lte=fim)), ZERO)
    return Fechamento(ano, mes, comp, caixa)


# -----------------------------------------------------------------------------------
# Entre empresas
# -----------------------------------------------------------------------------------

@dataclass
class MesEntreEmpresas:
    ano: int
    mes: int
    movimentos: list
    prolabores: list
    no_mes: Decimal
    acumulado: Decimal

    @property
    def rotulo(self):
        return rotulo_mes(self.ano, self.mes)


def entre_empresas():
    """Os meses, do mais novo para o mais velho, com o saldo acumulado até cada um.

    Saldo positivo: a Cabana deve ao Studio. Negativo: o Studio deve à Cabana.
    """
    validos = list(MovimentoEntreEmpresas.objects.filter(cancelado_em__isnull=True)
                   .order_by("data", "id"))
    meses, acumulado = [], ZERO
    chaves = sorted({(m.data.year, m.data.month) for m in validos})
    for ano, mes in chaves:
        do_mes = [m for m in validos if (m.data.year, m.data.month) == (ano, mes)]
        movimentos = [m for m in do_mes if m.tipo != MovimentoEntreEmpresas.Tipo.PROLABORE]
        no_mes = sum((m.sinal * m.valor for m in movimentos), ZERO)
        acumulado += no_mes
        meses.append(MesEntreEmpresas(ano, mes, movimentos,
                                      [m for m in do_mes if m.tipo == MovimentoEntreEmpresas.Tipo.PROLABORE],
                                      no_mes, acumulado))
    prolabore = {e: sum((m.valor for m in validos if m.tipo == MovimentoEntreEmpresas.Tipo.PROLABORE
                         and m.empresa == e), ZERO) for e in MovimentoEntreEmpresas.Empresa.values}
    return list(reversed(meses)), acumulado, prolabore
