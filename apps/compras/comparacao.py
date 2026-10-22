"""Comparar um período de venda com o mesmo período do ano passado.

Pedido do Edson em 14/10/2026: "análise de sugestão de compra de mercadorias precisa
além dos últimos meses com filtros, também permitir comparar com o mesmo período do ano
anterior".

Por que isso muda a compra: a loja vende quase tudo no fim de semana e em feriado, e o
que sai em julho não é o que sai em dezembro. Olhar só os últimos doze meses esconde a
estação. Quem compra precisa saber o que o mesmo mês vendeu no ano passado, porque é
esse o mês que está chegando.

Duas decisões que a tela precisa explicar, porque sem elas o número engana:

1. **Só mês fechado entra.** O mês da data de corte quase nunca está completo. Comparar
   vinte dias deste setembro com o setembro inteiro do ano passado acusaria uma queda
   que não existe — foi exatamente o erro que o gráfico do Dashboard cometeu em
   08/10/2026. Então o período termina no último mês fechado, e a tela diz qual é.
2. **Produto que não vendeu no ano passado não é produto que caiu.** Pode ser produto
   novo, e a variação em porcentagem não existe (dividir por zero). Esses aparecem como
   "não vendia no ano passado", que é informação, e não como +100%.
"""

from calendar import monthrange
from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Q, Sum

from apps.compras.sugestoes import so_mercadoria
from apps.core import procura
from apps.importacao.models import VendaMensalDoProduto

ZERO = Decimal("0")

PERIODOS = (
    ("3m", "3 meses", 3),
    ("6m", "6 meses", 6),
    ("12m", "12 meses", 12),
)
PERIODO_PADRAO = "3m"
# O período escolhido a dedo, mês a mês, em vez de um dos três prontos (1.30.0: "permitir
# edição por período"). Vale só quando a tela manda o mês de início e o de fim.
PERIODO_LIVRE = "livre"
MESES_DO_PERIODO = {chave: meses for chave, _, meses in PERIODOS}
ROTULO_DO_PERIODO = {chave: rotulo for chave, rotulo, _ in PERIODOS}

MESES = ("", "janeiro", "fevereiro", "março", "abril", "maio", "junho",
         "julho", "agosto", "setembro", "outubro", "novembro", "dezembro")

# Quantas linhas a tela abre e quantas entram em cada lista curta. O arquivo leva tudo.
POR_PAGINA = 60
QUANTOS_DESTAQUES = 8
# Quantos anos o quadro "o mesmo período, ano a ano" tenta mostrar (1.30.0: "trazer outro
# comparativo de vendas do mesmo período dos anos anteriores"). Ele mostra só os que
# couberem inteiros na foto, e a foto guarda cinco anos desde a 1.30.0.
ANOS_NO_BLOCO = 5


@dataclass
class LinhaComparada:
    codigo: str
    descricao: str
    grupo: str = ""
    fornecedor: str = ""
    estoque: Decimal = ZERO
    unidades: Decimal = ZERO
    unidades_antes: Decimal = ZERO
    receita: Decimal = ZERO
    receita_antes: Decimal = ZERO

    @property
    def diferenca(self):
        """Quanto este produto faturou a mais (ou a menos) que no ano passado."""
        return self.receita - self.receita_antes

    @property
    def novo(self):
        """Não vendia no ano passado: não é crescimento, é produto novo na prateleira."""
        return self.receita_antes <= ZERO and self.receita > ZERO

    @property
    def sumiu(self):
        return self.receita_antes > ZERO and self.receita <= ZERO

    @property
    def variacao(self):
        """A variação em porcentagem, ou None quando não há com o que comparar."""
        if self.receita_antes <= ZERO:
            return None
        return int(round((self.receita - self.receita_antes) * 100 / self.receita_antes))

    @property
    def largura(self):
        """Inteiro: decimal dentro de style= sai localizado e o navegador ignora a linha."""
        maior = max(abs(self.receita), abs(self.receita_antes))
        if maior <= ZERO:
            return 0
        return int(round(abs(self.diferenca) * 100 / maior))


