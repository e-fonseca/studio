"""A lista de compra: o que comprar, quanto e de quem, antes de faltar.

O pedido do Edson (07/10/2026) foi direto: "não deixar o produto acabar para
comprar; o sistema precisa fazer esse gerenciamento". A tela de Sugestões já
dizia o que repor, mas só depois de zerar — ou seja, depois de a loja já ter
perdido venda. Aqui a conta é feita antes.

A regra, em uma linha: quando o que a loja tem mais o que está a caminho cai
abaixo do ponto de pedido, é hora de comprar, e a quantidade é a que recompõe a
cobertura até a próxima compra.

O ponto de pedido sai de `apps/compras/calculos.py`, que é o mesmo cálculo da
tela "Antes de comprar" — não existem duas contas de reposição no sistema. O que
este arquivo faz é rodá-lo sobre a loja inteira, acrescentar três coisas que só
fazem sentido na lista, e agrupar por fornecedor, porque compra se faz por
fornecedor e não por produto:

1. **O mínimo cadastrado no SET entra na conta.** A loja preencheu QTDEMIN em
   2.747 produtos e isso é a opinião de quem vende: o ponto de pedido nunca fica
   abaixo dele.
2. **Prazo de entrega com reserva.** O SET grava a data da nota e não o prazo do
   fornecedor, então o prazo medido quase sempre dá zero. Vale o prazo que a
   gerência informou na ficha; sem ele, o sistema assume um prazo padrão e diz
   na tela que assumiu.
3. **Mercadoria a caminho é descontada.** Compra "Pendente" no SET já vem a
   caminho; sem descontar, a lista mandaria comprar de novo o que já foi pedido.

O que a lista NÃO faz: ela não compra, não manda e-mail e não fala com o SET.
Ela é um papel para levar ao fornecedor, e a última palavra é de quem compra.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from apps.compras import calculos, estacao, janela as janelas, movimento
from apps.compras import politica as politica_de_compra
from apps.compras.models import PoliticaDeCompra
from apps.compras.sugestoes import so_mercadoria
from apps.core.templatetags.cabana import quantidade as escrever
from apps.fornecedores import servicos as fornecedores

ZERO = Decimal("0")
UM = Decimal("1")

# Prazo assumido quando ninguém informou e o medido saiu zero. Duas semanas é o que
# a loja leva, na média, entre pedir e receber do fornecedor de fora do estado. É
# chute honesto: a tela marca a linha como "prazo assumido" e manda informar o certo.
PRAZO_PADRAO_DIAS = 15

# Teto de linhas por fornecedor na tela: as que mais pesam. Quarenta linhas vezes cinco
# fornecedores davam uma página que ninguém rola até o fim. A lista inteira sai no arquivo.
POR_FORNECEDOR = 15
# Quantos fornecedores entram no "comece por aqui". Mais do que isso ninguém resolve
# numa semana, e a lista deixa de ser uma decisão para virar um relatório.
QUANTOS_PRIMEIRO = 5

# O SET nem sempre tem fornecedor no produto (é o fornecedor da última compra, e produto
# que nunca foi comprado pelo SET fica sem). Esses não entram no "comece por aqui", porque
# não dá para ligar para um fornecedor que não existe: eles viram uma tarefa à parte, a de
# completar o cadastro.
SEM_FORNECEDOR = "Sem fornecedor no SET"


class Urgencia:
    """Por que este produto está na lista. A ordem aqui é a ordem na tela."""

    FALTANDO = "faltando"
    ABAIXO_DO_MINIMO = "abaixo_do_minimo"
    VAI_FALTAR = "vai_faltar"


ROTULO = {
    Urgencia.FALTANDO: "Está faltando",
    Urgencia.ABAIXO_DO_MINIMO: "Abaixo do mínimo",
    Urgencia.VAI_FALTAR: "Vai faltar",
}
EXPLICACAO = {
    Urgencia.FALTANDO: "Zerado na prateleira e continua vendendo: é venda perdida todo dia.",
    Urgencia.ABAIXO_DO_MINIMO: "Abaixo do mínimo que a loja cadastrou no SET para este produto.",
    Urgencia.VAI_FALTAR: "O que tem acaba antes de o fornecedor entregar o próximo pedido.",
}
PESO = {Urgencia.FALTANDO: 0, Urgencia.ABAIXO_DO_MINIMO: 1, Urgencia.VAI_FALTAR: 2}


@dataclass
class ItemDaLista:
    codigo: str
    descricao: str
    grupo: str
    fornecedor: str
    urgencia: str
    estoque: Decimal
    a_caminho: Decimal
    # Vai no pedido guardado (apps/pedidos) e é a ponte mais confiável para casar a
    # linha da nota fiscal com a linha do pedido: o código do produto na nota é o do
    # FORNECEDOR, o de barras é o mesmo nos dois lados do balcão.
    codigo_barras: str = ""
    minimo_set: Decimal = None
    ponto_de_pedido: Decimal = ZERO
    comprar: Decimal = ZERO
    custo: Decimal = None
    valor: Decimal = ZERO
    vendas_12m: Decimal = ZERO
    # Pedido dele em 20/10/2026, seção 6 do prompt: "Vendas em 90 dias | Avaliação do
    # giro". O número já vinha importado do SET (`ProdutoImportado.vendas_90d`) e não
    # chegava a esta tela. Fica ao lado do de doze meses porque é a comparação que diz
    # se o produto está acelerando ou parando, e nenhum dos dois diz isso sozinho.
    vendas_90d: Decimal = ZERO
    receita_12m: Decimal = ZERO
    dias_de_cobertura: str = ""
    prazo_dias: int = None
    prazo_assumido: bool = False
    motivo: str = ""
    # O mesmo período do ano passado (apps/compras/estacao.py): quantas vezes a média
    # ele vendeu, e qual seria a quantidade sem esse ajuste. A tela mostra os dois,
    # porque número que mudou sozinho sem explicação ninguém segue.
    fator_de_estacao: Decimal = UM
    comprar_sem_estacao: Decimal = ZERO
    # De onde entrou e para onde foi o estoque (apps/compras/movimento.py): é a conta
    # que o Edson pediu em 14/10/2026 para a sugestão parar de ser um número solto.
    movimento: object = None
    # A janela de venda que virou esta sugestão, e se ela caiu de volta para os doze
    # meses por falta de venda no período escolhido (apps/compras/janela.py).
    janela_rotulo: str = ""
    janela_voltou_para_12m: bool = False
    # Quanto de saldo negativo a conta desprezou nesta linha (apps/compras/calculos.py).
    # Sem isto na tela, TEM -69 e COMPRAR 1 na mesma linha não fecham.
    saldo_desprezado: Decimal = ZERO
    # Quanto o produto vende por dia na janela escolhida. Fica na linha para a tela poder
    # dizer quanto tempo a quantidade DURA, que é a pergunta que julga o número.
    demanda_diaria: Decimal = ZERO
    # Os três números que a conta usa e que não apareciam em lugar nenhum da tela. Ele
    # pediu em 20/10/2026 (seção 4) para "diferenciar claramente" estoque de segurança,
    # ponto de reposição, estoque disponível, estoque-alvo e quantidade sugerida: o
    # sistema calculava os cinco e mostrava dois. A coluna "Mínimo" é o mínimo do SET,
    # que é outra coisa — é opinião de quem vende, não conta de reposição.
    posicao_estoque: Decimal = ZERO
    estoque_alvo: Decimal = None
    estoque_seguranca: Decimal = ZERO
    # A parcela que a gerência acrescentou à conta, quando acrescentou. `comprar`
    # continua sendo a sugestão do sistema: ela não se apaga, porque é ela que explica
    # o número, e agora é também a primeira das duas parcelas da soma que ele pediu em
    # 20/10/2026 ("com a soma dois campos gera a quantidade total").
    a_mais: Decimal = None
    nao_comprar: bool = False
    ajustada_em: object = None
    ajustada_por: str = ""
    ajuste_observacao: str = ""
    # A sugestão guardada no momento do ajuste. Com a soma, o total acompanha a conta
    # nova sozinho; este número serve para a tela dizer de quanto para quanto a
    # sugestão andou desde então.
    sugerida_no_ajuste: Decimal = None
    ajuste_desatualizado: bool = False
    # O carro-chefe da loja e o alerta de 30% (apps/compras/politica.py), pedido dele em
    # 22/10/2026. A porcentagem é do estoque IDEAL (o estoque-alvo da conta), contando o
    # que está a caminho; None quando o produto não tem ideal porque não vende.
    carro_chefe: bool = False
    porcentagem_do_ideal: int = None
    em_alerta: bool = False

    @property
    def conta_da_reposicao(self):
        """A conta da compra escrita por extenso, com os cinco números separados.

        Pedido dele em 20/10/2026, seção 4. A frase existe para quem desconfia do número
        poder refazer a conta na calculadora sem abrir a documentação: é a mesma régua do
        resto do sistema, em que cada quantidade explica a si mesma.
        """
        if self.estoque_alvo is None or self.demanda_diaria <= ZERO:
            return ""
        if self.estoque_alvo < UM:
            # Produto que vende 2 por ano tem estoque-alvo de 0,16, e a tela escrevia
            # "estoque de segurança 0,0392": número que não explica nada e faz a linha
            # parecer defeito. Aqui quem decide a quantidade é o arredondamento para a
            # unidade inteira, não a fórmula — então a linha CALA em vez de escrever uma
            # frase que não muda o que a pessoa vai fazer. É a regra do "menos é mais".
            return ""
        return (
            f"estoque de segurança {_duas_casas(self.estoque_seguranca)}"
            f" · ponto de reposição {_duas_casas(self.ponto_de_pedido)}"
            f" · disponível com o que está a caminho {_duas_casas(self.posicao_estoque)}"
            f" · estoque-alvo {_duas_casas(self.estoque_alvo)}"
        )

    @property
    def giro_dos_90_dias(self):
        """A venda de 90 dias ao lado do ritmo dos doze meses, numa frase.

        O número cru não decide nada: 9 unidades em 90 dias é muito para um produto que
        vendeu 12 no ano e pouco para um que vendeu 200. Então a frase compara os dois
        ritmos, e só fala de aceleração quando a diferença passa de um quinto — abaixo
        disso é ruído de calendário, como no fator do ano passado.
        """
        if self.vendas_90d <= ZERO:
            if self.vendas_12m > ZERO:
                return "nada nos últimos 90 dias"
            return ""
        esperado = self.vendas_12m / Decimal("4")
        if esperado <= ZERO:
            return f"{escrever(self.vendas_90d)} em 90 dias"
        proporcao = self.vendas_90d / esperado
        if proporcao >= Decimal("1.2"):
            return (f"{escrever(self.vendas_90d)} em 90 dias, acima do ritmo do ano "
                    f"({escrever(esperado)} seria o normal)")
        if proporcao <= Decimal("0.8"):
            return (f"{escrever(self.vendas_90d)} em 90 dias, abaixo do ritmo do ano "
                    f"({escrever(esperado)} seria o normal)")
        return f"{escrever(self.vendas_90d)} em 90 dias, no ritmo do ano"

    @property
    def rotulo(self):
        return ROTULO[self.urgencia]

    @property
    def estacao_mexeu(self):
        """O ano passado mudou a quantidade? Só então a tela tem o que explicar."""
        return self.fator_de_estacao != UM and self.comprar != self.comprar_sem_estacao

    @property
    def estacao_vezes(self):
        return self.fator_de_estacao.quantize(Decimal("0.1"))

    @property
    def foi_ajustada(self):
        """Alguém mexeu nesta linha à mão? Parcela zero não conta: ela não muda nada."""
        return self.nao_comprar or bool(self.a_mais)

    @property
    def ajustada(self):
        """O total escolhido à mão, para quem só quer saber se o número é o do sistema.

        Volta None quando a linha segue a conta — é a mesma leitura de antes da soma,
        e é o que a tela e o CSV usam para dizer "mudado por".
        """
        return self.quantidade if self.foi_ajustada else None

    @property
    def quantidade(self):
        """O que vai no pedido: a sugestão do sistema MAIS a parcela da mão.

        Pedido dele em 20/10/2026. A soma, e não o total guardado, porque o que a
        pessoa quis dizer com "+5" foi cinco a mais do que o sistema achar certo —
        inclusive depois da sincronização, quando a conta já mudou.
        """
        if self.nao_comprar:
            return ZERO
        soma = (self.comprar or ZERO) + (self.a_mais or ZERO)
        return soma if soma > ZERO else ZERO

    @property
    def dias_que_a_quantidade_cobre(self):
        """Quantos dias de venda a quantidade do pedido cobre, na média da janela."""
        if not self.demanda_diaria or self.demanda_diaria <= ZERO:
            return None
        return int((self.quantidade or ZERO) / self.demanda_diaria)

    @property
    def quanto_tempo_a_quantidade_dura(self):
        """O mesmo em palavras, na unidade que a pessoa usa para pensar (ver `duracao`)."""
        return duracao(self.dias_que_a_quantidade_cobre)

    @property
    def quantidade_cobre_mais_de_um_ano(self):
        """Um ano de venda numa compra só. É o limite a partir do qual a frase muda de cor.

        Um ano não é regra contábil, é o calendário da loja: acima disso a mercadoria
        atravessa a estação inteira e volta, e é dela que sai o estoque que não vende
        nenhuma unidade no ano. A tela avisa; travar quem é que decide, não.
        """
        dias = self.dias_que_a_quantidade_cobre
        return dias is not None and dias > 365

    @property
    def valor_do_pedido(self):
        """Quanto custa a quantidade que vai no pedido, e não a sugerida.

        Arredonda ao centavo como `calculos.reais`, senão o total do pedido não bate
        com a soma das linhas impressas e quem confere acha que o sistema errou.
        """
        if self.custo is None:
            return ZERO
        return ((self.quantidade or ZERO) * self.custo).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass
class ListaDoFornecedor:
    nome: str
    itens: list = field(default_factory=list)
    valor: Decimal = ZERO
    prazo_dias: int = None
    prazo_assumido: bool = False
    # Quanto a loja vendeu em 12 meses do que hoje está faltando ou abaixo do mínimo
    # neste fornecedor: é o tamanho do buraco que ele tapa.
    receita_parada: Decimal = ZERO
    # O contrapeso: do que este mesmo fornecedor já entregou, quanto está parado na
    # prateleira sem vender nenhuma unidade no ano. Sem isso a lista mandaria comprar
    # mais de quem a loja já comprou errado.
    parado_na_prateleira: Decimal = ZERO
    itens_parados: int = 0
    # Quantas linhas deste fornecedor têm quantidade escolhida à mão.
    ajustados: int = 0

    @property
    def quantos(self):
        return len(self.itens)

    @property
    def faltando(self):
        return sum(1 for item in self.itens if item.urgencia == Urgencia.FALTANDO)

    @property
    def mostrados(self):
        return self.itens[:POR_FORNECEDOR]

    @property
    def escondidos(self):
        return max(self.quantos - POR_FORNECEDOR, 0)


@dataclass
class ListaDeCompra:
    importacao: object = None
    data_corte: object = None
    fornecedores: list = field(default_factory=list)
    valor: Decimal = ZERO
    quantos: int = 0
    faltando: int = 0
    abaixo_do_minimo: int = 0
    vai_faltar: int = 0
    sem_prazo_informado: int = 0
    sem_fornecedor: int = 0
    # Quantas linhas da lista inteira têm quantidade escolhida à mão.
    ajustados: int = 0
    com_minimo_no_set: int = 0
    produtos_com_minimo: int = 0
    # Quantas linhas têm saldo abaixo de zero no SET, que a compra conta como zero.
    com_saldo_negativo: int = 0
    # Quantas linhas não venderam nada na janela escolhida e caíram para os doze meses.
    # Na tela é o que diz se o filtro de período mexeu em algo ou foi escolha inócua.
    voltaram_para_12m: int = 0
    filtro_fornecedor: str = ""
    filtro_urgencia: str = ""
    filtro_media: str = ""
    # O pedaço de calendário de onde saiu a média de venda desta lista
    # (apps/compras/janela.py). A tela diz qual é, porque é ele que decide a quantidade.
    janela: object = None
    nomes_de_fornecedor: list = field(default_factory=list)
    # O começo da lista, o que cabe no teto do mês. É por aqui que se compra.
    primeiro: list = field(default_factory=list)
    valor_primeiro: Decimal = ZERO
    cabe_no_mes: Decimal = ZERO
    estourou_o_mes: bool = False
    resto: int = 0
    valor_resto: Decimal = ZERO
    # Os fornecedores que não entraram no começo da lista. Na tela eles aparecem só como
    # uma linha cada: cento e cinco tabelas abertas dariam uma página de oitenta mil
    # pixels, que ninguém lê. O detalhe deles está no arquivo e no filtro por fornecedor.
    outros: list = field(default_factory=list)
    # A política em vigor (models.PoliticaDeCompra) e o que ela acende: os carros-chefe
    # que já caíram ao alerta, do que tem menos para o que tem mais, e quantos produtos
    # da lista inteira estão em alerta.
    alerta_percentual: int = 30
    quantos_carros_chefe: int = 100
    carros_chefe_em_alerta: list = field(default_factory=list)
    em_alerta: int = 0

    @property
    def tem_itens(self):
        return self.quantos > 0


def duracao(dias):
    """Quantos dias de venda, na unidade que a pessoa usa para pensar.

    Dias até três meses, depois meses, depois anos: "cobre 1.825 dias" não assusta
    ninguém, e "cobre 5 anos" assusta — e é para assustar, porque é o erro que a loja
    comete. Quem lê isto é quem está decidindo a quantidade, e esta é a frase que julga o
    número que ele acabou de digitar. A compra guiada usa a mesma frase em cada opção.
    """
    if dias is None:
        return ""
    if dias < 90:
        return f"{dias} dia{'s' if dias != 1 else ''}"
    if dias < 730:
        meses = round(dias / 30)
        return f"{meses} {'meses' if meses != 1 else 'mês'}"
    anos = dias / 365
    return f"{anos:.1f}".replace(".", ",").removesuffix(",0") + " anos"


def _duas_casas(valor):
    """Quantidade com no máximo duas casas, para a conta escrita na linha.

    A conta interna trabalha com quatro casas; jogar 0,0392 na tela não explica nada e
    faz o número parecer defeito. Duas casas é o que a loja consegue conferir.
    """
    return escrever((valor or ZERO).quantize(Decimal("0.01")))


def _prazo(nome, produto, informados):
    """O prazo que vale para este produto, e se ele foi assumido pelo sistema."""
    informado = informados.get((nome or "").strip())
    if informado is not None:
        return informado, False
    medido = produto.prazo_reposicao_dias
    if medido:
        return medido, False
    return PRAZO_PADRAO_DIAS, True


def _urgencia(produto):
    """A tarja da linha, que é sempre sobre o ANO, não sobre a janela do filtro.

    Recebia o `resultado` do cálculo e não olhava para ele. Fica sem ele de propósito: a
    tarja responde "este produto está faltando na prateleira?", e isso se decide por
    estoque zerado mais venda no ano — a mesma régua, qualquer que seja a janela escolhida
    no filtro. Quem muda com a janela é a QUANTIDADE, e ela já se explica na própria
    linha. Trocar a tarja junto faria a mesma prateleira vazia aparecer e desaparecer de
    "Está faltando" conforme o filtro, e é essa tarja que vira a tarefa urgente da
    abertura ("Fechar o pedido do que está faltando").
    """
    minimo = produto.estoque_minimo_set
    if (produto.estoque or ZERO) <= 0 and (produto.vendas_12m or ZERO) > 0:
        return Urgencia.FALTANDO
    if minimo is not None and minimo > 0 and (produto.estoque or ZERO) < minimo:
        return Urgencia.ABAIXO_DO_MINIMO
    return Urgencia.VAI_FALTAR


def _candidatos(importacao):
    """Quem pode entrar na lista, filtrado no banco antes de contar produto a produto.

    São onze mil produtos; rodar a conta em todos custaria caro e não mudaria nada,
    porque produto que nunca vendeu e não tem mínimo cadastrado nunca vira compra
    por esta regra — ele é assunto da tela de Sugestões, não da lista de compra.
    """
    from django.db.models import Q

    return so_mercadoria(
        importacao.itens.filter(Q(vendas_12m__gt=0) | Q(estoque_minimo_set__gt=0))
    )


def montar(importacao, fornecedor="", urgencia="", media="", hoje=None, *, parametros=None,
           so_do_fornecedor="", prazos=None) -> ListaDeCompra:
    """A lista da loja inteira, com os filtros da tela aplicados depois da conta.

    Os três parâmetros nomeados são da compra guiada (apps/compras/guiada.py), e os três
    têm padrão que não muda nada para a lista de compra:

    - `parametros`: a política da conta (`calculos.Parametros`). A guiada troca o
      horizonte até a próxima compra pelo que a pessoa respondeu.
    - `so_do_fornecedor`: conta só os produtos deste fornecedor. A guiada é sempre de um
      fornecedor, e refazer a conta da loja inteira a cada pergunta custaria segundos.
    - `prazos`: prazos respondidos na guiada que ainda não estão na ficha (quem respondeu
      não pode mudar a ficha). Valem por cima dos informados, só nesta conta.
    """
    lista = ListaDeCompra()
    if importacao is None:
        return lista
    lista.importacao = importacao
    lista.data_corte = importacao.data_corte
    lista.filtro_media = janelas.valida(media)
    lista.produtos_com_minimo = importacao.itens.filter(estoque_minimo_set__gt=0).count()

    politica = PoliticaDeCompra.atual()
    lista.alerta_percentual = politica.alerta_percentual
    lista.quantos_carros_chefe = politica.carros_chefe
    carros = set(politica_de_compra.carros_chefe(importacao, politica.carros_chefe))

    informados = fornecedores.prazos_informados()
    if prazos:
        informados = {**informados, **prazos}
    parametros = parametros or calculos.Parametros()
    dias = importacao.dias_abertos_12m or 1
    por_fornecedor = {}
    nomes = set()
    candidatos = []
    # O que o ano passado diz sobre os dias que estes pedidos vão cobrir. Uma consulta
    # para a lista inteira, antes do laço: ver apps/compras/estacao.py.
    dia_do_pedido = hoje or date.today()
    # A mesma consulta para os quatro usos abaixo, montada UMA vez: ela era remontada a
    # cada chamada, com a cadeia de exclusões do `so_mercadoria` toda de novo.
    quem_entra = _candidatos(importacao)
    if so_do_fornecedor:
        quem_entra = quem_entra.filter(fornecedor=so_do_fornecedor)
    # A janela mais longa que o ano passado lê: 120 dias, mais o que a compra guiada
    # antecipa quando a próxima compra está longe. Sem a soma, o ano passado calava
    # justamente no pedido de três meses, que é o que mais atravessa estação.
    ano_passado = estacao.montar(importacao, quem_entra, hoje=dia_do_pedido,
                                 dias_maximos=estacao.DIAS_MAXIMOS + parametros.antecipar_dias)
    # De onde entrou e para onde foi o estoque de cada produto, e de que pedaço de
    # calendário sai a média de venda. Duas consultas cada, antes do laço, pelo mesmo
    # motivo da estação: onze mil produtos vezes uma consulta cada é a tela que não abre.
    movimentos = movimento.montar(importacao, quem_entra)
    janela = janelas.montar(importacao, quem_entra, media)
    lista.janela = janela

    for produto in quem_entra.iterator(chunk_size=2000):
        nome = (produto.fornecedor or "").strip() or SEM_FORNECEDOR
        prazo_dias, assumido = _prazo(produto.fornecedor, produto, informados)
        # A janela deste pedido: o prazo do fornecedor mais a próxima chance de comprar
        # e os dias de segurança. É esse pedaço de calendário que o ano passado explica.
        dias_da_janela = (prazo_dias or 0) + parametros.horizonte_revisao_dias + int(parametros.dias_seguranca)
        # A média de venda sai do período escolhido no filtro (pedido dele em
        # 14/10/2026); sem venda nenhuma lá, volta para os doze meses e a linha avisa.
        venda, voltou = janela.para(produto, produto.vendas_12m or ZERO, dias)
        # O fator do ano passado conserta UMA distorção, e só ela: a média de doze meses
        # é plana e não sabe de estação (apps/compras/estacao.py). Quando a média já sai
        # de uma janela curta, ela JÁ É a venda da estação de agora — multiplicar outra
        # vez pelo fator contaria a estação duas vezes e, com o teto de 2, chegaria a
        # pedir o dobro ao fornecedor em dezembro. Então o fator entra só onde a base é
        # plana: na janela de doze meses, e no produto que voltou para ela por não ter
        # vendido nada na janela curta.
        base_e_plana = janela.e_a_padrao or voltou
        fator = (ano_passado.para(produto.codigo, dias_da_janela, dia_do_pedido)
                 if base_e_plana else None)
        resultado = calculos.calcular(
            calculos.Item(
                sku=produto.codigo,
                descricao=produto.descricao,
                estoque_utilizavel=produto.estoque or ZERO,
                vendas_liquidas=venda.unidades,
                dias_janela=venda.dias_abertos or 1,
                prazo_reposicao_dias=prazo_dias,
                custo_unitario=produto.custo,
                reservas_nao_deduzidas=produto.reservado or ZERO,
                comprado_na_janela=produto.compras_12m or ZERO,
                recebimentos_pendentes=produto.pedido_em_aberto or ZERO,
                # O mínimo que a loja cadastrou no SET é opinião de quem vende: o
                # ponto de pedido nunca fica abaixo dele.
                estoque_minimo_manual=produto.estoque_minimo_set,
                fator_de_estacao=fator.fator if fator else UM,
            ),
            parametros,
            importacao.data_corte,
            hoje,
        )
        if resultado.compra_sugerida <= 0:
            continue
        nomes.add(nome)
        qual = _urgencia(produto)
        item = ItemDaLista(
            codigo=produto.codigo,
            descricao=produto.descricao or produto.codigo,
            grupo=produto.grupo,
            codigo_barras=produto.codigo_barras or "",
            fornecedor=nome,
            urgencia=qual,
            estoque=produto.estoque or ZERO,
            a_caminho=produto.pedido_em_aberto or ZERO,
            minimo_set=produto.estoque_minimo_set,
            ponto_de_pedido=resultado.ponto_reposicao or ZERO,
            comprar=resultado.compra_sugerida,
            custo=produto.custo,
            valor=resultado.custo_compra or ZERO,
            vendas_12m=produto.vendas_12m or ZERO,
            vendas_90d=produto.vendas_90d or ZERO,
            receita_12m=produto.receita_12m or ZERO,
            dias_de_cobertura=resultado.cobertura_texto,
            prazo_dias=prazo_dias,
            prazo_assumido=assumido,
            motivo=resultado.motivo,
            fator_de_estacao=resultado.fator_de_estacao,
            comprar_sem_estacao=resultado.compra_sem_estacao,
            movimento=movimentos.para(produto),
            janela_rotulo=janela.rotulo,
            janela_voltou_para_12m=voltou,
            saldo_desprezado=resultado.saldo_negativo_desprezado,
            demanda_diaria=resultado.demanda_diaria,
            posicao_estoque=resultado.posicao_estoque,
            estoque_alvo=resultado.estoque_alvo,
            # A segurança sai da MESMA demanda que decidiu a compra (a do pedido, com o
            # ano passado dentro), senão a soma escrita na tela não fecha com o ponto.
            estoque_seguranca=(resultado.demanda_do_pedido * parametros.dias_seguranca),
            carro_chefe=produto.codigo in carros,
        )
        item.porcentagem_do_ideal = politica_de_compra.porcentagem_do_ideal(
            resultado.posicao_estoque, resultado.estoque_alvo)
        item.em_alerta = politica_de_compra.em_alerta(item.porcentagem_do_ideal,
                                                      politica.alerta_percentual)
        candidatos.append((nome, item))

    _aplicar_ajustes(candidatos)

    # Os filtros só valem depois de conhecer a loja inteira: filtro por um fornecedor que
    # não está na lista é filtro errado, e esvaziar a tela por causa disso faria a pessoa
    # pensar que não há nada para comprar.
    lista.nomes_de_fornecedor = sorted(nomes)
    lista.filtro_fornecedor = fornecedor if fornecedor in nomes else ""
    lista.filtro_urgencia = urgencia if urgencia in ROTULO else ""

    for nome, item in candidatos:
        if lista.filtro_fornecedor and nome != lista.filtro_fornecedor:
            continue
        if lista.filtro_urgencia and item.urgencia != lista.filtro_urgencia:
            continue
        bloco = por_fornecedor.get(nome)
        if bloco is None:
            bloco = por_fornecedor[nome] = ListaDoFornecedor(nome=nome)
        bloco.itens.append(item)
        # O prazo do BLOCO é o MAIOR prazo entre as linhas dele, e fica como estimado se
        # qualquer uma delas foi estimada. Antes o bloco copiava o prazo da primeira
        # linha que caísse nele, e esse número vai impresso no pedido que o fornecedor
        # recebe: um fornecedor sem prazo na ficha, cuja primeira linha mediu 3 dias e as
        # outras 21, saía com "Prazo de entrega: 3 dias". Quando a ficha tem prazo
        # informado, todas as linhas têm o mesmo e nada muda aqui; o bloco SEM FORNECEDOR,
        # que junta produtos de origens diferentes, é o que mais sofria. O maior porque o
        # pedido só está completo quando a última caixa chega.
        if item.prazo_dias is not None and (bloco.prazo_dias is None
                                            or item.prazo_dias > bloco.prazo_dias):
            bloco.prazo_dias = item.prazo_dias
        bloco.prazo_assumido = bloco.prazo_assumido or item.prazo_assumido
        # A soma é do que vai no pedido, e não da sugestão: depois de alguém mudar a
        # quantidade, um total que ainda mostrasse a conta do sistema estaria mentindo.
        bloco.valor += item.valor_do_pedido
        lista.valor += item.valor_do_pedido
        lista.quantos += 1
        if item.foi_ajustada:
            bloco.ajustados += 1
            lista.ajustados += 1
        if item.urgencia == Urgencia.FALTANDO:
            lista.faltando += 1
        elif item.urgencia == Urgencia.ABAIXO_DO_MINIMO:
            lista.abaixo_do_minimo += 1
        else:
            lista.vai_faltar += 1
        if item.prazo_assumido:
            lista.sem_prazo_informado += 1
        if nome == SEM_FORNECEDOR:
            lista.sem_fornecedor += 1
        if item.minimo_set:
            lista.com_minimo_no_set += 1
        if item.saldo_desprezado:
            lista.com_saldo_negativo += 1
        if item.janela_voltou_para_12m:
            lista.voltaram_para_12m += 1
        if item.em_alerta:
            lista.em_alerta += 1
            if item.carro_chefe:
                lista.carros_chefe_em_alerta.append(item)

    for bloco in por_fornecedor.values():
        # Dentro do fornecedor, primeiro o que já está faltando, depois o que vale mais.
        # O carro-chefe vem antes de tudo dentro do fornecedor (pedido dele em 22/10/2026,
        # "destacar para os produtos mais vendidos"): é o produto que a loja não pode
        # deixar faltar, e numa lista de duzentas linhas o que fica embaixo não é lido.
        bloco.itens.sort(key=lambda i: (not i.carro_chefe, PESO[i.urgencia], -i.valor,
                                        i.descricao))
    # Do que tem menos do ideal para o que tem mais; no empate, o que mais fatura.
    lista.carros_chefe_em_alerta.sort(
        key=lambda i: (i.porcentagem_do_ideal, -i.receita_12m, i.descricao))
    # E os fornecedores do que pesa mais no pedido para o que pesa menos, porque é
    # por aí que se começa a ligar.
    lista.fornecedores = sorted(por_fornecedor.values(), key=lambda b: (-b.valor, b.nome))
    return lista


def _aplicar_ajustes(candidatos):
    """Põe em cada item a quantidade que a gerência escolheu, se escolheu alguma.

    Uma consulta só para a lista inteira: são milhares de candidatos e um `get` por
    linha deixaria a tela de joelhos. O ajuste casa pelo código do SET, que é o que
    sobrevive à sincronização.
    """
    from apps.compras.models import AjusteDeCompra  # noqa: PLC0415 - evita ciclo no import

    por_codigo = {item.codigo: item for _, item in candidatos}
    if not por_codigo:
        return
    salvos = AjusteDeCompra.objects.filter(codigo__in=list(por_codigo)).select_related("ajustado_por")
    for ajuste in salvos:
        item = por_codigo.get(ajuste.codigo)
        if item is None:
            continue
        item.a_mais = ajuste.a_mais
        item.nao_comprar = ajuste.nao_comprar
        item.sugerida_no_ajuste = ajuste.sugerida
        item.ajustada_em = ajuste.ajustado_em
        item.ajustada_por = (
            ajuste.ajustado_por.get_full_name() or ajuste.ajustado_por.get_username()
            if ajuste.ajustado_por else ""
        )
        item.ajuste_observacao = ajuste.observacao
        item.ajuste_desatualizado = ajuste.mudou_desde(item.comprar)


def _contrapeso(bloco, importacao):
    """Quanto já está parado na prateleira vindo deste mesmo fornecedor.

    O sistema não pode mandar comprar mais de quem a loja já comprou errado sem dizer
    isso na mesma tela. São poucos fornecedores (os do começo da lista), então uma
    consulta para cada sai barato.
    """
    from django.db.models import DecimalField, ExpressionWrapper, F, Sum

    if importacao is None or bloco.nome == SEM_FORNECEDOR:
        return bloco
    parado = ExpressionWrapper(F("estoque") * F("custo"),
                               output_field=DecimalField(max_digits=16, decimal_places=2))
    consulta = so_mercadoria(importacao.itens.filter(
        fornecedor=bloco.nome, estoque__gt=0, vendas_12m__lte=0, custo__gt=0))
    resumo = consulta.annotate(v=parado).aggregate(total=Sum("v"))
    bloco.parado_na_prateleira = (resumo["total"] or ZERO).quantize(Decimal("0.01"))
    bloco.itens_parados = consulta.count()
    return bloco


def priorizar(lista, teto):
    """Separa o começo da lista: por quais fornecedores começar neste mês.

    A lista inteira costuma passar do que a loja pode gastar no mês — nesta cópia dá
    R$ 95 mil contra um teto de R$ 59,8 mil. Entregar duas mil linhas de uma vez não é
    gerenciamento, é um monte de papel.

    Quem compra não compra produto, compra de fornecedor: é uma ligação, um pedido, um
    frete. Então o corte é por fornecedor, e não por item. Os fornecedores entram na
    ordem do que a loja mais deixa de vender por falta do que eles fornecem, até encher
    o que ainda cabe no mês.

    Não é autorização de gasto: o teto é o que saiu da prateleira num mês médio, e estar
    abaixo dele nunca é motivo para comprar. É só a ordem em que se resolve.
    """
    for bloco in lista.fornecedores:
        bloco.receita_parada = sum(
            (item.receita_12m for item in bloco.itens
             if item.urgencia != Urgencia.VAI_FALTAR), ZERO)

    ordenados = sorted((b for b in lista.fornecedores if b.nome != SEM_FORNECEDOR),
                       key=lambda b: (-b.receita_parada, -b.valor, b.nome))
    cabe = max(teto.sobra, ZERO) if teto is not None else ZERO
    lista.cabe_no_mes = cabe
    lista.estourou_o_mes = teto is not None and cabe <= ZERO

    gasto = ZERO
    primeiro = []
    for bloco in ordenados:
        if primeiro and (cabe <= ZERO or gasto + bloco.valor > cabe):
            break
        primeiro.append(bloco)
        gasto += bloco.valor
        if len(primeiro) >= QUANTOS_PRIMEIRO:
            break
    for bloco in primeiro:
        _contrapeso(bloco, lista.importacao)
    lista.primeiro = primeiro
    lista.valor_primeiro = gasto
    escolhidos = {bloco.nome for bloco in primeiro}
    lista.outros = [bloco for bloco in lista.fornecedores if bloco.nome not in escolhidos]
    lista.resto = len(lista.outros)
    lista.valor_resto = lista.valor - gasto
    return lista


def em_linhas(lista):
    """A lista inteira, uma linha por produto, para o arquivo que se leva ao fornecedor."""
    # "Comprar" é o total que vai no pedido, e as duas parcelas ficam ao lado: quem abre
    # o arquivo precisa ver que alguém mexeu no número, de quanto era e quanto a mão
    # acrescentou.
    cabecalho = ("Fornecedor", "Código", "Produto", "Grupo", "Situação", "Tem na loja",
                 "A caminho", "Mínimo no SET", "Ponto de pedido", "Comprar",
                 "Sugerido pelo sistema", "Quantidade a mais", "Quem mudou",
                 "Custo unitário", "Custo total", "Prazo (dias)", "Vendeu em 12 meses")
    linhas = [cabecalho]
    for bloco in lista.fornecedores:
        for item in bloco.itens:
            linhas.append((
                item.fornecedor, item.codigo, item.descricao, item.grupo, item.rotulo,
                item.estoque, item.a_caminho,
                item.minimo_set if item.minimo_set is not None else "",
                item.ponto_de_pedido, item.quantidade,
                item.comprar if item.foi_ajustada else "",
                # As duas parcelas da soma, uma em cada coluna: no arquivo cabe, e é
                # aqui que se confere de onde veio o total que foi ao fornecedor.
                ("não comprar" if item.nao_comprar else item.a_mais) if item.foi_ajustada else "",
                item.ajustada_por if item.foi_ajustada else "",
                item.custo if item.custo is not None else "",
                item.valor_do_pedido, item.prazo_dias, item.vendas_12m,
            ))
    return linhas
