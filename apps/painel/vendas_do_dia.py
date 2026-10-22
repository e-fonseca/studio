"""A relação dos produtos vendidos num dia, com custo, lucro em reais e em porcentagem.

Pedido do Edson em 11/10/2026. É a pergunta mais simples que a loja faz e a que o
sistema não respondia: "o que eu vendi hoje e quanto sobrou disso". O produto
importado guarda a soma de 12 meses, então quem responde é o item da venda
(ItemVendaImportada), importado desde a 1.24.0.

Duas decisões que mudam o número e que estão na tela em palavras:

1. O custo é o do DIA DA VENDA, o que o SET gravou no item quando passou no caixa, e
   não o custo do cadastro de hoje. É isso que faz o lucro ser o lucro realizado: se o
   fornecedor subiu o preço depois, o dia continua valendo o que valia.

2. Quando o SET não gravou o custo na venda, o sistema usa o custo do CADASTRO e marca
   a linha como estimada. Isso não é luxo: na cópia de 20/09/2026, até 24/08/2026 o
   custo da venda falta em 0,5% dos itens e de 25/08/2026 em diante falta em 70% a 100%
   deles, todo dia. Sem a estimativa, o dia que a loja abre na tela ficaria sem lucro.

3. Produto que saiu do cadastro não tem custo nenhum: fica na lista marcado como sem
   custo e FORA da conta do lucro. Tratar custo vazio como zero daria margem de 100% e
   uma relação de lucro que a loja não teve.

O faturamento daqui é a soma dos ITENS. O cupom pode ter desconto dado no fechamento,
que não está em item nenhum, então a tela mostra os dois e a diferença entre eles.
"""

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum

from apps.importacao.models import ItemVendaImportada, VendaImportada

ZERO = Decimal("0")
CEM = Decimal("100")
CENTAVO = Decimal("0.01")

# Quantos dias para trás a caixa de seleção oferece. Trinta cobre "ontem", "semana
# passada" e o fechamento do mês, que é para o que ele vai usar.
DIAS_PARA_ESCOLHER = 30

# Acima disto a tela paginaria sem motivo: o dia mais movimentado da cópia de
# 20/09/2026 teve 203 itens. O limite existe só para a tela não explodir num dia
# atípico; o CSV leva tudo.
MAXIMO_DE_LINHAS = 500


def _decimal(valor):
    return valor if isinstance(valor, Decimal) else Decimal(str(valor or 0))


def _porcento(parte, total):
    if not total:
        return None
    return (_decimal(parte) * CEM / _decimal(total)).quantize(Decimal("0.1"))