@dataclass
class AnoComparado:
    """Um ano no quadro "o mesmo período, ano a ano"."""

    ano: int
    rotulo: str
    receita: Decimal = ZERO
    unidades: Decimal = ZERO
    receita_do_anterior: Decimal | None = None
    maior: Decimal = ZERO

    @property
    def variacao(self):
        """Em relação ao ano DE BAIXO na lista, que é o ano anterior a este."""
        if not self.receita_do_anterior or self.receita_do_anterior <= ZERO:
            return None
        return int(round((self.receita - self.receita_do_anterior) * 100
                         / self.receita_do_anterior))

    @property
    def diferenca(self):
        if self.receita_do_anterior is None:
            return None
        return self.receita - self.receita_do_anterior

    @property
    def largura(self):
        """Inteiro: decimal dentro de style= sai localizado e o navegador ignora a linha."""
        if self.maior <= ZERO:
            return 0
        return int(round(self.receita * 100 / self.maior))


@dataclass
class Comparacao:
    periodo: str = PERIODO_PADRAO
    meses: int = 3
    rotulo: str = ""
    rotulo_de_agora: str = ""
    rotulo_de_antes: str = ""
    tem_historico: bool = False
    mes_de_fora: str = ""
    receita: Decimal = ZERO
    receita_antes: Decimal = ZERO
    unidades: Decimal = ZERO
    unidades_antes: Decimal = ZERO
    produtos: int = 0
    subiram: int = 0
    cairam: int = 0
    novos: int = 0
    sumiram: int = 0
    cresceram: list = field(default_factory=list)
    encolheram: list = field(default_factory=list)
    linhas: list = field(default_factory=list)
    encontrados: int = 0
    mostrados: int = 0
    filtro_grupo: str = ""
    filtro_fornecedor: str = ""
    busca: str = ""
    grupos: list = field(default_factory=list)
    fornecedores: list = field(default_factory=list)
    # Os meses escolhidos a dedo, como a tela os manda e os mostra: "2026-07".
    de: str = ""
    ate: str = ""
    # Todo mês fechado que a foto guarda, do mais novo para o mais velho, para os dois
    # campos de escolher mês: [("2026-09", "setembro de 2026"), ...].
    meses_disponiveis: list = field(default_factory=list)
    anos: list = field(default_factory=list)
    meses_na_foto: int = 0
    # Frase pronta quando o mesmo período do ano passado não cabe inteiro na foto. Sem
    # ela a tela compararia um ano passado pela metade e acusaria um crescimento que não
    # existe — o mesmo erro que o gráfico do Dashboard cometeu em 08/10/2026.
    falta_historico: str = ""

    @property
    def escolhido_a_dedo(self):
        return self.periodo == PERIODO_LIVRE

    @property
    def anos_mostrados(self):
        return len(self.anos)

    @property
    def diferenca(self):
        return self.receita - self.receita_antes

    @property
    def variacao(self):
        if self.receita_antes <= ZERO:
            return None
        return int(round((self.receita - self.receita_antes) * 100 / self.receita_antes))

    @property
    def escondidos(self):
        return max(self.encontrados - self.mostrados, 0)

    @property
    def tem_linhas(self):
        return bool(self.linhas)


def _mes_fechado(corte):
    """O último mês inteiro antes da data de corte, como (ano, mês).

    Quando o corte cai no último dia do mês, esse mês está fechado e vale. Em qualquer
    outro dia, o mês corrente fica de fora: ele é um pedaço, e pedaço contra mês inteiro
    é a comparação que mente.
    """
    ultimo_dia = monthrange(corte.year, corte.month)[1]
    if corte.day >= ultimo_dia:
        return corte.year, corte.month
    if corte.month == 1:
        return corte.year - 1, 12
    return corte.year, corte.month - 1


