"""Dashboard do varejo: os números da loja em gráficos, com filtros.

Pedido do Edson em 07/10/2026: uma tela de dashboard com gráficos, estatísticas e
filtros, no formato que o varejo usa. O que o varejo olha é sempre o mesmo
conjunto, e é ele que está aqui:

- faturamento, número de vendas e ticket médio, cada um comparado com o período
  anterior de igual tamanho (é a comparação que diz se melhorou ou piorou);
- margem bruta do cadastro, cobertura do estoque em meses e ruptura (produto que
  vende e está sem saldo), que é o lado do estoque;
- faturamento mês a mês com o mesmo mês do ano passado ao lado, curva ABC dos
  produtos, participação por grupo, campeões de faturamento e de margem;
- dia da semana, forma de pagamento e hora do dia.

Duas restrições do dado mandam no desenho da tela, e ela diz as duas em voz alta:

1. O SET não traz o item da venda, só a venda inteira. Então filtrar por grupo ou
   por fornecedor não mexe em faturamento, ticket, dia da semana nem forma de
   pagamento: esses blocos são sempre a loja toda. Os filtros de grupo e de
   fornecedor valem para os blocos de produto e de estoque.
2. Venda por produto é de 12 meses, calculada na importação (`receita_12m`). Por
   isso os blocos de produto não acompanham o filtro de período.

Os gráficos são SVG desenhado aqui, sem biblioteca: o sistema roda na loja e não
depende de baixar nada da internet.

Desde a 1.41.0 a tela tem o jeito do Grafana, que o Edson mandou de modelo em
31/10/2026 ("a visualização fica bem bonita e fácil de entender"): quadros escuros,
número grande com a cor da situação, minigráfico embaixo de cada número, linha do
tempo, mostrador e rosca, e a lista do que fazer com a gravidade de cada item. As
contas não mudaram; o que este arquivo ganhou foi a GEOMETRIA desses desenhos
(`Faisca`, `GraficoDeLinha`, `Rosca`), feita aqui e não no template porque o Django
escreve número com vírgula, e coordenada com vírgula não desenha nada.
"""

import calendar
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.db.models import Count, F, Q, Sum
from django.db.models.functions import Substr

from apps.caixa.dinheiro import nome_da_forma
from apps.compras.sugestoes import so_mercadoria
from apps.core import curva_abc
from apps.core.templatetags.cabana import contagem, reais
from apps.importacao.models import ProdutoImportado, VendaImportada

ZERO = Decimal("0")
CEM = Decimal("100")

# (valor na URL, rótulo na tela, dias para trás)
PERIODOS = (
    ("12m", "12 meses", 365),
    ("90d", "90 dias", 90),
    ("30d", "30 dias", 30),
    ("7d", "7 dias", 7),
)
PERIODO_PADRAO = "12m"
DIAS_DO_PERIODO = dict((chave, dias) for chave, _, dias in PERIODOS)
ROTULO_DO_PERIODO = dict((chave, rotulo) for chave, rotulo, _ in PERIODOS)