@dataclass
class Linha:
    """Um produto na relação do dia, já somado se saiu em mais de uma venda.

    Três bases de custo convivem na mesma linha, porque o mesmo produto pode sair duas
    vezes no dia: com o custo gravado na venda, com o custo estimado pelo cadastro, e sem
    custo nenhum. O que a tela mostra é a soma das duas primeiras, e a palavra "estimado"
    aparece sempre que a segunda entrou.
    """

    codigo: str
    descricao: str
    grupo: str = ""
    quantidade: Decimal = ZERO
    valor: Decimal = ZERO
    # Pela base do custo: o que o SET gravou na venda, o que veio do cadastro, e o que
    # não tem custo nenhum. Lucro e margem valem sobre a soma das duas primeiras.
    valor_do_dia: Decimal = ZERO
    custo_do_dia: Decimal = ZERO
    valor_estimado: Decimal = ZERO
    custo_estimado: Decimal = ZERO
    valor_sem_custo: Decimal = ZERO
    vendas: int = 0

    @property
    def custo(self):
        return self.custo_do_dia + self.custo_estimado

    @property
    def valor_com_custo(self):
        return self.valor_do_dia + self.valor_estimado

    @property
    def sem_custo(self):
        """Nenhuma unidade deste produto tem custo, nem o do cadastro."""
        return self.valor_com_custo <= ZERO

    @property
    def estimado(self):
        """Alguma parte do custo saiu do cadastro de hoje, e não da venda."""
        return self.custo_estimado > ZERO

    @property
    def so_estimado(self):
        return self.estimado and self.custo_do_dia <= ZERO

    @property
    def custo_parcial(self):
        """Parte das unidades não tem custo nenhum: ela fica fora do lucro da linha."""
        return not self.sem_custo and self.valor_sem_custo > ZERO

    @property
    def lucro(self):
        if self.sem_custo:
            return None
        return self.valor_com_custo - self.custo

    @property
    def margem(self):
        if self.sem_custo:
            return None
        return _porcento(self.lucro, self.valor_com_custo)

    @property
    def prejuizo(self):
        """Vendeu por menos do que custou. Acontece, e é o que ele precisa ver."""
        lucro = self.lucro
        return lucro is not None and lucro < ZERO

    @property
    def prejuizo_confirmado(self):
        """Prejuízo com o custo da VENDA, não com estimativa.

        A diferença importa: produto vendido a peso (pedra, geodo) tem custo de cadastro
        por quilo e venda por fração de quilo, então a estimativa aparece como prejuízo
        sem que a loja tenha perdido nada. Avisar isso como prejuízo seria dar alarme
        falso justamente na tela que ele vai abrir todo dia.
        """
        return self.prejuizo and not self.estimado

    @property
    def base_do_custo(self):
        """De onde saiu o custo desta linha, em uma palavra, para a tela e o CSV."""
        if self.sem_custo:
            return "sem custo"
        if self.so_estimado:
            return "estimado"
        if self.estimado:
            return "parte estimado"
        return "do dia"

    @property
    def custo_unitario_medio(self):
        quantidade = self.quantidade_com_custo
        if quantidade <= 0:
            return None
        return (self.custo / quantidade).quantize(CENTAVO)

    @property
    def quantidade_com_custo(self):
        """Quantas unidades entraram na conta do lucro, por regra de três do valor.

        A quantidade por base de custo não é somada na consulta de propósito: seriam três
        colunas a mais numa tabela de 32 mil linhas para mostrar um custo médio. O valor
        é o que decide a conta, e a proporção dele é a mesma.
        """
        if self.valor <= ZERO or self.sem_custo:
            return ZERO
        return (self.quantidade * self.valor_com_custo / self.valor).quantize(Decimal("0.001"))

    @property
    def preco_medio(self):
        if self.quantidade <= 0:
            return None
        return (self.valor / self.quantidade).quantize(CENTAVO)


@dataclass
class Resultado:
    dia = None
    dias: list = field(default_factory=list)
    linhas: list = field(default_factory=list)

    cupons: int = 0
    itens: int = 0
    faturamento: Decimal = ZERO
    total_dos_cupons: Decimal = ZERO
    custo_do_dia: Decimal = ZERO
    custo_estimado: Decimal = ZERO
    valor_do_dia: Decimal = ZERO
    valor_estimado: Decimal = ZERO
    produtos_estimados: int = 0
    produtos_sem_custo: int = 0
    valor_sem_custo: Decimal = ZERO
    cortou_linhas: bool = False

    importacao = None
    data_corte = None

    @property
    def tem_dados(self):
        return bool(self.linhas)

    @property
    def custo(self):
        """O custo do que saiu: o gravado na venda mais o estimado pelo cadastro."""
        return self.custo_do_dia + self.custo_estimado

    @property
    def valor_com_custo(self):
        return self.valor_do_dia + self.valor_estimado

    @property
    def lucro(self):
        return self.valor_com_custo - self.custo

    @property
    def margem(self):
        return _porcento(self.lucro, self.valor_com_custo)

    @property
    def tudo_tem_custo(self):
        return self.produtos_sem_custo == 0

    @property
    def tem_estimativa(self):
        return self.produtos_estimados > 0

    @property
    def fatia_estimada(self):
        """Quanto do dia está em cima de estimativa, para a tela dizer em porcentagem."""
        return _porcento(self.valor_estimado, self.faturamento)

    @property
    def desconto_no_fechamento(self):
        """O que o cupom cobrou a menos do que a soma dos itens.

        Sai negativo se o cupom cobrou a mais (frete, acréscimo). A tela só mostra a
        linha quando há diferença, para não botar um zero no meio dos números.
        """
        return self.faturamento - self.total_dos_cupons

    @property
    def ticket(self):
        if not self.cupons:
            return None
        return (self.total_dos_cupons / self.cupons).quantize(CENTAVO)

    @property
    def e_o_dia_da_importacao(self):
        return self.dia is not None and self.dia == self.data_corte