def _janela(ano, mes, quantos):
    """Os `quantos` meses que terminam em (ano, mês), do mais antigo para o mais novo."""
    meses = []
    for passo in range(quantos - 1, -1, -1):
        total = (ano * 12 + mes - 1) - passo
        meses.append((total // 12, total % 12 + 1))
    return meses


def _rotulo(janela):
    """"julho a setembro de 2026", ou "setembro de 2026" quando é um mês só."""
    (ano_i, mes_i), (ano_f, mes_f) = janela[0], janela[-1]
    if (ano_i, mes_i) == (ano_f, mes_f):
        return f"{MESES[mes_i]} de {ano_i}"
    if ano_i == ano_f:
        return f"{MESES[mes_i]} a {MESES[mes_f]} de {ano_f}"
    return f"{MESES[mes_i]} de {ano_i} a {MESES[mes_f]} de {ano_f}"


def _valor_do_mes(ano, mes):
    """O jeito como o mês viaja na tela: "2026-09". Ordena sozinho e não tem acento."""
    return f"{ano:04d}-{mes:02d}"


def _ler_mes(texto):
    """"2026-09" vira (2026, 9). Qualquer outra coisa vira None, sem levantar erro.

    O que chega aqui veio da barra de endereço, então pode ser qualquer coisa: mês 13,
    ano com letra, campo vazio. Nada disso pode derrubar a tela.
    """
    partes = (texto or "").strip().split("-")
    if len(partes) != 2:
        return None
    try:
        ano, mes = int(partes[0]), int(partes[1])
    except ValueError:
        return None
    if not 1 <= mes <= 12 or not 2000 <= ano <= 2100:
        return None
    return ano, mes


def _quantos_meses(inicio, fim):
    """Quantos meses vão de um (ano, mês) a outro, contando os dois. Zero ou menos se invertidos."""
    (ano_i, mes_i), (ano_f, mes_f) = inicio, fim
    return (ano_f * 12 + mes_f) - (ano_i * 12 + mes_i) + 1


def _recuar(janela, anos):
    """A mesma janela de meses, tantos anos atrás."""
    return [(ano - anos, mes) for ano, mes in janela]


def _limites(importacao):
    """O primeiro e o último mês que a foto guarda INTEIROS, ou None quando não há foto.

    O começo vem da própria foto (`Importacao.mes_a_mes_desde`), que a leitura grava no
    dia 1º do mês mais antigo que trouxe. Nas fotos tiradas até a 1.29.0 esse campo está
    vazio porque a leitura começava em "corte menos 730 dias", e aí o mês mais antigo era
    um PEDAÇO de mês: comparar doze meses com os doze anteriores usava meio outubro como
    outubro inteiro e acusava um crescimento que não existe. Sem o campo, portanto, o mês
    mais antigo da foto não conta.

    O fim é o último mês fechado, pela mesma razão do outro lado do calendário.
    """
    if importacao is None or importacao.data_corte is None:
        return None
    meses = sorted(
        (linha["ano"], linha["mes"]) for linha in
        VendaMensalDoProduto.objects.filter(importacao=importacao)
        .values("ano", "mes").distinct()
    )
    if not meses:
        return None
    desde = getattr(importacao, "mes_a_mes_desde", None)
    if desde is not None:
        # O que a foto diz, e não o mês da venda mais antiga: mês sem venda nenhuma é
        # zero de verdade, não falta de dado, e cortar por ele esconderia um ano fraco.
        primeiro = (desde.year, desde.month)
    elif len(meses) > 1:
        primeiro = meses[1]
    else:
        return None
    ultimo = _mes_fechado(importacao.data_corte)
    if _quantos_meses(primeiro, ultimo) < 1:
        return None
    return primeiro, ultimo


def _somar(importacao, janela):
    """Unidades e receita de cada produto na janela de meses, numa consulta só."""
    filtro = Q()
    for ano, mes in janela:
        filtro |= Q(ano=ano, mes=mes)
    linhas = (
        VendaMensalDoProduto.objects.filter(importacao=importacao).filter(filtro)
        .values("codigo")
        .annotate(unidades=Sum("unidades"), receita=Sum("receita"))
    )
    return {linha["codigo"]: (linha["unidades"] or ZERO, linha["receita"] or ZERO)
            for linha in linhas}


def _por_mes(importacao, meses, consulta_de_produtos):
    """Unidades e receita de cada mês, numa consulta só, dos mesmos produtos.

    O quadro ano a ano não precisa de produto a produto, só do total de cada mês. Mas o
    total tem que sair dos MESMOS produtos dos cartões de cima, senão a linha de um ano
    diz um número e o cartão ao lado diz outro para o mesmo período. Por isso o filtro
    entra como subconsulta: a lista de códigos tem milhares de itens e não caberia dentro
    da pergunta.
    """
    if not meses:
        return {}
    filtro = Q()
    for ano, mes in meses:
        filtro |= Q(ano=ano, mes=mes)
    linhas = (
        VendaMensalDoProduto.objects
        .filter(importacao=importacao, codigo__in=consulta_de_produtos.values("codigo"))
        .filter(filtro)
        .values("ano", "mes")
        .annotate(unidades=Sum("unidades"), receita=Sum("receita"))
    )
    return {(linha["ano"], linha["mes"]): (linha["unidades"] or ZERO, linha["receita"] or ZERO)
            for linha in linhas}


def _consulta_de_produtos(importacao, grupo="", fornecedor="", busca=""):
    """Os produtos que o filtro deixa passar, ainda como consulta."""
    consulta = so_mercadoria(importacao.itens.all())
    if grupo:
        consulta = consulta.filter(grupo=grupo)
    if fornecedor:
        consulta = consulta.filter(fornecedor=fornecedor)
    if busca:
        consulta = consulta.filter(
            procura.filtro(busca, "descricao", "grupo", "fornecedor")
            | Q(codigo__istartswith=busca)
        )
    return consulta


def _produtos(importacao, grupo="", fornecedor="", busca=""):
    """O cadastro dos produtos que o filtro deixa passar, por código."""
    consulta = _consulta_de_produtos(importacao, grupo=grupo, fornecedor=fornecedor,
                                     busca=busca)
    return {
        dados["codigo"]: dados
        for dados in consulta.values("codigo", "descricao", "grupo", "fornecedor", "estoque")
    }


def _escolher_janela(limites, periodo, de, ate):
    """A janela de meses que a tela pediu, e o período que ela é de verdade.

    Devolve (janela, periodo, quantos meses). O período escolhido a dedo só vale quando
    os dois meses chegam, são legíveis, estão na ordem certa e cabem na foto; fora disso
    a tela cai no período pronto, que é o que ela já fazia.
    """
    primeiro, ultimo = limites
    if periodo == PERIODO_LIVRE:
        inicio, fim = _ler_mes(de), _ler_mes(ate)
        if inicio and fim and _quantos_meses(inicio, fim) >= 1:
            inicio = max(inicio, primeiro)
            fim = min(fim, ultimo)
            quantos = _quantos_meses(inicio, fim)
            if quantos >= 1:
                return _janela(fim[0], fim[1], quantos), PERIODO_LIVRE, quantos
    periodo = periodo if periodo in MESES_DO_PERIODO else PERIODO_PADRAO
    quantos = MESES_DO_PERIODO[periodo]
    return _janela(ultimo[0], ultimo[1], quantos), periodo, quantos


def _ano_a_ano(importacao, janela, primeiro, quantos_anos, consulta_de_produtos):
    """O mesmo período, ano a ano, do mais novo para o mais velho.

    Só entra o ano cuja janela cabe INTEIRA na foto: um ano que começasse antes do
    primeiro mês guardado apareceria como uma queda enorme que é só falta de dado. E com
    um ano só não há quadro nenhum — isso é o cartão de cima, não uma série.
    """
    janelas = []
    for atras in range(max(int(quantos_anos), 1)):
        recuada = _recuar(janela, atras)
        if _quantos_meses(primeiro, recuada[0]) < 1:
            break
        janelas.append(recuada)
    if len(janelas) < 2:
        return []

    soma = _por_mes(importacao, [mes for recuada in janelas for mes in recuada],
                    consulta_de_produtos)
    linhas = [
        AnoComparado(
            # O ano do FIM da janela: um período de novembro a janeiro é "de 2026", que é
            # como quem está na loja chama o Natal que acabou de passar.
            ano=recuada[-1][0],
            rotulo=_rotulo(recuada),
            unidades=sum((soma.get(mes, (ZERO, ZERO))[0] for mes in recuada), ZERO),
            receita=sum((soma.get(mes, (ZERO, ZERO))[1] for mes in recuada), ZERO),
        )
        for recuada in janelas
    ]
    # Ano mais antigo sem venda nenhuma sai da lista: a foto pode alcançar antes de a loja
    # ter o que vender, e uma fileira de "R$ 0,00" só enche a tela. Zero no MEIO fica.
    while linhas and linhas[-1].receita <= ZERO:
        linhas.pop()
    if len(linhas) < 2:
        return []

    maior = max((linha.receita for linha in linhas), default=ZERO)
    for posicao, linha in enumerate(linhas):
        linha.maior = maior
        if posicao + 1 < len(linhas):
            linha.receita_do_anterior = linhas[posicao + 1].receita
    return linhas


def montar(importacao, periodo=PERIODO_PADRAO, grupo="", fornecedor="", busca="",
           quantos=POR_PAGINA, de="", ate="", anos=ANOS_NO_BLOCO) -> Comparacao:
    """O período escolhido contra o mesmo período dos anos anteriores, produto a produto."""
    if periodo not in MESES_DO_PERIODO and periodo != PERIODO_LIVRE:
        periodo = PERIODO_PADRAO
    dados = Comparacao(periodo=periodo, meses=MESES_DO_PERIODO.get(periodo, 3),
                       rotulo=ROTULO_DO_PERIODO.get(periodo, ""), filtro_grupo=grupo,
                       filtro_fornecedor=fornecedor, busca=busca, de=de, ate=ate)
    limites = _limites(importacao)
    if limites is None:
        return dados

    primeiro, ultimo = limites
    dados.meses_na_foto = _quantos_meses(primeiro, ultimo)
    dados.meses_disponiveis = [
        (_valor_do_mes(ano_m, mes_m), f"{MESES[mes_m]} de {ano_m}")
        for ano_m, mes_m in reversed(_janela(ultimo[0], ultimo[1], dados.meses_na_foto))
    ]

    agora, periodo, meses = _escolher_janela(limites, periodo, de, ate)
    antes = _recuar(agora, 1)
    dados.periodo = periodo
    dados.meses = meses
    dados.rotulo = ROTULO_DO_PERIODO.get(periodo, f"{meses} meses")
    dados.de = _valor_do_mes(*agora[0])
    dados.ate = _valor_do_mes(*agora[-1])
    dados.rotulo_de_agora = _rotulo(agora)
    dados.rotulo_de_antes = _rotulo(antes)
    if ultimo != (importacao.data_corte.year, importacao.data_corte.month):
        dados.mes_de_fora = f"{MESES[importacao.data_corte.month]} de {importacao.data_corte.year}"
    if _quantos_meses(primeiro, antes[0]) < 1:
        # O ano passado não cabe inteiro na foto. Dizer isso é melhor do que comparar com
        # meio ano passado, que é o mesmo erro de comparar meio mês com um mês inteiro.
        dados.falta_historico = (
            f"A foto do SET guarda {dados.meses_na_foto} meses fechados de venda mês a mês, e "
            f"comparar {_rotulo(agora)} com o mesmo período do ano passado pede "
            f"{_quantos_meses(antes[0], ultimo)}. Escolha um período mais curto, ou espere a "
            "próxima sincronização: a partir da versão 1.30.0 a foto guarda cinco anos."
        )

    soma_agora = _somar(importacao, agora)
    soma_antes = {} if dados.falta_historico else _somar(importacao, antes)
    dados.tem_historico = bool(soma_antes)
    if not soma_agora and not soma_antes:
        return dados

    cadastro = _produtos(importacao, grupo=grupo, fornecedor=fornecedor, busca=busca)
    dados.anos = _ano_a_ano(
        importacao, agora, primeiro, anos,
        _consulta_de_produtos(importacao, grupo=grupo, fornecedor=fornecedor, busca=busca))
    linhas = []
    for codigo in set(soma_agora) | set(soma_antes):
        produto = cadastro.get(codigo)
        if produto is None:
            continue
        unidades, receita = soma_agora.get(codigo, (ZERO, ZERO))
        unidades_antes, receita_antes = soma_antes.get(codigo, (ZERO, ZERO))
        linhas.append(LinhaComparada(
            codigo=codigo,
            descricao=produto["descricao"] or codigo,
            grupo=produto["grupo"],
            fornecedor=produto["fornecedor"],
            estoque=produto["estoque"] or ZERO,
            unidades=unidades, unidades_antes=unidades_antes,
            receita=receita, receita_antes=receita_antes,
        ))

    dados.produtos = len(linhas)
    dados.receita = sum((l.receita for l in linhas), ZERO)
    dados.receita_antes = sum((l.receita_antes for l in linhas), ZERO)
    dados.unidades = sum((l.unidades for l in linhas), ZERO)
    dados.unidades_antes = sum((l.unidades_antes for l in linhas), ZERO)
    dados.subiram = sum(1 for l in linhas if l.diferenca > ZERO and not l.novo)
    dados.cairam = sum(1 for l in linhas if l.diferenca < ZERO and not l.sumiu)
    dados.novos = sum(1 for l in linhas if l.novo)
    dados.sumiram = sum(1 for l in linhas if l.sumiu)

    por_diferenca = sorted(linhas, key=lambda l: (-l.diferenca, l.descricao))
    dados.cresceram = [l for l in por_diferenca if l.diferenca > ZERO][:QUANTOS_DESTAQUES]
    dados.encolheram = [l for l in reversed(por_diferenca) if l.diferenca < ZERO][:QUANTOS_DESTAQUES]

    # A tabela em ordem de faturamento do período: é por onde se começa a comprar.
    linhas.sort(key=lambda l: (-l.receita, -l.receita_antes, l.descricao))
    dados.encontrados = len(linhas)
    dados.linhas = linhas if quantos is None else linhas[:quantos]
    dados.mostrados = len(dados.linhas)

    # As listas dos filtros saem do catálogo INTEIRO, e não do que o filtro já deixou
    # passar: tiradas do filtrado, escolher um grupo apagaria todos os outros do seletor
    # e não haveria como trocar de grupo sem antes voltar para "Todos".
    catalogo = _consulta_de_produtos(importacao).order_by()
    dados.grupos = sorted(
        nome for nome in catalogo.values_list("grupo", flat=True).distinct() if nome)
    dados.fornecedores = sorted(
        nome for nome in catalogo.values_list("fornecedor", flat=True).distinct() if nome)
    return dados


def em_linhas(dados):
    """A comparação inteira em linhas, para o arquivo."""
    cabecalho = ("Código", "Produto", "Grupo", "Fornecedor",
                 f"Unidades ({dados.rotulo_de_agora})", f"Unidades ({dados.rotulo_de_antes})",
                 f"Faturou ({dados.rotulo_de_agora})", f"Faturou ({dados.rotulo_de_antes})",
                 "Diferença em R$", "Variação %", "Na prateleira hoje")
    linhas = [cabecalho]
    for linha in dados.linhas:
        linhas.append((
            linha.codigo, linha.descricao, linha.grupo, linha.fornecedor,
            linha.unidades, linha.unidades_antes, linha.receita, linha.receita_antes,
            linha.diferenca,
            "" if linha.variacao is None else linha.variacao,
            linha.estoque,
        ))
    return linhas
