"""Markup e margem de lucro: por produto e da loja inteira.

Pedido do Edson em 08/10/2026: "buscar no set se temos o valor de custo e a margem de
lucro dos produtos para calcular o Markup e a Margem de Lucro individuais por produto e
geral".

Temos. O cadastro do SET traz o custo (PRECOCUSTO, ou PRECOCOMPRA quando o primeiro está
zerado) e o preço de venda (PRECOVENDA) de cada produto, e o item de cada venda guarda o
custo que o produto tinha no dia (IVENDAS.PRECOCUSTO). Com isso dá para calcular as duas
coisas, e elas não são a mesma:

    markup = (venda / custo - 1) x 100     quanto se põe EM CIMA DO CUSTO
    margem = (venda - custo) / venda x 100 quanto sobra DO PREÇO DE VENDA

O mesmo preço dá markup de 119,9% e margem de 54,5%. Confundir um com o outro é o erro
mais caro do varejo: quem acha que tem 120% de margem se dá um desconto que come o lucro
inteiro. E o SET ajuda a confundir, porque o campo dele chamado "% de lucro" (PLUCRO) é
markup: confere com (precovenda / precocusto - 1) x 100 em 10.759 dos 10.764 produtos que
têm os três campos preenchidos na cópia de 20/09/2026. Por isso esta tela mostra os dois
números lado a lado, sempre com o nome certo.

Dois números de margem aparecem aqui, e a diferença entre eles é de propósito:

- A **realizada** sai das vendas de 12 meses, com o custo gravado no item no dia da venda.
  É o que a loja de fato ganhou. Em 1.608 dos 32.034 itens esse custo está vazio, então a
  conta é feita só sobre a receita dos itens que têm custo — o pedaço comparável.
- A **da tabela** usa custo e preço do cadastro de hoje, pesados pelo que cada produto
  vendeu em 12 meses. É o que a loja ganharia se vendesse o mesmo de novo, com os preços
  de agora. Quando ela é bem menor que a realizada, o preço de hoje está apertado.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Count, F, Q, Sum

from apps.compras.sugestoes import e_mercadoria
from apps.importacao.models import ProdutoImportado

ZERO = Decimal("0")
CEM = Decimal("100")
UM_DECIMO = Decimal("0.1")
CENTAVO = Decimal("0.01")

# Quanto o "% de lucro" do SET pode ficar longe do markup que o preço dá antes de a tela
# chamar aquilo de desatualizado. Meio ponto percentual é arredondamento; mais que isso é
# preço que mudou e o campo ficou para trás.
TOLERANCIA_MARKUP_SET = Decimal("0.5")

QUANTOS_NA_TELA = 200

ABAIXO_DO_CUSTO = "abaixo"
NO_CUSTO = "no_custo"
SEM_CUSTO = "sem_custo"
SEM_MARKUP_SET = "sem_markup"
MARKUP_SET_ERRADO = "markup_errado"

SITUACOES = [
    (ABAIXO_DO_CUSTO, "Preço abaixo do custo"),
    (NO_CUSTO, "Preço igual ao custo"),
    (SEM_CUSTO, "Sem custo no cadastro"),
    (SEM_MARKUP_SET, "Sem % de lucro no SET"),
    (MARKUP_SET_ERRADO, "% de lucro do SET desatualizado"),
]
ROTULO_SITUACAO = dict(SITUACOES)

ORDEM_PADRAO = "lucro"
ORDENS = [
    (ORDEM_PADRAO, "Maior lucro em 12 meses"),
    ("margem_menor", "Menor margem"),
    ("margem_maior", "Maior margem"),
    ("markup_menor", "Menor markup"),
    ("markup_maior", "Maior markup"),
    ("vendeu", "Mais vendidos"),
]
ROTULO_ORDEM = dict(ORDENS)


def markup(custo, venda):
    """Quanto por cento o preço está acima do custo. None quando não há com o que contar."""
    if custo is None or venda is None or custo <= ZERO or venda <= ZERO:
        return None
    return ((venda / custo - 1) * CEM).quantize(UM_DECIMO)


def margem(custo, venda):
    """Quanto por cento do preço de venda sobra depois do custo da mercadoria."""
    if custo is None or venda is None or venda <= ZERO:
        return None
    return ((venda - custo) / venda * CEM).quantize(UM_DECIMO)


def _porcento(parte, total):
    if not total:
        return None
    return (Decimal(parte) / Decimal(total) * CEM).quantize(UM_DECIMO)


def _dinheiro(valor):
    return (Decimal(valor or 0)).quantize(CENTAVO)


def _mediana(valores):
    ordenados = sorted(v for v in valores if v is not None)
    if not ordenados:
        return None
    meio = len(ordenados) // 2
    if len(ordenados) % 2:
        return ordenados[meio]
    return ((ordenados[meio - 1] + ordenados[meio]) / 2).quantize(UM_DECIMO)


@dataclass
class Linha:
    """Um produto com os dois números, e o que o SET diz sobre ele."""

    codigo: str
    descricao: str
    grupo: str
    fornecedor: str
    custo: Decimal | None
    venda: Decimal | None
    markup: Decimal | None
    margem: Decimal | None
    markup_set: Decimal | None
    markup_set_confere: bool | None
    mercadoria: bool
    estoque: Decimal
    vendas_12m: Decimal
    receita_12m: Decimal
    lucro_12m: Decimal | None
    margem_12m: Decimal | None
    situacao: str = ""

    @property
    def rotulo_situacao(self):
        return ROTULO_SITUACAO.get(self.situacao, "")

    @property
    def rotulo_selo(self):
        """Etiqueta na tabela só para o que pede ação; o resto viraria poluição.

        Faltar o "% de lucro" no SET não muda nada aqui, porque a conta é feita do
        custo e do preço: aparece na contagem de cima, não em 338 linhas marcadas.
        """
        if self.situacao in ("", SEM_MARKUP_SET):
            return ""
        return self.rotulo_situacao

    @property
    def dinheiro_parado_abaixo_do_custo(self):
        """Quanto a loja perde se vender, ao preço de hoje, o que tem na prateleira."""
        if self.situacao != ABAIXO_DO_CUSTO or self.estoque <= ZERO:
            return ZERO
        return ((self.custo - self.venda) * self.estoque).quantize(CENTAVO)


@dataclass
class Resumo:
    """Os números da loja inteira (ou do recorte filtrado)."""

    produtos: int = 0
    com_os_dois_precos: int = 0

    receita_12m: Decimal = ZERO
    receita_com_custo: Decimal = ZERO
    custo_vendido: Decimal = ZERO
    lucro: Decimal = ZERO
    margem_realizada: Decimal | None = None
    markup_realizado: Decimal | None = None
    cobertura_do_custo: Decimal | None = None

    margem_tabela: Decimal | None = None
    markup_tabela: Decimal | None = None
    margem_mediana: Decimal | None = None
    markup_mediano: Decimal | None = None

    abaixo_do_custo: int = 0
    no_custo: int = 0
    sem_custo: int = 0
    sem_markup_set: int = 0
    markup_set_errado: int = 0
    perda_abaixo_do_custo: Decimal = ZERO

    @property
    def vezes_o_custo(self):
        """O preço é quantas vezes o custo, no realizado. Fala mais do que o markup."""
        if not self.custo_vendido:
            return None
        return (self.receita_com_custo / self.custo_vendido).quantize(UM_DECIMO)

    @property
    def tem_alerta(self):
        return bool(self.abaixo_do_custo or self.no_custo or self.sem_custo
                    or self.sem_markup_set or self.markup_set_errado)


@dataclass
class Grupo:
    nome: str
    produtos: int
    receita_12m: Decimal
    lucro_12m: Decimal
    margem_12m: Decimal | None
    markup_12m: Decimal | None
    margem_tabela: Decimal | None


@dataclass
class Tela:
    tem_dados: bool = False
    data_corte: object = None
    resumo: Resumo = field(default_factory=Resumo)
    grupos: list = field(default_factory=list)
    produtos: list = field(default_factory=list)
    quantos: int = 0
    mostrando: int = 0
    grupos_para_filtro: list = field(default_factory=list)
    fornecedores_para_filtro: list = field(default_factory=list)
    filtro_grupo: str = ""
    filtro_fornecedor: str = ""
    filtro_situacao: str = ""
    busca: str = ""
    ordem: str = ORDEM_PADRAO

    @property
    def filtrou(self):
        return bool(self.filtro_grupo or self.filtro_fornecedor or self.filtro_situacao
                    or self.busca)

    @property
    def rotulo_ordem(self):
        return ROTULO_ORDEM.get(self.ordem, "")

    @property
    def tem_mais(self):
        return self.quantos > self.mostrando


def _situacao(custo, venda, markup_calculado, markup_set, mercadoria=True):
    """Em que caixa o produto cai, da mais grave para a menos grave.

    O que não é mercadoria de revenda (DIVERSOS, CONSUMO PROPRIO) não recebe situação
    nenhuma: DIVERSOS é o código em que o balcão lança a venda miúda, com preço de R$ 1,00
    e custo de cadastro que não quer dizer nada. Marcá-lo como "preço abaixo do custo"
    mandaria a gerência arrumar um preço que não existe. O faturamento e o lucro dele
    continuam na conta da loja, porque o dinheiro entrou.
    """
    if not mercadoria:
        return ""
    if venda is not None and venda > ZERO:
        if custo is None or custo <= ZERO:
            return SEM_CUSTO
        if venda < custo:
            return ABAIXO_DO_CUSTO
        if venda == custo:
            return NO_CUSTO
    if markup_calculado is not None:
        if markup_set is None:
            return SEM_MARKUP_SET
        if abs(markup_set - markup_calculado) > TOLERANCIA_MARKUP_SET:
            return MARKUP_SET_ERRADO
    return ""


def _linha(dados):
    # O que não é mercadoria de revenda (DIVERSOS, CONSUMO PROPRIO) não tem markup nem
    # margem: DIVERSOS é o código em que o balcão lança a venda miúda, a R$ 1,00, e o
    # custo que está no cadastro dele não quer dizer nada. Mostrar -1.150% de margem ali
    # seria dar um número errado com ar de certo. O dinheiro que ele trouxe continua na
    # conta da loja, porque entrou de verdade.
    mercadoria = e_mercadoria(dados["grupo"], dados["descricao"])
    custo = dados["custo"]
    venda = dados["preco_venda"]
    mk = markup(custo, venda) if mercadoria else None
    mg = margem(custo, venda) if mercadoria else None
    markup_set = dados["markup_set"]
    confere = None
    if mk is not None and markup_set is not None:
        confere = abs(markup_set - mk) <= TOLERANCIA_MARKUP_SET
    receita_com_custo = _dinheiro(dados["receita_com_custo_12m"])
    custo_vendido = _dinheiro(dados["custo_vendido_12m"])
    lucro = margem_realizada = None
    if receita_com_custo > ZERO:
        lucro = (receita_com_custo - custo_vendido).quantize(CENTAVO)
        margem_realizada = _porcento(lucro, receita_com_custo)
    return Linha(
        codigo=dados["codigo"],
        descricao=dados["descricao"],
        grupo=dados["grupo"],
        fornecedor=dados["fornecedor"],
        custo=custo,
        venda=venda,
        markup=mk,
        margem=mg,
        markup_set=markup_set,
        markup_set_confere=confere,
        mercadoria=mercadoria,
        estoque=dados["estoque"] or ZERO,
        vendas_12m=dados["vendas_12m"] or ZERO,
        receita_12m=_dinheiro(dados["receita_12m"]),
        lucro_12m=lucro,
        margem_12m=margem_realizada,
        situacao=_situacao(custo, venda, mk, markup_set, mercadoria=mercadoria),
    )


_CAMPOS = ("codigo", "descricao", "grupo", "fornecedor", "custo", "preco_venda",
           "markup_set", "estoque", "vendas_12m", "receita_12m",
           "custo_vendido_12m", "receita_com_custo_12m")


def _ordenar(linhas, ordem):
    """Ordena na mão porque markup e margem não são colunas do banco: são conta.

    Produto sem o número da ordem escolhida vai para o fim da lista, em vez de
    aparecer como se fosse o pior (ou o melhor) de todos.
    """
    def com_falta_no_fim(valor, invertido):
        existe = valor is not None
        if not existe:
            return (1, ZERO)
        return (0, -valor if invertido else valor)

    regras = {
        "lucro": lambda l: com_falta_no_fim(l.lucro_12m, True),
        "margem_menor": lambda l: com_falta_no_fim(l.margem, False),
        "margem_maior": lambda l: com_falta_no_fim(l.margem, True),
        "markup_menor": lambda l: com_falta_no_fim(l.markup, False),
        "markup_maior": lambda l: com_falta_no_fim(l.markup, True),
        "vendeu": lambda l: com_falta_no_fim(l.vendas_12m, True),
    }
    chave = regras.get(ordem, regras[ORDEM_PADRAO])
    return sorted(linhas, key=lambda l: (chave(l), l.codigo))


def _resumo(linhas):
    resumo = Resumo(produtos=len(linhas))
    receita_tabela = custo_tabela = ZERO
    markups = []
    margens = []
    for linha in linhas:
        # Receita, custo e lucro realizados não são somados aqui: vêm do banco, no
        # _realizado. Aqui ficam só as contas que dependem de produto a produto.
        if linha.markup is not None:
            resumo.com_os_dois_precos += 1
            markups.append(linha.markup)
            margens.append(linha.margem)
            if linha.vendas_12m > ZERO:
                receita_tabela += linha.vendas_12m * linha.venda
                custo_tabela += linha.vendas_12m * linha.custo
        if linha.situacao == ABAIXO_DO_CUSTO:
            resumo.abaixo_do_custo += 1
            resumo.perda_abaixo_do_custo += linha.dinheiro_parado_abaixo_do_custo
        elif linha.situacao == NO_CUSTO:
            resumo.no_custo += 1
        elif linha.situacao == SEM_CUSTO:
            resumo.sem_custo += 1
        elif linha.situacao == SEM_MARKUP_SET:
            resumo.sem_markup_set += 1
        elif linha.situacao == MARKUP_SET_ERRADO:
            resumo.markup_set_errado += 1

    if receita_tabela:
        resumo.margem_tabela = _porcento(receita_tabela - custo_tabela, receita_tabela)
        resumo.markup_tabela = _porcento(receita_tabela - custo_tabela, custo_tabela)
    resumo.markup_mediano = _mediana(markups)
    resumo.margem_mediana = _mediana(margens)
    return resumo


def _realizado(consulta, resumo):
    """A margem que a loja realizou, somada no banco: é dinheiro, não média de médias."""
    totais = consulta.aggregate(
        faturamento=Sum("receita_12m"),
        faturamento_com_custo=Sum("receita_com_custo_12m"),
        custo_do_vendido=Sum("custo_vendido_12m"),
    )
    resumo.receita_12m = _dinheiro(totais["faturamento"])
    resumo.receita_com_custo = _dinheiro(totais["faturamento_com_custo"])
    resumo.custo_vendido = _dinheiro(totais["custo_do_vendido"])
    resumo.lucro = (resumo.receita_com_custo - resumo.custo_vendido).quantize(CENTAVO)
    resumo.margem_realizada = _porcento(resumo.lucro, resumo.receita_com_custo)
    resumo.markup_realizado = _porcento(resumo.lucro, resumo.custo_vendido)
    resumo.cobertura_do_custo = _porcento(resumo.receita_com_custo, resumo.receita_12m)
    return resumo


def _grupos(consulta):
    """Markup e margem por grupo: é por aí que se decide onde mexer no preço."""
    linhas = []
    # Os nomes das somas não repetem nome de campo de propósito: um apelido chamado
    # "custo" faria o F("custo") de baixo apontar para a própria soma, e o Django
    # recusaria a conta ("is an aggregate").
    for dados in (consulta.values("grupo")
                  .annotate(produtos=Count("id"),
                            faturamento=Sum("receita_12m"),
                            faturamento_com_custo=Sum("receita_com_custo_12m"),
                            custo_do_vendido=Sum("custo_vendido_12m"),
                            receita_tabela=Sum(F("vendas_12m") * F("preco_venda")),
                            custo_tabela=Sum(F("vendas_12m") * F("custo")))
                  .order_by()):
        receita_com_custo = _dinheiro(dados["faturamento_com_custo"])
        custo = _dinheiro(dados["custo_do_vendido"])
        lucro = (receita_com_custo - custo).quantize(CENTAVO)
        receita_tabela = _dinheiro(dados["receita_tabela"])
        custo_tabela = _dinheiro(dados["custo_tabela"])
        linhas.append(Grupo(
            nome=dados["grupo"] or "SEM GRUPO",
            produtos=dados["produtos"],
            receita_12m=_dinheiro(dados["faturamento"]),
            lucro_12m=lucro,
            margem_12m=_porcento(lucro, receita_com_custo),
            markup_12m=_porcento(lucro, custo),
            margem_tabela=(_porcento(receita_tabela - custo_tabela, receita_tabela)
                           if receita_tabela else None),
        ))
    return sorted(linhas, key=lambda g: (-g.lucro_12m, g.nome))


def montar(importacao, grupo="", fornecedor="", situacao="", busca="",
           ordem=ORDEM_PADRAO, quantos=QUANTOS_NA_TELA):
    """Monta a tela: resumo da loja, tabela por grupo e os produtos do recorte."""
    tela = Tela(filtro_grupo=grupo, filtro_fornecedor=fornecedor,
                filtro_situacao=situacao, busca=busca,
                ordem=ordem if ordem in ROTULO_ORDEM else ORDEM_PADRAO)
    if importacao is None:
        return tela
    tela.tem_dados = True
    tela.data_corte = importacao.data_corte

    todos = ProdutoImportado.objects.filter(importacao=importacao)
    # Meta.ordering entra no DISTINCT e o deixa sem efeito: order_by() vazio primeiro.
    tela.grupos_para_filtro = sorted(
        v for v in todos.order_by().values_list("grupo", flat=True).distinct() if v)
    tela.fornecedores_para_filtro = sorted(
        v for v in todos.order_by().values_list("fornecedor", flat=True).distinct() if v)

    consulta = todos
    if grupo:
        consulta = consulta.filter(grupo=grupo)
    if fornecedor:
        consulta = consulta.filter(fornecedor=fornecedor)
    if busca:
        consulta = consulta.filter(Q(descricao__icontains=busca) | Q(codigo__icontains=busca)
                                   | Q(codigo_barras=busca))

    linhas = [_linha(dados) for dados in consulta.values(*_CAMPOS)]
    tela.resumo = _realizado(consulta, _resumo(linhas))
    tela.grupos = _grupos(consulta)

    if situacao:
        linhas = [linha for linha in linhas if linha.situacao == situacao]
    linhas = _ordenar(linhas, tela.ordem)
    tela.quantos = len(linhas)
    if quantos:
        linhas = linhas[:quantos]
    tela.mostrando = len(linhas)
    tela.produtos = linhas
    return tela


def _numero(valor, casas=2):
    """Número com vírgula, que é como o Excel em português espera ler."""
    if valor is None:
        return ""
    return f"{Decimal(valor):.{casas}f}".replace(".", ",")


def em_linhas(tela):
    """A tabela inteira em linhas, para o arquivo que se abre no Excel."""
    cabecalho = ("Código", "Produto", "Grupo", "Fornecedor", "Custo", "Preço de venda",
                 "Markup %", "Margem %", "% de lucro no SET", "O SET confere",
                 "Tem na loja", "Vendeu em 12 meses", "Faturou em 12 meses",
                 "Lucro em 12 meses", "Margem realizada %", "Situação")
    linhas = [cabecalho]
    for item in tela.produtos:
        confere = "" if item.markup_set_confere is None else (
            "sim" if item.markup_set_confere else "não")
        linhas.append((
            item.codigo, item.descricao, item.grupo, item.fornecedor,
            _numero(item.custo, 4), _numero(item.venda, 4),
            _numero(item.markup, 1), _numero(item.margem, 1),
            _numero(item.markup_set, 1), confere,
            _numero(item.estoque, 3), _numero(item.vendas_12m, 3),
            _numero(item.receita_12m), _numero(item.lucro_12m),
            _numero(item.margem_12m, 1), item.rotulo_situacao,
        ))
    return linhas