def dias_disponiveis(importacao, quantos=DIAS_PARA_ESCOLHER):
    """Os dias com venda nesta importação, do mais novo para o mais velho.

    Só os que têm venda: oferecer um domingo fechado seria oferecer uma tela vazia.
    """
    if importacao is None or importacao.data_corte is None:
        return []
    desde = importacao.data_corte - timedelta(days=quantos * 2)
    return list(
        VendaImportada.objects.filter(importacao=importacao, data__gte=desde)
        .values_list("data", flat=True).distinct().order_by("-data")[:quantos]
    )


def _dia_pedido(importacao, dia, disponiveis):
    """Qual dia a tela mostra: o pedido, se existir; senão o último com venda."""
    if dia and dia in disponiveis:
        return dia
    if dia:
        # Pediu um dia sem venda: respeita a escolha e mostra a tela vazia dizendo isso.
        return dia
    if disponiveis:
        return disponiveis[0]
    return importacao.data_corte if importacao else None


def calcular(importacao, dia=None, limite=MAXIMO_DE_LINHAS):
    """A relação do dia: uma linha por produto, mais os totais do dia.

    Agrupa por código porque o mesmo produto sai em vendas diferentes no mesmo dia, e
    a relação que ele pediu é por produto, não por cupom.

    `limite=0` traz tudo, que é o que o arquivo para o Excel e o e-mail pedem.
    """
    resultado = Resultado()
    resultado.importacao = importacao
    if importacao is None:
        return resultado
    resultado.data_corte = importacao.data_corte
    resultado.dias = dias_disponiveis(importacao)
    resultado.dia = _dia_pedido(importacao, dia, resultado.dias)
    if resultado.dia is None:
        return resultado

    do_dia = ItemVendaImportada.objects.filter(
        venda__importacao=importacao, venda__data=resultado.dia)

    # Três bases de custo, nesta ordem de preferência: o custo gravado na venda, o custo
    # do cadastro como estimativa, e nenhum custo.
    #
    # Os apelidos começam com "soma_" porque apelido igual ao nome do campo faz a soma
    # seguinte apontar para a soma anterior em vez de para a coluna, e o erro só aparece
    # na segunda soma do mesmo campo ("'quantidade' is an aggregate").
    do_set = Q(custo_total__isnull=False)
    estimado = Q(custo_total__isnull=True, custo_estimado_total__isnull=False)
    nenhum = Q(custo_total__isnull=True, custo_estimado_total__isnull=True)
    agrupado = (
        do_dia.values("codigo", "descricao", "grupo")
        .annotate(
            soma_quantidade=Sum("quantidade"),
            soma_valor=Sum("valor_total"),
            soma_custo_do_dia=Sum("custo_total", filter=do_set),
            soma_valor_do_dia=Sum("valor_total", filter=do_set),
            soma_custo_estimado=Sum("custo_estimado_total", filter=estimado),
            soma_valor_estimado=Sum("valor_total", filter=estimado),
            soma_valor_sem_custo=Sum("valor_total", filter=nenhum),
            quantas_vendas=Count("venda", distinct=True),
        )
        .order_by("-soma_valor")
    )

    linhas = [
        Linha(
            codigo=registro["codigo"],
            descricao=registro["descricao"] or registro["codigo"],
            grupo=registro["grupo"],
            quantidade=_decimal(registro["soma_quantidade"]),
            valor=_decimal(registro["soma_valor"]),
            valor_do_dia=_decimal(registro["soma_valor_do_dia"]),
            custo_do_dia=_decimal(registro["soma_custo_do_dia"]),
            valor_estimado=_decimal(registro["soma_valor_estimado"]),
            custo_estimado=_decimal(registro["soma_custo_estimado"]),
            valor_sem_custo=_decimal(registro["soma_valor_sem_custo"]),
            vendas=registro["quantas_vendas"],
        )
        for registro in (agrupado if not limite else agrupado[: limite + 1])
    ]
    resultado.cortou_linhas = bool(limite) and len(linhas) > limite
    resultado.linhas = linhas[:limite] if limite else linhas

    # Os totais saem da consulta inteira, e não das linhas mostradas: cortar a lista
    # não pode mudar o faturamento do dia.
    totais = do_dia.aggregate(
        quantos_itens=Count("id"),
        soma_valor=Sum("valor_total"),
        soma_custo_do_dia=Sum("custo_total", filter=do_set),
        soma_valor_do_dia=Sum("valor_total", filter=do_set),
        soma_custo_estimado=Sum("custo_estimado_total", filter=estimado),
        soma_valor_estimado=Sum("valor_total", filter=estimado),
        soma_valor_sem_custo=Sum("valor_total", filter=nenhum),
        quantos_estimados=Count("id", filter=estimado),
        quantos_sem_custo=Count("id", filter=nenhum),
    )
    resultado.itens = totais["quantos_itens"] or 0
    resultado.faturamento = _decimal(totais["soma_valor"])
    resultado.custo_do_dia = _decimal(totais["soma_custo_do_dia"])
    resultado.valor_do_dia = _decimal(totais["soma_valor_do_dia"])
    resultado.custo_estimado = _decimal(totais["soma_custo_estimado"])
    resultado.valor_estimado = _decimal(totais["soma_valor_estimado"])
    resultado.valor_sem_custo = _decimal(totais["soma_valor_sem_custo"])
    resultado.produtos_estimados = totais["quantos_estimados"] or 0
    resultado.produtos_sem_custo = totais["quantos_sem_custo"] or 0

    cupons = VendaImportada.objects.filter(
        importacao=importacao, data=resultado.dia).aggregate(n=Count("id"), soma=Sum("valor"))
    resultado.cupons = cupons["n"] or 0
    resultado.total_dos_cupons = _decimal(cupons["soma"])
    return resultado


def linhas_do_csv(resultado):
    """A relação inteira em linhas de texto, para o CSV e para o e-mail.

    Devolve cabeçalho e linhas já formatados com vírgula decimal: quem abre no Excel
    da loja espera vírgula, e quem lê no e-mail espera o número como na tela.
    """
    cabecalho = ["Código", "Produto", "Grupo", "Quantidade", "Valor vendido",
                 "Custo", "Base do custo", "Lucro", "Margem %"]
    corpo = []
    for linha in resultado.linhas:
        corpo.append([
            linha.codigo,
            linha.descricao,
            linha.grupo,
            _quantidade(linha.quantidade),
            _numero(linha.valor),
            _numero(linha.custo) if not linha.sem_custo else "",
            linha.base_do_custo,
            _numero(linha.lucro) if not linha.sem_custo else "",
            _numero(linha.margem) if linha.margem is not None else "",
        ])
    return cabecalho, corpo


def _numero(valor):
    if valor is None:
        return ""
    return f"{valor:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


def _quantidade(valor):
    """12 em vez de 12,000, como o filtro `quantidade` da tela."""
    if valor is None:
        return ""
    texto = f"{valor:f}"
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return texto.replace(".", ",")