DIAS_DA_SEMANA = ("Domingo", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado")
MESES_CURTOS = ("", "jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")

# Quantos meses o gráfico mostra. A importação guarda 25 meses, e 13 é o que cabe na
# tela do celular sem a barra virar risco: um ano fechado mais o mês de agora.
MESES_NO_GRAFICO = 13
# Quantas linhas as listas de campeões mostram. Dez é o costume do varejo e é o que
# alguém lê de uma vez.
QUANTOS_CAMPEOES = 10
# Quantos grupos a rosca separa antes de juntar o resto em "outros".
QUANTOS_GRUPOS = 8
# Faixas de hora do dia, no formato que a loja fala.
FAIXAS_DE_HORA = ((8, 11, "Manhã (8h-11h)"), (11, 14, "Meio-dia (11h-14h)"),
                  (14, 17, "Tarde (14h-17h)"), (17, 24, "Fim do dia (17h em diante)"))

# O rótulo curto de cada faixa, para caber embaixo da coluna do gráfico.
ROTULO_CURTO_DA_HORA = {"Manhã (8h-11h)": ("Manhã", "8h-11h"),
                        "Meio-dia (11h-14h)": ("Meio-dia", "11h-14h"),
                        "Tarde (14h-17h)": ("Tarde", "14h-17h"),
                        "Fim do dia (17h em diante)": ("Fim do dia", "17h em diante")}
# A cobertura acima disto fica na cor de atenção. É o "uns três meses" que a explicação
# do número já dizia desde a 1.18.0; o quadro só passou a pintar o que o texto dizia.
COBERTURA_DE_ATENCAO = Decimal("3")
# Até 31 dias o minigráfico tem um ponto por dia; acima disso, um por semana. Ponto por
# dia num ano inteiro seria um serrote: a loja vende quase metade no domingo.
DIAS_POR_PONTO_LONGO = 7

# Cores das fatias, as mesmas variáveis que a Visão geral usa.
CORES = ("--cor-fatia-1", "--cor-fatia-2", "--cor-fatia-3", "--cor-fatia-4",
         "--cor-fatia-5", "--cor-fatia-6", "--cor-fatia-7", "--cor-fatia-8", "--cor-fatia-9")


def _decimal(valor):
    try:
        return Decimal(valor or 0)
    except (TypeError, InvalidOperation):
        return ZERO


def _milhar(numero):
    """11274 vira 11.274. Para o texto do cartão, que é lido por gente da loja."""
    return f"{int(numero):,}".replace(",", ".")


def _porcento(parte, total):
    if not total:
        return ZERO
    return (_decimal(parte) * CEM / _decimal(total)).quantize(Decimal("0.1"))


def _largura(parte, total):
    """Largura ou altura de barra, de 0 a 100, em número inteiro.

    Inteiro de propósito: isto vai dentro de um `style=` e o Django localiza número
    no template, então um Decimal sairia como "66,5%" — CSS inválido, barra com
    altura zero. Quem é texto na tela (a porcentagem ao lado) continua Decimal, que
    é justamente onde a vírgula tem que aparecer. Valor que existe nunca some: o
    mínimo é 1%, como no gráfico de compra e venda do painel.
    """
    if not total or _decimal(parte) <= ZERO:
        return 0
    return max(1, int(_decimal(parte) * CEM / _decimal(total)))


def _variacao(agora, antes):
    """Quanto o número subiu ou caiu, em porcentagem. None quando não há com que comparar."""
    if not antes:
        return None
    return ((_decimal(agora) - _decimal(antes)) * CEM / _decimal(antes)).quantize(Decimal("0.1"))


def _coordenada(numero):
    """Número para dentro de um desenho SVG: ponto decimal, uma casa, nunca vírgula."""
    return f"{float(numero):.1f}"


@dataclass
class Faisca:
    """O minigráfico embaixo do número grande, como no Grafana.

    Mostra a FORMA do período, não a escala: vai do menor ao maior valor da própria
    série, para uma semana fraca aparecer como vale. O número que vale é o de cima; o
    desenho só diz se o período subiu, caiu ou oscilou. Coordenadas em 0..100 × 0..32,
    esticadas pelo CSS (`preserveAspectRatio="none"`).
    """

    linha: str = ""
    area: str = ""
    pontos: int = 0
    por: str = ""  # "dia" ou "semana", para a ajuda dizer o que cada ponto é

    @property
    def tem(self):
        return bool(self.linha)


ALTURA_DA_FAISCA = 32


def _faisca(valores, por="dia"):
    if len(valores) < 2:
        return Faisca()
    numeros = [float(valor or 0) for valor in valores]
    menor, maior = min(numeros), max(numeros)
    alto, baixo = 3.0, ALTURA_DA_FAISCA - 1.0
    passo = 100.0 / (len(numeros) - 1)
    pontos = []
    for posicao, numero in enumerate(numeros):
        if maior == menor:
            y = (alto + baixo) / 2
        else:
            y = baixo - (numero - menor) / (maior - menor) * (baixo - alto)
        pontos.append((posicao * passo, y))
    linha = "M" + " L".join(f"{_coordenada(x)} {_coordenada(y)}" for x, y in pontos)
    area = f"{linha} L100.0 {ALTURA_DA_FAISCA}.0 L0.0 {ALTURA_DA_FAISCA}.0 Z"
    return Faisca(linha=linha, area=area, pontos=len(numeros), por=por)


@dataclass
class Kpi:
    """Um número grande do topo, com a comparação já pronta."""

    chave: str
    rotulo: str
    valor: Decimal
    formato: str = "numero"  # numero, reais, porcento, meses
    variacao: Decimal | None = None
    comparado_com: str = ""
    explicacao: str = ""
    # Quando subir é ruim (ruptura, capital parado), o verde e o vermelho trocam.
    subir_e_bom: bool = True
    faisca: Faisca = field(default_factory=Faisca)
    # Número sem comparação que tem um limite já escrito na explicação ("acima de uns
    # três meses, é dinheiro parado"): passou dele, o número fica na cor de atenção.
    atencao_acima_de: Decimal | None = None

    @property
    def nivel(self):
        if self.atencao_acima_de is not None and self.valor > self.atencao_acima_de:
            return "atencao"
        if self.variacao is None or self.variacao == ZERO:
            return "neutro"
        subiu = self.variacao > ZERO
        return "bom" if subiu == self.subir_e_bom else "ruim"

    @property
    def texto(self):
        """O número como aparece no quadro: R$ 1.538.337,98, 16.361, 2,4%, 12,4 meses."""
        if self.formato == "reais":
            return reais(self.valor)
        if self.formato in ("porcento", "meses"):
            numero = Decimal(self.valor).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
            numero = numero.quantize(Decimal("1")) if numero == numero.to_integral() else numero
            escrito = f"{numero}".replace(".", ",")
            if self.formato == "porcento":
                return f"{escrito}%"
            return f"{escrito} {'mês' if numero == 1 else 'meses'}"
        return contagem(self.valor)

    @property
    def letras(self):
        """Quantas letras o número ocupa. O quadro do Dashboard tem a largura de
        "16.361", e "R$ 1.538.337,98" saía cortado no fim (1.41.0): o CSS divide a
        largura do quadro por este número para escolher o tamanho da letra."""
        return len(self.texto)


@dataclass
class Mes:
    rotulo: str
    valor: Decimal
    vendas: int = 0
    valor_ano_passado: Decimal | None = None
    altura: int = 0
    altura_ano_passado: int | None = None
    # Mês que ainda não terminou: o do corte dos dados, quase sempre.
    parcial: bool = False
    dia_parcial: int | None = None
    # Faturamento que sobe é bom; conta paga que sobe é ruim. O mesmo desenho serve às
    # duas telas (Contas a pagar, 1.47.0), e só a cor da porcentagem troca de lado.
    mais_e_bom: bool = True

    @property
    def variacao(self):
        return _variacao(self.valor, self.valor_ano_passado)

    @property
    def sentido(self):
        """A cor da porcentagem embaixo do mês: "bom", "ruim" ou "neutro"."""
        variacao = self.variacao
        if variacao is None or variacao == 0:
            return "neutro"
        return "bom" if (variacao > 0) == self.mais_e_bom else "ruim"

    @property
    def ate_o_dia(self):
        """Texto curto para a coluna do mês que ainda está correndo."""
        return f"até dia {self.dia_parcial}" if self.parcial and self.dia_parcial else ""


@dataclass
class Fatia:
    nome: str
    valor: Decimal
    fatia: Decimal = ZERO
    cor: str = CORES[0]
    traco: str = ""
    giro: str = ""
    largura: int = 0
    # Embaixo da coluna do gráfico só cabe uma palavra: "Dom", "Manhã".
    curto: str = ""
    complemento: str = ""
    quantos: int = 0
    # Para onde o nome da fatia leva, quando leva: a rosca das contas em aberto abre a
    # lista daquela fatia (1.47.0). Vazio, a legenda é só texto, como no Dashboard.
    endereco: str = ""


@dataclass
class Rosca:
    """Uma rosca com legenda, como os quadros "Status dos Hosts" do Grafana."""

    fatias: list = field(default_factory=list)
    centro: str = ""          # o número grande no furo
    centro_legenda: str = ""  # a palavra embaixo dele

    @property
    def tem(self):
        return bool(self.fatias)


def _fatiar(fatias, total):
    """Porcentagem, traço e giro de cada fatia, em cima do círculo de perímetro 100.

    O traço começa no topo (giro 25) e anda no sentido do relógio. Fica em texto com
    ponto decimal porque vai dentro de um `style=`.
    """
    giro = Decimal("25")
    for fatia in fatias:
        fatia.fatia = _porcento(fatia.valor, total)
        fatia.traco = f"{fatia.fatia} {CEM - fatia.fatia}"
        fatia.giro = str(giro)
        giro = giro - fatia.fatia
        if giro < ZERO:
            giro += CEM
    return fatias


@dataclass
class GraficoDeLinha:
    """Faturamento mês a mês em linhas: este ano e o mesmo mês do ano passado.

    Antes eram duas barras por mês. A linha é o desenho do Grafana que o Edson mandou
    de modelo, e lê-se do mesmo jeito: a de cima vendeu mais. Cada mês fica no MEIO da
    sua coluna (`(posição + 0,5) / meses`), para o ponto cair em cima do nome do mês,
    que é texto da página e não do desenho — texto dentro de SVG esticado sai torto.
    """

    agora: str = ""
    agora_area: str = ""
    parcial: str = ""        # o trecho do mês que ainda corre, tracejado
    antes: str = ""
    marcas: list = field(default_factory=list)  # as linhas de grade, de baixo para cima
    colunas: int = 0

    @property
    def tem(self):
        return bool(self.agora)


LARGURA_DA_LINHA, ALTURA_DA_LINHA = 1000, 300


@dataclass
class Marca:
    """Uma linha de grade do eixo: o rótulo, a altura em % (página) e o y (desenho).

    `escrita` diz se o rótulo aparece: "sempre", "alto" (só quando o gráfico é alto o
    bastante para ele não encostar no vizinho, o que o CSS decide pela altura real do
    eixo) ou "" (só a linha, sem rótulo).
    """

    rotulo: str
    altura: int
    y: str
    escrita: str = "sempre"


# As faixas que o Edson pediu no eixo vertical (02/11/2026): "no gráfico principal do
# dashboard, inserir na vertical mais faixas de valores 10.000 50.000 80.000 120.000
# 150.000 250.000". Entram junto com as marcas redondas do passo, e só as que cabem na
# escala do gráfico: num ano de R$ 600 mil por mês a de 10 mil seria um fio colado no zero.
FAIXAS_DO_FATURAMENTO = (10_000, 50_000, 80_000, 120_000, 150_000, 250_000)

# Distância mínima entre dois rótulos, em porcentagem da altura do eixo. "Sempre" é a
# que cabe no celular (o eixo tem uns 190 px e a letra 10 px); "alto" é a que cabe no
# computador, onde o eixo passa de 400 px. Abaixo de "alto", o rótulo encostaria no
# vizinho em qualquer tela e fica só a linha.
_FOLGA_SEMPRE = 5.5
_FOLGA_NO_ALTO = 2.8


def _marcas(topo, passo, faixas=FAIXAS_DO_FATURAMENTO):
    """As linhas de grade: as redondas do passo e as faixas pedidas, de baixo para cima.

    Quando dois rótulos ficariam um em cima do outro, ganha a faixa que o Edson pediu,
    depois a marca redonda; o zero é o que menos diz, porque o pé do gráfico já é o
    zero. O outro rótulo fica só para o gráfico alto, ou some, e a linha continua.
    """
    valores = {}
    valor = 0.0
    while valor <= topo + 0.001:
        valores[round(valor, 2)] = 1 if valor else 0
        valor += passo
    for faixa in faixas:
        if faixa < topo:
            valores[float(faixa)] = 2

    alturas = {v: v / topo * 100 for v in valores}
    sempre, no_alto = [], []
    for v in sorted(valores, key=lambda v: (-valores[v], v)):
        perto_de_sempre = min((abs(alturas[v] - alturas[o]) for o in sempre), default=100)
        perto_de_todos = min((abs(alturas[v] - alturas[o]) for o in sempre + no_alto),
                             default=100)
        if perto_de_sempre >= _FOLGA_SEMPRE:
            sempre.append(v)
        elif perto_de_todos >= _FOLGA_NO_ALTO:
            no_alto.append(v)

    marcas = []
    for v in sorted(valores):
        escrita = "sempre" if v in sempre else ("alto" if v in no_alto else "")
        marcas.append(Marca(_reais_curto(v), int(round(alturas[v])),
                            _coordenada(ALTURA_DA_LINHA - alturas[v] / 100 * ALTURA_DA_LINHA),
                            escrita))
    return marcas


def _escala(maior):
    """O topo do eixo num número redondo (100 mil, 175 mil) e o passo das marcas."""
    maior = float(maior or 0)
    if maior <= 0:
        return 1.0, 0.25
    bruto = maior / 4
    potencia = 10 ** len(str(int(bruto))) / 10
    for multiplo in (1, 2, 2.5, 5, 10):
        passo = multiplo * potencia
        if passo >= bruto:
            break
    topo = passo * -(-maior // passo)
    return topo, passo


def _reais_curto(valor):
    """"R$ 150 mil" no eixo: o valor inteiro está no nome do mês, ao passar o mouse."""
    valor = float(valor)
    if valor >= 1_000_000:
        texto = f"{valor / 1_000_000:.1f}".rstrip("0").rstrip(".")
        return f"R$ {texto.replace('.', ',')} mi"
    if valor >= 1000:
        texto = f"{valor / 1000:.1f}".rstrip("0").rstrip(".")
        return f"R$ {texto.replace('.', ',')} mil"
    return f"R$ {int(valor)}"


def _grafico_de_linha(meses, faixas=FAIXAS_DO_FATURAMENTO):
    """A linha do tempo de qualquer valor mês a mês, com o mesmo mês do ano passado.

    `faixas` são as linhas de grade pedidas além das redondas. Contas a pagar usa as
    mesmas do faturamento: a loja paga e vende na mesma escala de mês, e o Edson pediu o
    mesmo formato de gráfico (04/11/2026).
    """
    if len(meses) < 2:
        return GraficoDeLinha()
    maior = max(max(m.valor, m.valor_ano_passado or ZERO) for m in meses)
    topo, passo = _escala(maior)
    quantos = len(meses)

    def ponto(posicao, valor):
        x = (posicao + 0.5) / quantos * LARGURA_DA_LINHA
        y = ALTURA_DA_LINHA - float(valor) / topo * ALTURA_DA_LINHA
        return f"{_coordenada(x)} {_coordenada(y)}"

    # O mês que ainda corre sai da linha cheia e vira um trecho tracejado: ele tem só
    # os dias até o corte, e ligado com a linha cheia pareceria um tombo nas vendas.
    ultimo_cheio = quantos - 2 if meses[-1].parcial else quantos - 1
    agora = "M" + " L".join(ponto(i, m.valor) for i, m in enumerate(meses[:ultimo_cheio + 1]))
    area = (f"{agora} L{ponto(ultimo_cheio, 0)} L{ponto(0, 0)} Z")
    parcial = ""
    if meses[-1].parcial and ultimo_cheio >= 0:
        parcial = f"M{ponto(ultimo_cheio, meses[ultimo_cheio].valor)} L{ponto(quantos - 1, meses[-1].valor)}"

    # O ano passado pode ter buraco (mês sem número): a linha para ali e recomeça.
    trechos, atual = [], []
    for posicao, mes in enumerate(meses):
        if mes.valor_ano_passado is None:
            if atual:
                trechos.append(atual)
            atual = []
            continue
        atual.append(ponto(posicao, mes.valor_ano_passado))
    if atual:
        trechos.append(atual)
    antes = " ".join("M" + " L".join(trecho) for trecho in trechos if len(trecho) > 1)

    return GraficoDeLinha(agora=agora, agora_area=area, parcial=parcial, antes=antes,
                          marcas=_marcas(topo, passo, faixas), colunas=quantos)


# A ordem das cores do gráfico de anos: o ano de agora é a linha verde, como o "este ano"
# do Dashboard; o ano passado é a laranja, como o "ano passado"; o retrasado é a azul.
PAPEIS_DOS_ANOS = ("agora", "antes", "retrasado")


@dataclass
class LinhaDoAno:
    """Um ano do gráfico de anos (1.48.0), de janeiro a dezembro.

    `valores` são os doze meses, com None onde não há número: o mês que ainda não chegou,
    ou o mês que a foto do SET não traz inteiro. O mês que ainda corre (`mes_parcial`, só
    no ano de agora) sai tracejado, como na linha do Dashboard, e só o ano de agora leva a
    área por baixo. Mês sem vizinho com número não tem com quem formar linha: vira ponto
    (`pontos`), senão um janeiro sozinho sumiria do desenho.
    """

    ano: int
    valores: list
    papel: str = "agora"
    mes_parcial: int | None = None
    caminho: str = ""
    area: str = ""
    parcial: str = ""
    pontos: str = ""


@dataclass
class GraficoDeAnos:
    """Contas pagas de janeiro a dezembro, uma linha para cada um dos últimos três anos.

    Pedido do Edson em 04/11/2026, em Contas a pagar: *"nesse mesmo gráfico do contas a
    pagar manter sempre os últimos 3 anos"*. É o desenho da linha do tempo do Dashboard
    (mesma escala, mesmas faixas no eixo, mesmo SVG esticado), com o mês fixo no eixo de
    baixo em vez dos 13 meses que andam: assim cada ano é uma linha inteira, e o mês que
    costuma pesar aparece nos três anos, um sobre o outro.
    """

    linhas: list = field(default_factory=list)   # do ano mais antigo ao de agora: o de agora por cima
    marcas: list = field(default_factory=list)
    colunas: int = 12

    @property
    def tem(self):
        return any(linha.caminho or linha.parcial or linha.pontos for linha in self.linhas)

    @property
    def legenda(self):
        """Do ano de agora para o mais antigo, a ordem em que se lê a legenda e a tabela."""
        return list(reversed(self.linhas))


def _trechos(meses_e_valores):
    """Os pedaços seguidos de (mês, valor): onde falta um mês, a linha para e recomeça."""
    trechos, atual, anterior = [], [], None
    for mes, valor in meses_e_valores:
        if atual and mes != anterior + 1:
            trechos.append(atual)
            atual = []
        atual.append((mes, valor))
        anterior = mes
    if atual:
        trechos.append(atual)
    return trechos


def _grafico_de_anos(linhas, faixas=FAIXAS_DO_FATURAMENTO):
    """A geometria de cada ano: a linha cheia, a área do ano de agora, o tracejado e os pontos."""
    valores = [valor for linha in linhas for valor in linha.valores if valor is not None]
    if not valores:
        return GraficoDeAnos()
    topo, passo = _escala(max(valores))

    def ponto(mes, valor):
        x = (mes - 0.5) / 12 * LARGURA_DA_LINHA
        y = ALTURA_DA_LINHA - float(valor) / topo * ALTURA_DA_LINHA
        return f"{_coordenada(x)} {_coordenada(y)}"

    for linha in linhas:
        cheios = [(mes, valor) for mes, valor in enumerate(linha.valores, start=1)
                  if valor is not None and mes != linha.mes_parcial]
        trechos = _trechos(cheios)
        juntos = [trecho for trecho in trechos if len(trecho) > 1]
        soltos = [trecho[0] for trecho in trechos if len(trecho) == 1]
        linha.caminho = " ".join("M" + " L".join(ponto(m, v) for m, v in trecho) for trecho in juntos)
        if linha.papel == "agora":
            linha.area = " ".join(
                f"M{ponto(trecho[0][0], 0)} L" + " L".join(ponto(m, v) for m, v in trecho)
                + f" L{ponto(trecho[-1][0], 0)} Z"
                for trecho in juntos
            )
        parcial = linha.mes_parcial
        if parcial and linha.valores[parcial - 1] is not None:
            anterior = linha.valores[parcial - 2] if parcial > 1 else None
            if anterior is not None:
                linha.parcial = f"M{ponto(parcial - 1, anterior)} L{ponto(parcial, linha.valores[parcial - 1])}"
            else:
                soltos.append((parcial, linha.valores[parcial - 1]))
        # Ponto é um traço de tamanho zero com a ponta redonda (`.monitor-tempo-ponto`):
        # círculo de verdade, porque o traço não estica junto com o desenho.
        linha.pontos = " ".join(f"M{ponto(m, v)} l0 0" for m, v in soltos)

    return GraficoDeAnos(linhas=list(linhas), marcas=_marcas(topo, passo, faixas))


# Os desenhos do Dashboard servem a outras telas no mesmo formato (1.47.0: Contas a
# pagar). Os nomes com sublinhado continuam sendo os de dentro deste arquivo e dos testes.
grafico_de_anos = _grafico_de_anos
fatiar = _fatiar
porcento = _porcento
variacao = _variacao


@dataclass
class Campeao:
    codigo: str
    descricao: str
    grupo: str
    valor: Decimal
    unidades: Decimal = ZERO
    margem: Decimal | None = None
    # Barra do quadro, de 0 a 100, contra o primeiro da lista. Inteiro: vai num style=.
    largura: int = 0


@dataclass
class ClasseAbc:
    letra: str
    produtos: int = 0
    receita: Decimal = ZERO
    fatia_dos_produtos: Decimal = ZERO
    fatia_da_receita: Decimal = ZERO
    # O que a classe é, em três palavras de loja: a letra sozinha não diz nada a quem
    # nunca ouviu falar em curva ABC.
    titulo: str = ""
    explicacao: str = ""
    # Largura da barra, de 0 a 100, em porcentagem do faturamento. Inteiro porque vai
    # dentro de um style= e o Django localiza número no template: Decimal sairia "31,2"
    # e o CSS ignoraria a linha.
    largura_receita: int = 0


@dataclass
class Dashboard:
    importacao = None
    periodo: str = PERIODO_PADRAO
    rotulo_periodo: str = ""
    desde = None
    ate = None
    filtro_grupo: str = ""
    filtro_fornecedor: str = ""
    grupos_disponiveis: list = field(default_factory=list)
    fornecedores_disponiveis: list = field(default_factory=list)
    kpis_da_venda: list = field(default_factory=list)
    kpis_do_estoque: list = field(default_factory=list)
    meses: list = field(default_factory=list)
    grupos: list = field(default_factory=list)
    abc: list = field(default_factory=list)
    campeoes_faturamento: list = field(default_factory=list)
    campeoes_margem: list = field(default_factory=list)
    linha_dos_meses: GraficoDeLinha = field(default_factory=GraficoDeLinha)
    # O lado do estoque em desenho: o mostrador da margem e as duas roscas.
    margem: Decimal = ZERO
    margem_traco: str = "0 100"
    rosca_da_ruptura: Rosca = field(default_factory=Rosca)
    rosca_do_estoque: Rosca = field(default_factory=Rosca)
    rosca_das_formas: Rosca = field(default_factory=Rosca)
    rosca_dos_grupos: Rosca = field(default_factory=Rosca)
    dias_da_semana: list = field(default_factory=list)
    formas: list = field(default_factory=list)
    horas: list = field(default_factory=list)
    produtos_no_filtro: int = 0
    vendas_no_periodo: int = 0
    tem_dados: bool = False

    @property
    def filtrou_produto(self):
        return bool(self.filtro_grupo or self.filtro_fornecedor)


def _janela(importacao, periodo):
    """Do que até quando. O fim é a data de corte da importação, não hoje."""
    ate = importacao.data_corte
    dias = DIAS_DO_PERIODO.get(periodo, DIAS_DO_PERIODO[PERIODO_PADRAO])
    return ate - timedelta(days=dias - 1), ate, dias


def _resumo_das_vendas(importacao, desde, ate):
    linha = VendaImportada.objects.filter(
        importacao=importacao, data__gte=desde, data__lte=ate
    ).aggregate(quantas=Count("id"), valor=Sum("valor"), desconto=Sum("desconto"))
    return {
        "vendas": linha["quantas"] or 0,
        "faturamento": _decimal(linha["valor"]),
        "desconto": _decimal(linha["desconto"]),
    }


def _serie(importacao, ate, dias):
    """O período em pontos para os minigráficos: um por dia até 31 dias, um por semana acima.

    As semanas contam para trás a partir do corte, então a última é sempre inteira; o
    pedaço de semana que sobra no começo do período fica de fora do desenho, senão o
    minigráfico começaria com um tombo que é só falta de dias.
    """
    tamanho = 1 if dias <= 31 else DIAS_POR_PONTO_LONGO
    quantos = dias // tamanho
    comeco = ate - timedelta(days=quantos * tamanho - 1)
    pontos = [{"faturamento": ZERO, "vendas": 0, "desconto": ZERO} for _ in range(quantos)]
    linhas = (VendaImportada.objects
              .filter(importacao=importacao, data__gte=comeco, data__lte=ate)
              .values("data").order_by()
              .annotate(valor=Sum("valor"), quantas=Count("id"), desconto=Sum("desconto")))
    for linha in linhas:
        posicao = quantos - 1 - (ate - linha["data"]).days // tamanho
        if 0 <= posicao < quantos:
            pontos[posicao]["faturamento"] += _decimal(linha["valor"])
            pontos[posicao]["vendas"] += linha["quantas"]
            pontos[posicao]["desconto"] += _decimal(linha["desconto"])
    return pontos, ("dia" if tamanho == 1 else "semana")


def _faiscas_da_venda(pontos, por):
    """Os quatro minigráficos do topo, na ordem dos números."""
    tickets, descontos = [], []
    ultimo_ticket = ZERO
    for ponto in pontos:
        # Dia sem venda não tem ticket: repete o anterior em vez de despencar a zero,
        # que desenharia uma queda de ticket que não aconteceu.
        if ponto["vendas"]:
            ultimo_ticket = ponto["faturamento"] / ponto["vendas"]
        tickets.append(ultimo_ticket)
        descontos.append(_porcento(ponto["desconto"], ponto["faturamento"]))
    return {
        "faturamento": _faisca([p["faturamento"] for p in pontos], por),
        "vendas": _faisca([p["vendas"] for p in pontos], por),
        "ticket": _faisca(tickets, por),
        "desconto": _faisca(descontos, por),
    }


def _kpis_da_venda(importacao, desde, ate, dias):
    """Os quatro números da venda, cada um contra o período anterior de igual tamanho."""
    agora = _resumo_das_vendas(importacao, desde, ate)
    antes = _resumo_das_vendas(importacao, desde - timedelta(days=dias), desde - timedelta(days=1))
    comparado = f"{dias} dias anteriores"

    def ticket(dados):
        if not dados["vendas"]:
            return ZERO
        return (dados["faturamento"] / dados["vendas"]).quantize(Decimal("0.01"))

    kpis = [
        Kpi("faturamento", "Faturamento", agora["faturamento"], "reais",
            _variacao(agora["faturamento"], antes["faturamento"]), comparado,
            "Soma das vendas do período, como o SET registrou: é o total da venda, já "
            "sem o desconto dado no balcão. A Visão geral soma o preço dos itens, antes "
            "do desconto, por isso o número de lá é um pouco maior."),
        Kpi("vendas", "Vendas", Decimal(agora["vendas"]), "numero",
            _variacao(agora["vendas"], antes["vendas"]), comparado,
            "Quantas vendas a loja fez, não quantas peças."),
        Kpi("ticket", "Ticket médio", ticket(agora), "reais",
            _variacao(ticket(agora), ticket(antes)), comparado,
            "Quanto o cliente gasta por compra: faturamento dividido pelo número de vendas."),
        Kpi("desconto", "Desconto dado", _porcento(agora["desconto"], agora["faturamento"]),
            "porcento",
            _variacao(_porcento(agora["desconto"], agora["faturamento"]),
                      _porcento(antes["desconto"], antes["faturamento"])),
            comparado,
            "Quanto do faturamento saiu em desconto no período.", subir_e_bom=False),
    ]
    pontos, por = _serie(importacao, ate, dias)
    faiscas = _faiscas_da_venda(pontos, por)
    for kpi in kpis:
        kpi.faisca = faiscas.get(kpi.chave, Faisca())
    return agora, kpis


def _produtos(importacao, grupo, fornecedor):
    consulta = ProdutoImportado.objects.filter(importacao=importacao)
    if grupo:
        consulta = consulta.filter(grupo=grupo)
    if fornecedor:
        consulta = consulta.filter(fornecedor=fornecedor)
    return consulta


def _kpis_do_estoque(consulta):
    """Margem, cobertura, ruptura e capital parado: o lado do estoque, sempre 12 meses."""
    # Saldo negativo conta como zero, e não como dinheiro a menos. São 1.456 produtos no
    # SET com saldo abaixo de zero: isso é erro de cadastro de uma loja que nunca fez
    # contagem, não mercadoria devendo na prateleira. Somar o negativo tirava R$ 37 mil do
    # "parado" e R$ 127 mil do valor do estoque, e fazia esta tela discordar da Lista de
    # compra e do "Antes de comprar", que sempre filtraram saldo positivo.
    totais = consulta.aggregate(
        quantos=Count("id"),
        receita=Sum("receita_12m"),
        estoque_ao_custo=Sum(F("estoque") * F("custo"), filter=Q(estoque__gt=0)),
        custo_do_vendido=Sum(F("vendas_12m") * F("custo")),
    )
    quantos = totais["quantos"] or 0
    receita = _decimal(totais["receita"])
    estoque_ao_custo = _decimal(totais["estoque_ao_custo"])
    custo_do_vendido = _decimal(totais["custo_do_vendido"])

    margem = ZERO
    if receita:
        margem = _porcento(receita - custo_do_vendido, receita)
    cobertura = ZERO
    if custo_do_vendido:
        cobertura = (estoque_ao_custo / (custo_do_vendido / Decimal("12"))).quantize(Decimal("0.1"))

    vendem = consulta.filter(vendas_12m__gt=0)
    com_venda = vendem.count()
    sem_saldo = vendem.filter(estoque__lte=0).count()
    # so_mercadoria porque consumo próprio da loja não é dinheiro que se põe para girar:
    # sem isso esta tela dava R$ 4,9 mil a mais que o "O que fazer agora" e a Sugestões,
    # com o mesmo nome em cima do número.
    parado = _decimal(so_mercadoria(consulta.filter(vendas_12m__lte=0, estoque__gt=0)).aggregate(
        valor=Sum(F("estoque") * F("custo")))["valor"])
    negativos = consulta.filter(estoque__lt=0).count()
    numeros = {"margem": margem, "estoque_ao_custo": estoque_ao_custo, "parado": parado,
               "com_venda": com_venda, "sem_saldo": sem_saldo}

    return quantos, numeros, [
        Kpi("margem", "Margem bruta", margem, "porcento", None, "",
            "Quanto sobra da venda depois do custo da mercadoria, pelos valores do cadastro "
            "do SET, pesado pelo que cada produto vendeu em 12 meses."),
        Kpi("cobertura", "Cobertura do estoque", cobertura, "meses", None, "",
            "Quantos meses de venda o estoque de hoje aguenta, no ritmo dos últimos 12 meses. "
            "Acima de uns três meses, é dinheiro parado na prateleira.",
            atencao_acima_de=COBERTURA_DE_ATENCAO),
        Kpi("ruptura", "Ruptura", _porcento(sem_saldo, com_venda), "porcento", None, "",
            f"{_milhar(sem_saldo)} de {_milhar(com_venda)} produtos que venderam no ano "
            "estão sem saldo no SET. "
            "É venda perdida por falta, mas o saldo do SET é estimativa enquanto a loja não "
            "fizer a contagem física, então o número verdadeiro é menor que este.",
            subir_e_bom=False),
        Kpi("parado", "Parado sem vender", parado, "reais", None, "",
            "Dinheiro em estoque de produto que não vendeu nenhuma unidade em 12 meses."
            + (f" {_milhar(negativos)} produtos estão com saldo negativo no SET e contam "
               "como zero aqui: saldo negativo é erro de cadastro, não mercadoria."
               if negativos else ""),
            subir_e_bom=False),
    ]


def _meses(importacao):
    """Faturamento mês a mês, com o mesmo mês do ano passado ao lado.

    Vem de `detalhe["vendas_mes"]`, calculado na importação, porque ele guarda 25
    meses — a tabela de vendas guarda 12, que não daria para comparar com o ano
    passado.

    O último mês quase nunca está fechado: os dados vão até o dia do backup. Comparar
    sete dias deste mês com o mês inteiro do ano passado dava "-84%", uma queda que não
    existe — foi o que o Edson viu em 08/10/2026. Então o mês que ainda corre é comparado
    com o MESMO PEDAÇO do ano passado (`detalhe["mes_parcial"]`), do dia 1 ao mesmo dia, e
    a coluna diz "até dia 7". Importação antiga não tem esse número: aí o mês aparece sem
    comparação nenhuma, que é melhor do que uma errada.
    """
    bruto = (importacao.detalhe or {}).get("vendas_mes") or []
    por_mes = {}
    for linha in bruto:
        if len(linha) < 4:
            continue
        ano, mes, valor, vendas = int(linha[0]), int(linha[1]), _decimal(linha[2]), int(linha[3])
        por_mes[(ano, mes)] = (valor, vendas)
    chaves = sorted(por_mes)[-MESES_NO_GRAFICO:]

    corte = importacao.data_corte
    parcial = (importacao.detalhe or {}).get("mes_parcial") or []
    preparados = []
    for ano, mes in chaves:
        valor, vendas = por_mes[(ano, mes)]
        antes = por_mes.get((ano - 1, mes))
        valor_antes = antes[0] if antes else None
        e_parcial = bool(corte and (ano, mes) == (corte.year, corte.month)
                         and corte.day < calendar.monthrange(ano, mes)[1])
        if e_parcial:
            valor_antes = _ano_passado_ate_o_dia(parcial, ano, mes)
        preparados.append((ano, mes, valor, vendas, valor_antes, e_parcial))

    maior = max((p[2] for p in preparados), default=ZERO)
    for _ano, _mes, _valor, _vendas, valor_antes, _parcial in preparados:
        if valor_antes:
            maior = max(maior, valor_antes)

    meses = []
    for ano, mes, valor, vendas, valor_antes, e_parcial in preparados:
        mes_pronto = Mes(
            rotulo=f"{MESES_CURTOS[mes]}/{str(ano)[2:]}",
            valor=valor.quantize(Decimal("0.01")),
            vendas=vendas,
            valor_ano_passado=valor_antes.quantize(Decimal("0.01")) if valor_antes else None,
            altura=_largura(valor, maior),
            parcial=e_parcial,
            dia_parcial=corte.day if e_parcial and corte else None,
        )
        if valor_antes:
            mes_pronto.altura_ano_passado = _largura(valor_antes, maior)
        meses.append(mes_pronto)
    return meses


def _ano_passado_ate_o_dia(parcial, ano, mes):
    """Quanto o mesmo mês do ano passado tinha vendido até o mesmo dia.

    None quando a importação é anterior à 1.20.1 e não traz esse número, ou quando o
    ano passado não teve venda nenhuma nesse pedaço: nos dois casos é melhor não
    comparar do que comparar com o mês inteiro.
    """
    if len(parcial) < 4 or int(parcial[0]) != ano or int(parcial[1]) != mes:
        return None
    valor = _decimal(parcial[3])
    return valor if valor and valor > ZERO else None


def _grupos(consulta):
    """Participação de cada grupo no faturamento de 12 meses, em rosca."""
    linhas = list(
        consulta.exclude(receita_12m__lte=0)
        .values("grupo")
        .annotate(valor=Sum("receita_12m"))
        .order_by("-valor")
    )
    total = sum((_decimal(linha["valor"]) for linha in linhas), ZERO)
    if not total:
        return []
    principais = linhas[:QUANTOS_GRUPOS]
    resto = sum((_decimal(linha["valor"]) for linha in linhas[QUANTOS_GRUPOS:]), ZERO)
    fatias = [
        Fatia(nome=(linha["grupo"] or "sem grupo"), valor=_decimal(linha["valor"]),
              cor=CORES[posicao % len(CORES)])
        for posicao, linha in enumerate(principais)
    ]
    if resto:
        fatias.append(Fatia(nome=f"outros {len(linhas) - QUANTOS_GRUPOS} grupos", valor=resto,
                            cor=CORES[len(fatias) % len(CORES)]))
    return _fatiar(fatias, total)


def _abc(consulta):
    """Curva ABC: A são os produtos que fazem os primeiros 80% do faturamento.

    O que o varejo faz com ela: A nunca pode faltar, C não merece estoque.

    O desenho já mudou duas vezes em 08/10/2026, as duas a pedido do Edson. Era a curva
    de Pareto, uma linha subindo num quadro sem números; virou duas faixas repartidas em
    A, B e C, que ele também achou confusa. Agora é a mesma lista de barras horizontais
    das outras caixas da tela (dia da semana, forma de pagamento): uma linha por classe,
    com o nome do grupo em palavras, quantos produtos são e quanto do faturamento fazem.
    O contraste que é a curva ABC fica escrito em uma frase acima da lista, que é como
    ele próprio conta a história para o sogro.
    """
    receitas = [
        _decimal(valor)
        for valor in consulta.exclude(receita_12m__lte=0)
        .order_by("-receita_12m").values_list("receita_12m", flat=True)
    ]
    total = sum(receitas, ZERO)
    if not total:
        return []
    # A regra de onde cada faixa termina mora em apps/core/curva_abc.py, porque o
    # inventário usa a MESMA classificação para decidir de quanto em quanto tempo
    # contar cada produto. Duas cópias da regra seria o mesmo produto sendo classe A
    # numa tela e B noutra.
    classes = {
        letra: ClasseAbc(letra, titulo=curva_abc.TITULOS[letra],
                         explicacao=curva_abc.EXPLICACOES[letra])
        for letra in curva_abc.LETRAS
    }
    for receita, letra in zip(receitas, curva_abc.letras(receitas)):
        classe = classes[letra]
        classe.produtos += 1
        classe.receita += receita
    for classe in classes.values():
        classe.fatia_dos_produtos = _porcento(classe.produtos, len(receitas))
        classe.fatia_da_receita = _porcento(classe.receita, total)
        # O mínimo de 1 que o _largura devolve deixa visível a barra da classe pequena.
        classe.largura_receita = _largura(classe.receita, total)
        classe.receita = classe.receita.quantize(Decimal("0.01"))
    return [classes["A"], classes["B"], classes["C"]]


def _campeoes(consulta):
    """Os dez maiores de faturamento e os dez maiores de margem em reais."""
    por_faturamento = [
        Campeao(codigo=p.codigo, descricao=p.descricao, grupo=p.grupo,
                valor=_decimal(p.receita_12m).quantize(Decimal("0.01")),
                unidades=_decimal(p.vendas_12m))
        for p in consulta.exclude(receita_12m__lte=0).order_by("-receita_12m")[:QUANTOS_CAMPEOES]
    ]
    por_margem = [
        Campeao(codigo=p["codigo"], descricao=p["descricao"], grupo=p["grupo"],
                valor=_decimal(p["ganho"]).quantize(Decimal("0.01")),
                unidades=_decimal(p["vendas_12m"]),
                margem=_porcento(_decimal(p["ganho"]), _decimal(p["receita_12m"])))
        for p in consulta.exclude(receita_12m__lte=0).filter(custo__gt=0)
        .annotate(ganho=F("receita_12m") - F("vendas_12m") * F("custo"))
        .values("codigo", "descricao", "grupo", "ganho", "receita_12m", "vendas_12m")
        .order_by("-ganho")[:QUANTOS_CAMPEOES]
    ]
    for lista in (por_faturamento, por_margem):
        maior = max((campeao.valor for campeao in lista), default=ZERO)
        for campeao in lista:
            campeao.largura = _largura(campeao.valor, maior)
    return por_faturamento, por_margem


def _barras(linhas, rotulo_de):
    """Transforma linhas agregadas em barras com largura em porcentagem."""
    maior = max((_decimal(linha["valor"]) for linha in linhas), default=ZERO)
    total = sum((_decimal(linha["valor"]) for linha in linhas), ZERO)
    fatias = []
    for posicao, linha in enumerate(linhas):
        valor = _decimal(linha["valor"]).quantize(Decimal("0.01"))
        fatias.append(Fatia(
            nome=rotulo_de(linha),
            valor=valor,
            fatia=_porcento(valor, total),
            largura=_largura(valor, maior),
            cor=CORES[posicao % len(CORES)],
        ))
    return fatias


def _recortes_da_venda(importacao, desde, ate):
    """Dia da semana, forma de pagamento e hora do dia, no período escolhido."""
    vendas = VendaImportada.objects.filter(importacao=importacao, data__gte=desde, data__lte=ate)

    por_dia = {linha["dia_da_semana"]: linha for linha in vendas.values("dia_da_semana")
               .annotate(valor=Sum("valor"), quantas=Count("id"))}
    dias = _barras(
        [{"valor": por_dia.get(numero, {}).get("valor") or ZERO,
          "quantas": por_dia.get(numero, {}).get("quantas") or 0, "nome": nome}
         for numero, nome in enumerate(DIAS_DA_SEMANA)],
        lambda linha: linha["nome"],
    )
    for dia in dias:
        dia.curto = dia.nome[:3]

    # "Cartão de crédito" e "Dinheiro", e não "CARTAO CREDITO" e "AVISTA": os nomes do SET
    # viram os da loja pela mesma função do e-mail do caixa. Dois nomes do SET para a
    # mesma forma (AVISTA e DINHEIRO) somam numa linha só.
    por_forma = {}
    for linha in (vendas.exclude(forma_pagamento="").values("forma_pagamento").order_by()
                  .annotate(valor=Sum("valor"), quantas=Count("id"))):
        nome = nome_da_forma(linha["forma_pagamento"])
        atual = por_forma.setdefault(nome, {"nome": nome, "valor": ZERO, "quantas": 0})
        atual["valor"] += _decimal(linha["valor"])
        atual["quantas"] += linha["quantas"]
    formas = _barras(sorted(por_forma.values(), key=lambda linha: -linha["valor"]),
                     lambda linha: linha["nome"])

    # A hora vem como texto "HH:MM:SS" do SET; os dois primeiros dígitos bastam.
    cru = (vendas.exclude(hora="").annotate(hh=Substr("hora", 1, 2)).values("hh")
           .annotate(valor=Sum("valor"), quantas=Count("id")))
    somas = {}
    for linha in cru:
        try:
            hora = int(linha["hh"])
        except (TypeError, ValueError):
            continue
        for comeco, fim, nome in FAIXAS_DE_HORA:
            if comeco <= hora < fim:
                atual = somas.setdefault(nome, {"valor": ZERO, "quantas": 0, "nome": nome})
                atual["valor"] += _decimal(linha["valor"])
                atual["quantas"] += linha["quantas"]
                break
    horas = _barras(
        [somas[nome] for _, _, nome in FAIXAS_DE_HORA if nome in somas],
        lambda linha: linha["nome"],
    )
    for hora in horas:
        hora.curto, hora.complemento = ROTULO_CURTO_DA_HORA.get(hora.nome, (hora.nome, ""))
    return dias, formas, horas


def montar(importacao, periodo=PERIODO_PADRAO, grupo="", fornecedor=""):
    """Monta o dashboard inteiro. Sem importação concluída, devolve a tela vazia."""
    painel = Dashboard()
    if importacao is None or not importacao.data_corte:
        return painel

    periodo = periodo if periodo in DIAS_DO_PERIODO else PERIODO_PADRAO
    desde, ate, dias = _janela(importacao, periodo)
    painel.importacao = importacao
    painel.periodo = periodo
    painel.rotulo_periodo = ROTULO_DO_PERIODO[periodo]
    painel.desde, painel.ate = desde, ate
    painel.tem_dados = True

    todos = ProdutoImportado.objects.filter(importacao=importacao)
    # order_by() vazio de propósito: o modelo ordena por código, e com a ordenação de pé
    # o DISTINCT passa a ser por (grupo, código) — a lista vinha com os onze mil produtos
    # em vez dos trinta e cinco grupos.
    painel.grupos_disponiveis = sorted(
        nome for nome in todos.exclude(grupo="").order_by().values_list("grupo", flat=True).distinct()
        if nome)
    painel.fornecedores_disponiveis = sorted(
        nome for nome in todos.exclude(fornecedor="").order_by()
        .values_list("fornecedor", flat=True).distinct()
        if nome)
    painel.filtro_grupo = grupo if grupo in painel.grupos_disponiveis else ""
    painel.filtro_fornecedor = fornecedor if fornecedor in painel.fornecedores_disponiveis else ""

    resumo, painel.kpis_da_venda = _kpis_da_venda(importacao, desde, ate, dias)
    painel.vendas_no_periodo = resumo["vendas"]

    consulta = _produtos(importacao, painel.filtro_grupo, painel.filtro_fornecedor)
    painel.produtos_no_filtro, numeros, painel.kpis_do_estoque = _kpis_do_estoque(consulta)

    painel.meses = _meses(importacao)
    painel.linha_dos_meses = _grafico_de_linha(painel.meses)
    painel.grupos = _grupos(consulta)
    painel.abc = _abc(consulta)
    painel.campeoes_faturamento, painel.campeoes_margem = _campeoes(consulta)
    painel.dias_da_semana, painel.formas, painel.horas = _recortes_da_venda(importacao, desde, ate)
    _desenhos_do_estoque(painel, numeros)
    painel.rosca_das_formas = _rosca_das_formas(painel.formas)
    painel.rosca_dos_grupos = Rosca(fatias=painel.grupos)
    return painel


def _desenhos_do_estoque(painel, numeros):
    """O mostrador da margem e as roscas de ruptura e de estoque parado.

    São os mesmos números dos cartões de estoque (`_kpis_do_estoque`), só desenhados:
    a rosca da ruptura reparte os produtos que venderam no ano entre com saldo e sem
    saldo; a do estoque reparte o dinheiro na prateleira entre o que girou e o parado.
    """
    margem = numeros["margem"]
    painel.margem = margem
    painel.margem_traco = f"{min(max(margem, ZERO), CEM)} 100"

    com_venda, sem_saldo = numeros["com_venda"], numeros["sem_saldo"]
    if com_venda:
        painel.rosca_da_ruptura = Rosca(
            fatias=_fatiar([
                Fatia("Com saldo no SET", Decimal(com_venda - sem_saldo), cor="--mon-verde",
                      quantos=com_venda - sem_saldo),
                Fatia("Sem saldo no SET", Decimal(sem_saldo), cor="--mon-vermelho",
                      quantos=sem_saldo),
            ], Decimal(com_venda)),
            centro=f"{_porcento(sem_saldo, com_venda)}%".replace(".", ","),
            centro_legenda="sem saldo",
        )

    total, parado = numeros["estoque_ao_custo"], numeros["parado"]
    if total:
        girou = max(total - parado, ZERO)
        painel.rosca_do_estoque = Rosca(
            fatias=_fatiar([
                Fatia("Vendeu no ano", girou.quantize(Decimal("0.01")), cor="--mon-verde"),
                Fatia("Parado sem vender", parado.quantize(Decimal("0.01")), cor="--mon-laranja"),
            ], total),
            centro=f"{_porcento(parado, total)}%".replace(".", ","),
            centro_legenda="parado",
        )


def _rosca_das_formas(formas):
    """A forma de pagamento em rosca, com as mesmas fatias da lista de barras."""
    if not formas:
        return Rosca()
    total = sum((forma.valor for forma in formas), ZERO)
    fatias = [Fatia(forma.nome, forma.valor, cor=CORES[posicao % len(CORES)])
              for posicao, forma in enumerate(formas)]
    return Rosca(fatias=_fatiar(fatias, total))
