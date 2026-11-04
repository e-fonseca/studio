"""A compra guiada: perguntas, uma de cada vez, que montam o pedido de UM fornecedor.

Pedido do Edson em 02/11/2026: *"no menu compras criar um sub menu compra guiada / fazer
formato tipo apresentação, pop up, só que com perguntas fechadas ou abertas para informar
tipo ou quantidade para formatar a sugestão de compra, elaborar perguntas que façam uma
leitura de todo o estoque, venda, produto que mais vende para formatar um pedido de compra
para o fornecedor assertivo. Hoje o formato está longe de está intuitivo e fácil de operar
(...) a funcionária que trabalhava com essa parte saiu da empresa e não deixou nenhuma
informação registrada."*

A lista de compra mostra a loja inteira de uma vez: duas mil linhas, cinco números por
linha, filtros, a regra do alerta. Quem compra há anos lê aquilo; quem nunca comprou não
sabe por onde começar. A compra guiada é o mesmo trabalho na ordem em que uma pessoa
experiente o faria, uma pergunta por tela, com o número que decide a pergunta na frente.

A conta é a da lista de compra
------------------------------
Nada aqui calcula reposição. `lista_de_compra.montar` faz a conta de sempre (com o ano
passado, a janela de venda, o saldo negativo contado como zero e os ajustes já feitos na
lista), só para o fornecedor escolhido. As respostas trocam os padrões que a lista assume
calada:

1. **o prazo de entrega**, quando ninguém informou na ficha (a lista assume 15 dias);
2. **quando a pessoa volta a comprar deste fornecedor**: a lista assume a semana que vem,
   porque é revista toda semana. Quem só volta a este fornecedor daqui a um mês precisa
   que a compra dure um mês, e que entre também o que acaba antes de a compra SEGUINTE
   chegar (`calculos.Parametros.antecipar_dias`);
3. **que tipos de produto entram, e o quê**: tudo o que vai faltar, só o que já falta, ou
   só os carros-chefe;
4. **a venda de base**: o ano inteiro com a estação do ano passado, ou um pedaço recente
   (a mesma escolha do filtro "Média de venda de" da lista);
5. **a quantidade dos que mais vendem**, um por um, com a leitura de cada um;
6. **as encomendas** de cliente e as sugestões da equipe;
7. **o orçamento**, que corta pelo fim da fila: o que menos vende sai primeiro.

Cada opção mostra o que ela faz com o pedido (quanto custa, quantos produtos, quanto
tempo dura) antes de a pessoa escolher: pergunta sem consequência à vista é chute.

O que ela não faz
-----------------
Não compra sozinha: o pedido só nasce no clique de uma pessoa, e o da Líder de loja espera
a gerência (`apps/pedidos/servicos.py`). Não passa do orçamento sem a pessoa digitar a
quantidade. Não inventa número: produto sem custo no SET sai sem valor, e a tela diz.

As respostas ficam em `CompraGuiada.respostas`, e é isso que registra COMO cada compra foi
decidida. As chaves:

    prazo            dias que o fornecedor leva (só quando a ficha não tinha)
    prazo_nao_sabe   a pessoa disse que não sabe: vale o prazo assumido
    proxima_compra   em quantos dias a pessoa volta a comprar deste fornecedor
    tipos            os grupos de produto que entram (ausente: todos)
    entra            "tudo", "faltando" ou "carro_chefe"
    media            a janela de venda (as chaves de apps/compras/janela.py)
    quantidades      código -> "sugerida", "metade", "dobro", "nao" ou um número
    outros           código -> unidades que a pessoa pôs à mão na conferência, entre os
                     outros produtos do fornecedor (1.47.0)
    encomendas       código -> unidades encomendadas por cliente
    equipe           id da sugestão da equipe -> unidades
    orcamento        "mes", "valor" ou "livre"; orcamento_valor quando "valor"
    recado           o que vai escrito no pedido para o fornecedor
    respondidos      as perguntas já respondidas, na ordem
"""

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Max, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.auditoria.servicos import registrar
from apps.core import procura
from apps.core.templatetags.cabana import quantidade as escrever, reais

from . import calculos, janela as janelas, limite, lista_de_compra
from . import politica as politica_de_compra
from .lista_de_compra import PESO, SEM_FORNECEDOR, Urgencia
from .models import CompraGuiada, PoliticaDeCompra, SugestaoDeCompra
from .sugestoes import so_mercadoria

ZERO = Decimal("0")
UM = Decimal("1")
CENTAVO = Decimal("0.01")

# A semana que a lista de compra assume até a próxima chance de comprar.
HORIZONTE_DA_LISTA = calculos.Parametros().horizonte_revisao_dias

PROXIMA_COMPRA = (
    (7, "Na semana que vem"),
    (15, "Daqui a 15 dias"),
    (30, "Daqui a 1 mês"),
    (60, "Daqui a 2 meses"),
    (90, "Daqui a 3 meses"),
)
# Um mês, e não a semana da lista: o teto de compra é mensal, e na foto de 20/09/2026 a
# loja comprou de cada fornecedor de duas a seis vezes no ano, nunca toda semana.
PROXIMA_PADRAO = 30

PRAZOS = (
    (7, "Até uma semana"),
    (15, "Umas duas semanas"),
    (30, "Um mês"),
    (45, "Mais de um mês"),
)

ENTRA = (
    ("tudo", "Tudo o que vai faltar até a próxima compra chegar"),
    ("faltando", "Só o que já está faltando ou abaixo do mínimo"),
    ("carro_chefe", "Só os carros-chefe"),
)
ENTRA_PADRAO = "tudo"

# A venda de base: as mesmas janelas do filtro da lista de compra, ditas como pergunta.
MEDIAS = (
    ("", "O ano inteiro, com a estação do ano passado"),
    ("180", "Os últimos 6 meses"),
    ("90", "Os últimos 3 meses"),
    ("30", "Os últimos 30 dias"),
)

ORCAMENTOS = ("mes", "valor", "livre")

# Quantos produtos ganham uma pergunta só deles. Cinco é o que a pessoa responde com
# atenção; o resto segue a conta e aparece inteiro na conferência, onde dá para mudar.
QUANTOS_PRINCIPAIS = 5
# Quantos fornecedores aparecem em cartão na abertura; os outros ficam na caixa de escolha.
QUANTOS_NA_ABERTURA = 6
# Quantos produtos a busca de encomenda mostra.
QUANTOS_ACHADOS = 8
# Quantos carros-chefe em alerta a abertura mostra.
QUANTOS_CARROS = 5
MAIOR_QUANTIDADE = Decimal("99999")

PRAZO = "prazo"
PROXIMA = "proxima-compra"
TIPOS = "tipos"
VENDA = "venda"
ENCOMENDAS = "encomendas"
ORCAMENTO = "orcamento"
REVISAO = "revisao"
PRODUTO = "produto-"


class RespostaInvalida(Exception):
    """A resposta não serve, numa frase que vai para a tela."""


# --------------------------------------------------------------------------- números


def numero(bruto, *, maximo=MAIOR_QUANTIDADE, inteiro=False):
    """O número digitado, com vírgula ou ponto. None quando vazio; erro quando não é número."""
    texto = (str(bruto) if bruto is not None else "").strip().replace(" ", "")
    if not texto:
        return None
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        valor = Decimal(texto)
    except InvalidOperation:
        raise RespostaInvalida("Escreva só o número, por exemplo 12.") from None
    if not valor.is_finite() or valor < 0:
        raise RespostaInvalida("O número não pode ser negativo.")
    if valor > maximo:
        raise RespostaInvalida(f"O número passa do maior aceito ({escrever(maximo)}).")
    if inteiro and valor != valor.to_integral_value():
        raise RespostaInvalida("Escreva um número inteiro de dias.")
    return valor


def _para_texto(valor):
    return format(valor.normalize(), "f") if isinstance(valor, Decimal) else str(valor)


def _reais_exatos(valor):
    return (valor or ZERO).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def _dias_que_cobre(unidades, demanda_diaria):
    if not demanda_diaria or demanda_diaria <= ZERO:
        return None
    return int((unidades or ZERO) / demanda_diaria)


# --------------------------------------------------------------------------- a linha


@dataclass
class Linha:
    """Um produto da compra: o que o sistema pede, o que a pessoa decidiu e a encomenda."""

    codigo: str
    descricao: str
    grupo: str
    codigo_barras: str = ""
    custo: Decimal = None
    estoque: Decimal = ZERO
    a_caminho: Decimal = ZERO
    vendas_12m: Decimal = ZERO
    vendas_90d: Decimal = ZERO
    receita_12m: Decimal = ZERO
    urgencia: str = ""
    carro_chefe: bool = False
    # O que o sistema pede, já com o que a gerência mudou na lista de compra.
    sugerida: Decimal = ZERO
    demanda_diaria: Decimal = ZERO
    item: object = None  # a linha da lista de compra, quando o produto está nela
    # O que a pessoa respondeu sobre este produto, e quanto isso dá.
    escolha: str = ""
    decidida: Decimal = None
    encomenda: Decimal = ZERO
    # Ficou de fora porque o orçamento acabou antes de chegar nela.
    cortada: bool = False
    # Entrou só porque a pessoa digitou a quantidade nos outros produtos do fornecedor,
    # na conferência (1.47.0): a conta não pedia, ou pedia fora do que ela escolheu.
    a_mao: bool = False
    # Na lista dos outros produtos: por que a conta não pôs este no pedido.
    nota: str = ""

    @property
    def reposicao(self):
        """A parte da quantidade que repõe a prateleira (sem a encomenda)."""
        if self.cortada:
            return ZERO
        return self.decidida if self.decidida is not None else self.sugerida

    @property
    def quantidade(self):
        """O que vai no pedido: a reposição mais o que foi encomendado."""
        return (self.reposicao or ZERO) + (self.encomenda or ZERO)

    @property
    def valor_do_pedido(self):
        if self.custo is None:
            return ZERO
        return _reais_exatos(self.quantidade * self.custo)

    @property
    def valor_da_reposicao(self):
        if self.custo is None:
            return ZERO
        return _reais_exatos((self.decidida if self.decidida is not None else self.sugerida)
                             * self.custo)

    @property
    def decidida_pela_pessoa(self):
        return self.decidida is not None

    @property
    def foi_ajustada(self):
        """Quantidade que é decisão de gente: sai em marrom na folha do pedido."""
        if self.encomenda > ZERO:
            return True
        if self.decidida is not None and self.decidida != self.sugerida:
            return True
        return bool(self.item is not None and self.item.foi_ajustada)

    @property
    def rotulo(self):
        if self.urgencia:
            return lista_de_compra.ROTULO.get(self.urgencia, "Encomenda")
        return "Encomenda" if self.encomenda > ZERO else "Fora da conta"

    @property
    def por_mes(self):
        """Quanto vende num mês, na média da venda de base."""
        return (self.demanda_diaria * 30).quantize(Decimal("0.1"))

    @property
    def cobre(self):
        """Quanto tempo a quantidade do pedido dura, em palavras ("2 meses")."""
        return lista_de_compra.duracao(_dias_que_cobre(self.quantidade, self.demanda_diaria))

    @property
    def cobre_mais_de_um_ano(self):
        dias = _dias_que_cobre(self.quantidade, self.demanda_diaria)
        return dias is not None and dias > 365

    @property
    def parou_de_vender(self):
        """Vendeu no ano e nada nos últimos 90 dias: a pergunta que vale fazer antes."""
        return self.vendas_12m > ZERO and self.vendas_90d <= ZERO

    @property
    def ajuste_da_lista(self):
        """A frase do que a gerência já tinha mudado na lista de compra, se mudou."""
        item = self.item
        if item is None or not item.foi_ajustada:
            return ""
        quem = item.ajustada_por or "a gerência"
        if item.nao_comprar:
            return f"Na lista de compra, {quem} marcou para não comprar agora."
        sinal = "acrescentou" if item.a_mais > ZERO else "tirou"
        return f"Na lista de compra, {quem} {sinal} {escrever(abs(item.a_mais))} à sugestão."

    def opcoes(self):
        """As respostas prontas da pergunta "quantos comprar?", cada uma com o que dá.

        A sugestão do sistema, a metade e o dobro: são as três que uma pessoa de compras
        pensaria, e cada uma vem com quanto tempo dura e quanto custa. Opção repetida
        (metade de 1 é 1) não aparece duas vezes.
        """
        base = self.sugerida
        vistas, saida = set(), []
        candidatas = [("sugerida", base, "Sugestão do sistema")]
        if base >= 2:
            candidatas.append(("metade", (base / 2).to_integral_value(rounding=ROUND_CEILING),
                               "A metade"))
        if base > ZERO:
            candidatas.append(("dobro", base * 2, "O dobro"))
        for chave, unidades, rotulo in candidatas:
            if unidades <= ZERO or unidades in vistas:
                continue
            vistas.add(unidades)
            dias = _dias_que_cobre(unidades + self.encomenda, self.demanda_diaria)
            saida.append(Opcao(chave=chave, rotulo=rotulo, unidades=unidades,
                               valor=_reais_exatos(unidades * self.custo) if self.custo is not None else None,
                               cobre=lista_de_compra.duracao(dias),
                               longe=dias is not None and dias > 365))
        return saida


@dataclass
class Opcao:
    """Uma resposta pronta, com a consequência dela escrita ao lado."""

    chave: object
    rotulo: str
    unidades: Decimal = None
    valor: Decimal = None
    quantos: int = None
    cobre: str = ""
    longe: bool = False
    recomendada: bool = False
    nota: str = ""
    desligada: bool = False


def _resolver(escolha, sugerida):
    """O número que a resposta guardada vale, contra a sugestão de AGORA.

    "Sugestão", "metade" e "dobro" ficam guardados como palavra, e não como número: se a
    pessoa volta e muda a próxima compra, a sugestão muda, e a metade dela acompanha.
    """
    if escolha in ("", None):
        return None
    if escolha == "sugerida":
        return sugerida
    if escolha == "metade":
        return (sugerida / 2).to_integral_value(rounding=ROUND_CEILING) if sugerida >= 2 else sugerida
    if escolha == "dobro":
        return sugerida * 2
    if escolha == "nao":
        return ZERO
    try:
        return Decimal(str(escolha))
    except InvalidOperation:
        return None


def _prioridade(linha):
    """A ordem da fila: o que corta por último vem primeiro.

    Carro-chefe, depois o que já está faltando, depois o que mais fatura: o orçamento
    corta pelo fim, que é o que menos faz falta na prateleira.
    """
    return (not linha.carro_chefe, PESO.get(linha.urgencia, 3), -(linha.receita_12m or ZERO),
            linha.descricao)


def _linha_do_item(item):
    return Linha(
        codigo=item.codigo, descricao=item.descricao, grupo=item.grupo or "",
        codigo_barras=item.codigo_barras or "", custo=item.custo, estoque=item.estoque,
        a_caminho=item.a_caminho, vendas_12m=item.vendas_12m, vendas_90d=item.vendas_90d,
        receita_12m=item.receita_12m, urgencia=item.urgencia, carro_chefe=item.carro_chefe,
        sugerida=item.quantidade, demanda_diaria=item.demanda_diaria or ZERO, item=item,
    )


def _linha_do_produto(produto, dias_abertos, carros):
    """Produto que não está na lista de compra e entrou por encomenda."""
    dias = dias_abertos or 365
    venda = produto.vendas_12m or ZERO
    return Linha(
        codigo=produto.codigo, descricao=produto.descricao or produto.codigo,
        grupo=produto.grupo or "", codigo_barras=produto.codigo_barras or "",
        custo=produto.custo, estoque=produto.estoque or ZERO,
        a_caminho=produto.pedido_em_aberto or ZERO, vendas_12m=venda,
        vendas_90d=produto.vendas_90d or ZERO, receita_12m=produto.receita_12m or ZERO,
        carro_chefe=produto.codigo in carros,
        demanda_diaria=(venda / dias) if venda > ZERO else ZERO,
    )


# --------------------------------------------------------------------------- a proposta


@dataclass
class Tipo:
    """Um grupo de produto do fornecedor, com o que ele tem para comprar."""

    grupo: str
    quantos: int = 0
    valor: Decimal = ZERO
    faltando: int = 0
    # Quantos entram em cada resposta de "o que entra": a tela soma os tipos marcados.
    faltando_ou_abaixo: int = 0
    carros_chefe: int = 0
    vendeu_12m: Decimal = ZERO
    escolhido: bool = True


@dataclass
class BlocoDaGuiada:
    """O pedido de um fornecedor do jeito que a folha e o registro do pedido leem."""

    nome: str
    itens: list
    prazo_dias: int = None
    prazo_assumido: bool = False

    @property
    def ajustados(self):
        return sum(1 for item in self.itens if item.foi_ajustada)


@dataclass
class Proposta:
    fornecedor: str
    importacao: object = None
    data_corte: object = None
    prazo_dias: int = lista_de_compra.PRAZO_PADRAO_DIAS
    prazo_origem: str = "assumido"  # ficha, medido, assumido, respondido
    proxima_compra: int = PROXIMA_PADRAO
    media: str = ""
    entra: str = ENTRA_PADRAO
    tipos: list = field(default_factory=list)
    linhas: list = field(default_factory=list)
    principais: list = field(default_factory=list)
    # Tudo o que a lista de compra pede deste fornecedor, antes dos tipos e do "o que
    # entra": a conferência mostra no começo dos outros o que ficou de fora por escolha.
    itens_da_lista: list = field(default_factory=list)
    # Quantas linhas cada resposta de "o que entra" daria, com os tipos escolhidos.
    por_entra: dict = field(default_factory=dict)
    orcamento: Decimal = None
    orcamento_tipo: str = ""
    total_sem_corte: Decimal = ZERO
    estacao_mexeu: int = 0
    estacao_subiu: int = 0
    voltaram_para_12m: int = 0
    janela_rotulo: str = ""
    saldo_negativo: int = 0

    @property
    def no_pedido(self):
        return [linha for linha in self.linhas if linha.quantidade > ZERO]

    @property
    def cortadas(self):
        return [linha for linha in self.linhas if linha.cortada]

    @property
    def fora_do_pedido(self):
        """Linhas que estão na compra mas não vão no papel: zeradas ou cortadas."""
        return [linha for linha in self.linhas if linha.quantidade <= ZERO]

    @property
    def total(self):
        return sum((linha.valor_do_pedido for linha in self.no_pedido), ZERO)

    @property
    def unidades(self):
        return sum((linha.quantidade for linha in self.no_pedido), ZERO)

    @property
    def longe(self):
        """Linhas que a conta pôs no pedido e que duram mais de um ano na prateleira.

        Ficam de fora a encomenda (o cliente pediu) e a quantidade que a pessoa escolheu
        (ela já viu quanto dura). O resto é quase sempre o estoque mínimo cadastrado no SET
        (2.807 produtos têm um em 20/09/2026) maior do que o produto vende: dinheiro
        parado, o maior problema da loja. A conferência pergunta antes de gerar.
        """
        return [linha for linha in self.no_pedido
                if linha.cobre_mais_de_um_ano and linha.encomenda <= ZERO
                and not linha.decidida_pela_pessoa]

    @property
    def valor_longe(self):
        return sum((linha.valor_do_pedido for linha in self.longe), ZERO)

    @property
    def valor_cortado(self):
        return sum((linha.valor_da_reposicao for linha in self.cortadas), ZERO)

    @property
    def sem_custo(self):
        return sum(1 for linha in self.no_pedido if linha.custo is None)

    @property
    def encomendas(self):
        return [linha for linha in self.linhas if linha.encomenda > ZERO]

    @property
    def decididas(self):
        return sum(1 for linha in self.linhas if linha.decidida_pela_pessoa)

    @property
    def prazo_assumido(self):
        return self.prazo_origem == "assumido"

    @property
    def tempo_ate_chegar(self):
        """Do pedido de hoje até a compra seguinte chegar: o tempo que esta compra cobre."""
        return self.proxima_compra + (self.prazo_dias or 0)

    def bloco(self):
        return BlocoDaGuiada(nome=self.fornecedor, itens=self.no_pedido,
                             prazo_dias=self.prazo_dias, prazo_assumido=self.prazo_assumido)

    def linha(self, codigo):
        for linha in self.linhas:
            if linha.codigo == codigo:
                return linha
        return None


def _parametros(proxima_compra):
    return calculos.Parametros(horizonte_revisao_dias=proxima_compra,
                               antecipar_dias=max(proxima_compra - HORIZONTE_DA_LISTA, 0))


def _proxima(respostas):
    try:
        dias = int(respostas.get("proxima_compra") or PROXIMA_PADRAO)
    except (TypeError, ValueError):
        dias = PROXIMA_PADRAO
    return dias if dias in dict(PROXIMA_COMPRA) else PROXIMA_PADRAO


def _encomendas(respostas):
    """Unidades encomendadas por código: as de cliente mais as da equipe."""
    por_codigo = {}
    for codigo, bruto in (respostas.get("encomendas") or {}).items():
        valor = _resolver(bruto, ZERO) or ZERO
        if valor > ZERO:
            por_codigo[codigo] = por_codigo.get(codigo, ZERO) + valor
    equipe = respostas.get("equipe") or {}
    if equipe:
        sugestoes = SugestaoDeCompra.objects.filter(pk__in=[int(chave) for chave in equipe
                                                            if str(chave).isdigit()])
        for sugestao in sugestoes:
            valor = _resolver(equipe.get(str(sugestao.pk)), ZERO) or ZERO
            if sugestao.codigo and valor > ZERO:
                por_codigo[sugestao.codigo] = por_codigo.get(sugestao.codigo, ZERO) + valor
    return por_codigo


def montar(compra, importacao, *, proxima_compra=None, media=None, aplicar_orcamento=True,
           leitura=None, hoje=None):
    """A compra como está agora, com as respostas dadas até aqui.

    `proxima_compra` e `media` trocam UMA resposta sem gravar nada: é como a tela mostra o
    que cada opção daria antes de a pessoa escolher.
    """
    respostas = compra.respostas or {}
    nome = compra.fornecedor
    proposta = Proposta(fornecedor=nome, importacao=importacao)
    proposta.proxima_compra = proxima_compra or _proxima(respostas)
    proposta.media = janelas.valida(respostas.get("media", "") if media is None else media)
    proposta.entra = respostas.get("entra") if respostas.get("entra") in dict(ENTRA) else ENTRA_PADRAO
    if importacao is None:
        return proposta
    proposta.data_corte = importacao.data_corte

    from apps.fornecedores import servicos as fornecedores  # noqa: PLC0415

    informados = fornecedores.prazos_informados()
    respondido = respostas.get("prazo")
    prazos = {nome: int(respondido)} if respondido else None
    lista = lista_de_compra.montar(
        importacao, fornecedor=nome, media=proposta.media, hoje=hoje,
        parametros=_parametros(proposta.proxima_compra), so_do_fornecedor=nome, prazos=prazos)
    bloco = lista.fornecedores[0] if lista.fornecedores else None
    proposta.janela_rotulo = lista.janela.rotulo if lista.janela else ""

    if respondido:
        proposta.prazo_dias, proposta.prazo_origem = int(respondido), "respondido"
    elif nome in informados:
        proposta.prazo_dias, proposta.prazo_origem = informados[nome], "ficha"
    elif bloco is not None and not bloco.prazo_assumido:
        proposta.prazo_dias, proposta.prazo_origem = bloco.prazo_dias, "medido"
    else:
        proposta.prazo_dias = lista_de_compra.PRAZO_PADRAO_DIAS

    itens = bloco.itens if bloco else []
    proposta.itens_da_lista = itens
    _tipos(proposta, importacao, itens, respostas)
    escolhidos = {tipo.grupo for tipo in proposta.tipos if tipo.escolhido}

    def entra(item, regra):
        if regra == "faltando":
            return item.urgencia in (Urgencia.FALTANDO, Urgencia.ABAIXO_DO_MINIMO)
        if regra == "carro_chefe":
            return item.carro_chefe
        return True

    dos_tipos = [item for item in itens if (item.grupo or "") in escolhidos]
    proposta.por_entra = {chave: sum(1 for item in dos_tipos if entra(item, chave))
                          for chave, _ in ENTRA}
    linhas = [_linha_do_item(item) for item in dos_tipos if entra(item, proposta.entra)]
    proposta.estacao_mexeu = sum(1 for linha in linhas if linha.item.estacao_mexeu)
    proposta.estacao_subiu = sum(1 for linha in linhas
                                 if linha.item.estacao_mexeu and linha.item.fator_de_estacao > UM)
    proposta.voltaram_para_12m = sum(1 for linha in linhas if linha.item.janela_voltou_para_12m)
    proposta.saldo_negativo = sum(1 for linha in linhas if linha.item.saldo_desprezado)

    # Os que mais vendem ganham uma pergunta cada, antes de qualquer decisão: assim a ordem
    # das perguntas não muda enquanto a pessoa responde.
    proposta.principais = [linha for linha in sorted(
        linhas, key=lambda l: (not l.carro_chefe, -(l.receita_12m or ZERO), l.descricao))
        if linha.sugerida > ZERO][:QUANTOS_PRINCIPAIS]

    # As encomendas: somam à linha do produto, ou trazem o produto que não estava nela.
    encomendas = _encomendas(respostas)
    por_codigo = {linha.codigo: linha for linha in linhas}
    da_lista = {item.codigo: item for item in itens}
    carros = {item.codigo for item in itens if item.carro_chefe}
    fora = [codigo for codigo in encomendas if codigo not in por_codigo]
    if fora:
        produtos = {produto.codigo: produto
                    for produto in importacao.itens.filter(codigo__in=fora)}
        for codigo in fora:
            if codigo in da_lista:
                linha = _linha_do_item(da_lista[codigo])
                # Estava na lista, mas fora dos tipos ou do "o que entra": vem só a encomenda.
                linha.sugerida = ZERO
            elif codigo in produtos:
                linha = _linha_do_produto(produtos[codigo], importacao.dias_abertos_12m, carros)
            else:
                continue
            linhas.append(linha)
            por_codigo[codigo] = linha
    for codigo, unidades in encomendas.items():
        if codigo in por_codigo:
            por_codigo[codigo].encomenda = unidades

    # O que a pessoa digitou nos outros produtos do fornecedor, na conferência (1.47.0):
    # o produto entra na compra com o número dela, mesmo sem a conta pedir. Só produto
    # deste fornecedor, que é a lista que a conferência mostra. Fica numa chave própria,
    # e não em "quantidades", para a resposta de uma pergunta antiga (o "dobro" de um
    # produto que depois saiu pelo "o que entra") não voltar sozinha para o pedido.
    outros = respostas.get("outros") or {}
    novos = [codigo for codigo in outros if codigo not in por_codigo]
    if novos:
        produtos = {produto.codigo: produto for produto in so_mercadoria(
            importacao.itens.filter(codigo__in=novos, fornecedor=nome))}
        for codigo in novos:
            if codigo in da_lista:
                linha = _linha_do_item(da_lista[codigo])
            elif codigo in produtos:
                linha = _linha_do_produto(produtos[codigo], importacao.dias_abertos_12m, carros)
            else:
                continue
            linha.a_mao = True
            linhas.append(linha)
            por_codigo[codigo] = linha
    # Produto posto à mão que depois entrou na conta (outra importação, outra resposta):
    # continua valendo o número da pessoa, como qualquer quantidade escolhida.
    for codigo, valor in outros.items():
        if codigo in por_codigo:
            por_codigo[codigo].escolha = valor
            por_codigo[codigo].decidida = _resolver(valor, por_codigo[codigo].sugerida)

    for codigo, escolha in (respostas.get("quantidades") or {}).items():
        linha = por_codigo.get(codigo)
        # A linha posta à mão segue só o número dos outros: a resposta de quando ela era
        # da conta (um "dobro" antigo) não volta para o pedido por baixo dele.
        if linha is None or linha.a_mao:
            continue
        linha.escolha = escolha
        linha.decidida = _resolver(escolha, linha.sugerida)

    linhas.sort(key=_prioridade)
    proposta.linhas = linhas
    proposta.total_sem_corte = proposta.total
    if aplicar_orcamento:
        _orcamento(proposta, respostas, importacao, leitura)
    return proposta


def _tipos(proposta, importacao, itens, respostas):
    """Os grupos de produto do fornecedor que têm o que comprar, com a venda do ano."""
    por_grupo = {}
    for item in itens:
        tipo = por_grupo.setdefault(item.grupo or "", Tipo(grupo=item.grupo or ""))
        tipo.quantos += 1
        tipo.valor += item.valor_do_pedido
        if item.urgencia == Urgencia.FALTANDO:
            tipo.faltando += 1
        if item.urgencia in (Urgencia.FALTANDO, Urgencia.ABAIXO_DO_MINIMO):
            tipo.faltando_ou_abaixo += 1
        if item.carro_chefe:
            tipo.carros_chefe += 1
    if por_grupo:
        vendas = (so_mercadoria(importacao.itens.filter(fornecedor=proposta.fornecedor))
                  .values("grupo").annotate(receita=Sum("receita_12m")))
        for linha in vendas:
            if (linha["grupo"] or "") in por_grupo:
                por_grupo[linha["grupo"] or ""].vendeu_12m = linha["receita"] or ZERO
    pedidos = set(respostas.get("tipos") or [])
    for tipo in por_grupo.values():
        tipo.escolhido = not pedidos or tipo.grupo in pedidos
    if pedidos and not any(tipo.escolhido for tipo in por_grupo.values()):
        # Os tipos guardados não existem mais nesta foto: vale tudo, em vez de nada.
        for tipo in por_grupo.values():
            tipo.escolhido = True
    proposta.tipos = sorted(por_grupo.values(), key=lambda t: (-t.vendeu_12m, -t.valor, t.grupo))


def _orcamento(proposta, respostas, importacao, leitura):
    """Corta pelo fim da fila o que não cabe no orçamento respondido.

    Encomenda e quantidade que a pessoa escolheu não se cortam: são decisão de gente, e a
    tela avisa quando elas sozinhas já passam do orçamento. O resto entra na ordem da
    fila (carro-chefe, o que falta, o que mais fatura) enquanto couber; linha que não
    cabe é pulada, e uma menor que vem depois ainda pode caber.
    """
    tipo = respostas.get("orcamento")
    if tipo not in ORCAMENTOS or tipo == "livre":
        proposta.orcamento_tipo = tipo or ""
        return
    if tipo == "mes":
        leitura = leitura or teto_do_mes(importacao)
        teto = max(leitura.sobra, ZERO)
    else:
        try:
            teto = numero(respostas.get("orcamento_valor"), maximo=Decimal("99999999"))
        except RespostaInvalida:
            teto = None
        if teto is None:
            return
    proposta.orcamento_tipo, proposta.orcamento = tipo, _reais_exatos(teto)
    gasto = sum((_o_que_nao_se_corta(linha) for linha in proposta.linhas), ZERO)
    for linha in proposta.linhas:
        if linha.decidida_pela_pessoa or linha.sugerida <= ZERO:
            continue
        custo = linha.valor_da_reposicao
        if gasto + custo <= proposta.orcamento:
            gasto += custo
        else:
            linha.cortada = True


def _o_que_nao_se_corta(linha):
    """O valor da linha que o orçamento não corta: a escolha da pessoa e a encomenda.

    Da linha que só tem encomenda por cima da sugestão, entra aqui só a encomenda; a
    sugestão é que disputa o orçamento com as outras, no laço de _orcamento. Contar a
    linha inteira aqui, e de novo a sugestão no laço, gastava a sugestão duas vezes.
    """
    if linha.custo is None:
        return ZERO
    if linha.decidida_pela_pessoa:
        return linha.valor_do_pedido
    return _reais_exatos(linha.encomenda * linha.custo) if linha.encomenda > ZERO else ZERO


def os_demais(proposta, importacao):
    """Os outros produtos do fornecedor, para a conferência mostrar o cadastro inteiro.

    Pedido do Edson em 04/11/2026: *"em compra guiada, exibir todos os produtos de cada
    fornecedor, priorizar os produtos em falta E acabando e em seguida todos os demais."*
    Os em falta e acabando são o pedido que a conta monta (`proposta.linhas`, a mesma
    conta da lista de compra); aqui vem o resto do que o SET tem deste fornecedor, com a
    quantidade em zero, para a pessoa pôr à mão o que a conta não pediu. A ordem:

    1. o que a lista de compra pede, mas ficou fora pelos tipos ou pelo "o que entra";
    2. o que vendeu no ano, do que mais faturou para o que menos;
    3. o que não vendeu no ano e tem saldo no SET: o parado deste fornecedor;
    4. o que não vendeu nem tem saldo.

    O produto que a pessoa já pôs à mão continua no lugar dele nesta lista, com o número
    dela: trocar de tabela depois de salvar faria a pessoa procurar o que acabou de digitar.
    """
    if importacao is None or not proposta.fornecedor:
        return []
    na_conta = {linha.codigo for linha in proposta.linhas if not linha.a_mao}
    a_mao = {linha.codigo: linha for linha in proposta.linhas if linha.a_mao}
    da_lista = {item.codigo: item for item in proposta.itens_da_lista}
    carros = set(politica_de_compra.carros_chefe(importacao, PoliticaDeCompra.atual().carros_chefe))
    linhas = []
    for produto in so_mercadoria(importacao.itens.filter(fornecedor=proposta.fornecedor)):
        if produto.codigo in na_conta:
            continue
        linha = a_mao.get(produto.codigo)
        item = da_lista.get(produto.codigo)
        if linha is None:
            linha = (_linha_do_item(item) if item is not None
                     else _linha_do_produto(produto, importacao.dias_abertos_12m, carros))
        if item is not None:
            linha.nota = f"{lista_de_compra.ROTULO.get(item.urgencia, '').lower()}, fora do que você escolheu"
            ordem = (0, PESO.get(item.urgencia, 3), not linha.carro_chefe)
        elif (linha.vendas_12m or ZERO) > ZERO:
            linha.nota = "o que tem dá até a próxima compra"
            ordem = (1, 0, not linha.carro_chefe)
        elif (linha.estoque or ZERO) > ZERO:
            linha.nota = "parado: não vendeu no ano"
            ordem = (2, 0, True)
        else:
            linha.nota = "não vendeu no ano"
            ordem = (3, 0, True)
        if linha.a_mao:
            linha.nota = "posto por você"
        linhas.append((ordem + (-(linha.receita_12m or ZERO), linha.descricao, linha.codigo), linha))
    linhas.sort(key=lambda par: par[0])
    return [linha for _, linha in linhas]


# --------------------------------------------------------------------------- leituras


@dataclass
class TetoDoMes:
    """O teto da lista de compra, menos os pedidos feitos aqui que ainda não chegaram."""

    teto: object = None
    pedidos_abertos: Decimal = ZERO
    quantos_pedidos: int = 0

    @property
    def sobra(self):
        if self.teto is None:
            return ZERO
        return self.teto.sobra - self.pedidos_abertos

    @property
    def estourou(self):
        return self.sobra <= ZERO


def teto_do_mes(importacao):
    """Quanto ainda cabe no mês: o teto da lista de compra e os pedidos deste sistema.

    O teto conta o que o SET já lançou como compra no mês. O pedido feito aqui só entra no
    SET quando a mercadoria chega com a nota; até lá ele não está na conta do teto e o
    dinheiro já está prometido. Por isso sai da sobra o que foi pedido aqui no mês e
    ainda espera a mercadoria (ou a aprovação).
    """
    from apps.pedidos.models import ItemDoPedido, Pedido  # noqa: PLC0415

    leitura = TetoDoMes(teto=limite.teto_de(importacao))
    if importacao is None or importacao.data_corte is None:
        return leitura
    corte = importacao.data_corte
    abertos = Pedido.objects.filter(
        situacao__in=(Pedido.Situacao.ABERTO, Pedido.Situacao.AGUARDANDO),
        criado_em__year=corte.year, criado_em__month=corte.month)
    leitura.quantos_pedidos = abertos.count()
    leitura.pedidos_abertos = (ItemDoPedido.objects.filter(pedido__in=abertos)
                               .aggregate(soma=Sum("valor"))["soma"] or ZERO)
    return leitura


@dataclass
class OpcaoDeFornecedor:
    nome: str
    quantos: int = 0
    faltando: int = 0
    carros_chefe: int = 0
    valor: Decimal = ZERO
    receita_parada: Decimal = ZERO
    parado: Decimal = ZERO
    prazo_dias: int = None
    prazo_assumido: bool = False
    ultima_compra: object = None


@dataclass
class LeituraDaLoja:
    """O retrato da loja que abre a compra guiada: o estoque, a falta e o dinheiro do mês."""

    importacao: object = None
    teto: TetoDoMes = field(default_factory=TetoDoMes)
    na_prateleira: Decimal = ZERO
    parado: Decimal = ZERO
    produtos_parados: int = 0
    faltando: int = 0
    carros_chefe_em_alerta: int = 0
    alerta_percentual: int = 30
    valor_da_lista: Decimal = ZERO
    fornecedores_na_lista: int = 0
    sem_fornecedor: int = 0
    # Os carros-chefe que já caíram ao alerta, do que tem menos para o que tem mais: é o
    # "produto que mais vende" da pergunta, e cada um diz de quem comprar.
    carros: list = field(default_factory=list)
    opcoes: list = field(default_factory=list)
    outros: list = field(default_factory=list)
    todos: list = field(default_factory=list)

    @property
    def parado_porcentagem(self):
        if self.na_prateleira <= ZERO:
            return 0
        return int(self.parado * 100 / self.na_prateleira)


def _valor_em_estoque():
    return ExpressionWrapper(F("estoque") * F("custo"),
                             output_field=DecimalField(max_digits=20, decimal_places=4))


def ler_a_loja(importacao):
    """Lê a loja inteira uma vez: a lista de compra, o estoque e os fornecedores."""
    leitura = LeituraDaLoja(importacao=importacao)
    if importacao is None:
        return leitura
    leitura.teto = teto_do_mes(importacao)
    lista = lista_de_compra.montar(importacao)
    lista_de_compra.priorizar(lista, leitura.teto.teto)
    leitura.faltando = lista.faltando
    leitura.carros_chefe_em_alerta = len(lista.carros_chefe_em_alerta)
    leitura.carros = [item for item in lista.carros_chefe_em_alerta
                      if item.fornecedor and item.fornecedor != SEM_FORNECEDOR][:QUANTOS_CARROS]
    leitura.alerta_percentual = lista.alerta_percentual
    leitura.valor_da_lista = lista.valor
    leitura.sem_fornecedor = lista.sem_fornecedor

    com_saldo = so_mercadoria(importacao.itens.filter(estoque__gt=0, custo__gt=0)).annotate(
        v=_valor_em_estoque())
    soma = com_saldo.aggregate(total=Sum("v"), parado=Sum("v", filter=Q(vendas_12m__lte=0)),
                               produtos=Count("id", filter=Q(vendas_12m__lte=0)))
    leitura.na_prateleira = _reais_exatos(soma["total"])
    leitura.parado = _reais_exatos(soma["parado"])
    leitura.produtos_parados = soma["produtos"] or 0

    blocos = sorted((b for b in lista.fornecedores if b.nome != SEM_FORNECEDOR),
                    key=lambda b: (-b.receita_parada, -b.valor, b.nome))
    leitura.fornecedores_na_lista = len(blocos)
    primeiros = blocos[:QUANTOS_NA_ABERTURA]
    nomes = [b.nome for b in primeiros]
    parados = {
        linha["fornecedor"]: linha["parado"] or ZERO
        for linha in com_saldo.filter(fornecedor__in=nomes, vendas_12m__lte=0)
        .values("fornecedor").annotate(parado=Sum("v"))
    }
    ultimas = _ultimas_compras(importacao, nomes)
    for b in primeiros:
        leitura.opcoes.append(OpcaoDeFornecedor(
            nome=b.nome, quantos=b.quantos, faltando=b.faltando,
            carros_chefe=sum(1 for item in b.itens if item.carro_chefe),
            valor=b.valor, receita_parada=b.receita_parada,
            parado=_reais_exatos(parados.get(b.nome)), prazo_dias=b.prazo_dias,
            prazo_assumido=b.prazo_assumido, ultima_compra=ultimas.get(b.nome)))
    leitura.outros = [(b.nome, b.valor, b.quantos) for b in blocos[QUANTOS_NA_ABERTURA:]]
    # order_by antes do distinct: a ordem padrão do modelo entraria no SELECT DISTINCT e
    # repetiria o mesmo fornecedor uma vez por produto.
    leitura.todos = [nome for nome in importacao.itens.exclude(fornecedor="")
                     .order_by("fornecedor").values_list("fornecedor", flat=True).distinct()
                     if nome]
    return leitura


def _compras_do_fornecedor(importacao, nomes):
    """As compras já lançadas no SET (não as pendentes), com a data que vale."""
    return (importacao.compras.filter(pendente=False, fornecedor__in=nomes)
            .annotate(dia=Coalesce("data_nota", "data_pedido")).exclude(dia=None))


def _ultimas_compras(importacao, nomes):
    return {linha["fornecedor"]: linha["ultima"] for linha in
            _compras_do_fornecedor(importacao, nomes).values("fornecedor")
            .annotate(ultima=Max("dia"))}


@dataclass
class HistoricoDoFornecedor:
    """O que a loja já fez com este fornecedor: compras, venda, prateleira, o que parou."""

    nome: str
    compras_12m: int = 0
    datas: list = field(default_factory=list)
    ultima_compra: object = None
    intervalo_dias: int = None
    comprado_12m: Decimal = ZERO
    produtos: int = 0
    vendeu_12m: Decimal = ZERO
    vendeu_unidades_12m: Decimal = ZERO
    vendeu_unidades_90d: Decimal = ZERO
    na_prateleira: Decimal = ZERO
    parado: Decimal = ZERO
    produtos_parados: int = 0
    mais_vendidos: list = field(default_factory=list)

    @property
    def ritmo_dos_90_dias(self):
        """Quanto os últimos 90 dias venderam contra o ritmo do ano, em porcentagem."""
        esperado = self.vendeu_unidades_12m / 4
        if esperado <= ZERO:
            return None
        return int(((self.vendeu_unidades_90d / esperado) - 1) * 100)

    @property
    def ritmo_sem_sinal(self):
        ritmo = self.ritmo_dos_90_dias
        return abs(ritmo) if ritmo is not None else None

    @property
    def proxima_recomendada(self):
        """A próxima compra que a tela recomenda, pela frequência que a loja já tem.

        Quem compra deste fornecedor mais de uma vez por mês recebe a recomendação de
        voltar antes; os outros, um mês, que é o tamanho do teto de compra. Comprar para
        três meses porque se compra a cada três meses prende o dinheiro de três meses de
        uma vez, e é essa a escolha que a pessoa tem que fazer de olhos abertos.
        """
        if self.intervalo_dias is not None and self.intervalo_dias <= 10:
            return 7
        if self.intervalo_dias is not None and self.intervalo_dias <= 22:
            return 15
        return PROXIMA_PADRAO

    @property
    def pelo_ritmo(self):
        return self.intervalo_dias is not None and self.intervalo_dias <= 22

    @property
    def porque_da_recomendada(self):
        """A frase que vai embaixo da resposta recomendada: por que ela, e não outra."""
        if self.pelo_ritmo:
            return f"A loja compra dele a cada {self.intervalo_dias} dias, em média."
        if self.intervalo_dias is not None and self.intervalo_dias > 45:
            return (f"A loja compra dele a cada {self.intervalo_dias} dias, mas um mês é o "
                    "tamanho do teto de compra: comprar para mais tempo prende o dinheiro de uma vez.")
        return "Um mês é o tamanho do teto de compra."


def historico_do_fornecedor(importacao, nome):
    historico = HistoricoDoFornecedor(nome=nome)
    if importacao is None or importacao.data_corte is None:
        return historico
    desde = importacao.data_corte - timedelta(days=365)
    compras = _compras_do_fornecedor(importacao, [nome]).filter(dia__gte=desde)
    datas = sorted(set(compras.values_list("dia", flat=True)))
    historico.datas = datas
    historico.compras_12m = len(datas)
    historico.ultima_compra = (_ultimas_compras(importacao, [nome]) or {}).get(nome)
    historico.comprado_12m = compras.aggregate(soma=Sum("valor_total"))["soma"] or ZERO
    if len(datas) >= 2:
        historico.intervalo_dias = int((datas[-1] - datas[0]).days / (len(datas) - 1))

    produtos = so_mercadoria(importacao.itens.filter(fornecedor=nome))
    soma = produtos.annotate(v=_valor_em_estoque()).aggregate(
        receita=Sum("receita_12m"), unidades=Sum("vendas_12m"), noventa=Sum("vendas_90d"),
        produtos=Count("id"),
        prateleira=Sum("v", filter=Q(estoque__gt=0, custo__gt=0)),
        parado=Sum("v", filter=Q(estoque__gt=0, custo__gt=0, vendas_12m__lte=0)),
        parados=Count("id", filter=Q(estoque__gt=0, custo__gt=0, vendas_12m__lte=0)))
    historico.vendeu_12m = soma["receita"] or ZERO
    historico.vendeu_unidades_12m = soma["unidades"] or ZERO
    historico.vendeu_unidades_90d = soma["noventa"] or ZERO
    historico.produtos = soma["produtos"] or 0
    historico.na_prateleira = _reais_exatos(soma["prateleira"])
    historico.parado = _reais_exatos(soma["parado"])
    historico.produtos_parados = soma["parados"] or 0
    historico.mais_vendidos = list(produtos.filter(receita_12m__gt=0)
                                   .order_by("-receita_12m", "codigo")[:3])
    return historico


# --------------------------------------------------------------------------- as perguntas


def passos(compra, proposta):
    """As perguntas desta compra, na ordem. A primeira (o fornecedor) é a abertura."""
    respostas = compra.respostas or {}
    lista = []
    if proposta.prazo_origem == "assumido" or "prazo" in respostas or respostas.get("prazo_nao_sabe"):
        lista.append(PRAZO)
    lista += [PROXIMA, TIPOS, VENDA]
    lista += [f"{PRODUTO}{posicao}" for posicao in range(1, len(proposta.principais) + 1)]
    lista += [ENCOMENDAS, ORCAMENTO, REVISAO]
    return lista


def respondida(compra, proposta, passo):
    """Se a pergunta já tem resposta.

    A de produto vale pelo PRODUTO, e não pela posição: mudar os tipos ou a venda de base
    muda quem são os cinco que mais vendem, e o segundo de agora pode ser um produto que
    ninguém olhou ainda.
    """
    respostas = compra.respostas or {}
    if passo.startswith(PRODUTO):
        linha = principal(proposta, passo)
        return linha is not None and linha.codigo in (respostas.get("quantidades") or {})
    return passo in (respostas.get("respondidos") or [])


def onde_parou(compra, proposta):
    """A primeira pergunta ainda sem resposta; a conferência quando todas têm."""
    for passo in passos(compra, proposta):
        if passo != REVISAO and not respondida(compra, proposta, passo):
            return passo
    return REVISAO


def principal(proposta, passo):
    """A linha do produto da pergunta `produto-N`, ou None quando N não existe."""
    if not passo.startswith(PRODUTO):
        return None
    try:
        posicao = int(passo[len(PRODUTO):])
    except ValueError:
        return None
    if 1 <= posicao <= len(proposta.principais):
        return proposta.principais[posicao - 1]
    return None


def _respondeu(compra, passo):
    respondidos = list((compra.respostas or {}).get("respondidos") or [])
    if passo not in respondidos:
        respondidos.append(passo)
    compra.respostas["respondidos"] = respondidos


def opcoes_de_prazo(compra, importacao):
    """As respostas prontas do prazo de entrega, cada uma com o pedido que ela dá.

    Prazo maior é pedido maior: a compra tem que segurar a loja enquanto a mercadoria não
    chega. A conta roda numa cópia da compra, que não é gravada.
    """
    saida = []
    for dias, rotulo in PRAZOS:
        teste = CompraGuiada(fornecedor=compra.fornecedor,
                             respostas={**(compra.respostas or {}), "prazo": dias})
        proposta = montar(teste, importacao, aplicar_orcamento=False)
        saida.append(Opcao(chave=dias, rotulo=rotulo, valor=proposta.total,
                           quantos=len(proposta.no_pedido)))
    return saida


def opcoes_de_proxima_compra(compra, importacao, historico):
    saida = []
    recomendada = historico.proxima_recomendada
    for dias, rotulo in PROXIMA_COMPRA:
        proposta = montar(compra, importacao, proxima_compra=dias, aplicar_orcamento=False)
        saida.append(Opcao(chave=dias, rotulo=rotulo, valor=proposta.total,
                           quantos=len(proposta.no_pedido), recomendada=dias == recomendada,
                           cobre=lista_de_compra.duracao(proposta.tempo_ate_chegar)))
    return saida


def opcoes_de_venda(compra, importacao):
    saida = []
    for chave, rotulo in MEDIAS:
        proposta = montar(compra, importacao, media=chave, aplicar_orcamento=False)
        saida.append(Opcao(chave=chave, rotulo=rotulo, valor=proposta.total,
                           quantos=len(proposta.no_pedido), recomendada=chave == "",
                           nota=(f"{proposta.estacao_mexeu} produto"
                                 f"{'s' if proposta.estacao_mexeu != 1 else ''} com a estação "
                                 "do ano passado" if chave == "" and proposta.estacao_mexeu else "")))
    return saida


def opcoes_de_orcamento(proposta, teto):
    """As três respostas do orçamento, com o que cada uma deixa no pedido."""
    total = proposta.total_sem_corte
    sobra = max(teto.sobra, ZERO)
    mes = Opcao(chave="mes", rotulo="Até o que sobra no teto do mês", valor=_reais_exatos(sobra))
    if teto.estourou:
        mes.nota = "O mês já passou do teto: só entra o que você escolher à mão e as encomendas."
    elif total <= sobra:
        mes.nota = "O pedido cabe inteiro."
    else:
        mes.nota = (f"Ficam de fora os que menos vendem, até o pedido caber "
                    f"({reais(total - sobra)} a menos).")
    valor = Opcao(chave="valor", rotulo="Até um valor que eu digo")
    livre = Opcao(chave="livre", rotulo="Sem limite: eu confiro linha a linha",
                  valor=total, nota="O pedido fica com tudo o que a conta pediu.")
    if teto.estourou:
        valor.recomendada = True
    else:
        mes.recomendada = True
    return [mes, valor, livre]


def salvar_resposta(compra, passo, dados, usuario, importacao):
    """Guarda a resposta de uma pergunta. Devolve o recado para a tela (ou "")."""
    respostas = compra.respostas = dict(compra.respostas or {})
    recado = ""
    if passo == PRAZO:
        recado = _salvar_prazo(compra, dados, usuario)
    elif passo == PROXIMA:
        try:
            dias = int(dados.get("proxima_compra") or 0)
        except (TypeError, ValueError):
            dias = 0
        if dias not in dict(PROXIMA_COMPRA):
            raise RespostaInvalida("Escolha quando você volta a comprar deste fornecedor.")
        respostas["proxima_compra"] = dias
    elif passo == TIPOS:
        proposta = montar(compra, importacao, aplicar_orcamento=False)
        existentes = {tipo.grupo for tipo in proposta.tipos}
        tipos = [tipo for tipo in dados.getlist("tipo") if tipo in existentes]
        if existentes and not tipos:
            raise RespostaInvalida("Marque pelo menos um tipo de produto.")
        regra = dados.get("entra") or ENTRA_PADRAO
        if regra not in dict(ENTRA):
            raise RespostaInvalida("Escolha o que entra nesta compra.")
        respostas["tipos"] = [] if set(tipos) == existentes else sorted(tipos)
        respostas["entra"] = regra
    elif passo == VENDA:
        media = dados.get("media", "")
        if media not in dict(MEDIAS):
            raise RespostaInvalida("Escolha em que venda o sistema se baseia.")
        respostas["media"] = media
    elif passo.startswith(PRODUTO):
        proposta = montar(compra, importacao, aplicar_orcamento=False)
        linha = principal(proposta, passo)
        if linha is None:
            raise RespostaInvalida("Este produto saiu da compra; siga para a próxima pergunta.")
        respostas.setdefault("quantidades", {})
        respostas["quantidades"][linha.codigo] = _escolha_de_quantidade(dados)
    elif passo == ENCOMENDAS:
        recado = _salvar_encomendas(compra, dados, importacao)
        if dados.get("acao") in ("adicionar", "tirar"):
            # Continua na mesma pergunta, que ainda não conta como respondida; mas a
            # encomenda posta (ou tirada) tem que ficar gravada antes de voltar à tela.
            compra.save(update_fields=["respostas", "atualizada_em"])
            return recado
    elif passo == ORCAMENTO:
        tipo = dados.get("orcamento")
        if tipo not in ORCAMENTOS:
            raise RespostaInvalida("Escolha até quanto este pedido pode chegar.")
        if tipo == "valor":
            valor = numero(dados.get("orcamento_valor"), maximo=Decimal("99999999"))
            if not valor:
                raise RespostaInvalida("Escreva o valor, em reais, por exemplo 2000.")
            respostas["orcamento_valor"] = _para_texto(valor)
        respostas["orcamento"] = tipo
    elif passo == REVISAO:
        _salvar_conferencia(compra, dados, importacao)
        if dados.get("acao") == "tirar_longe":
            recado = _tirar_os_que_duram_demais(compra, importacao)
    else:
        raise RespostaInvalida("Pergunta desconhecida.")
    _respondeu(compra, passo)
    compra.save(update_fields=["respostas", "atualizada_em"])
    return recado


def _escolha_de_quantidade(dados):
    escolha = dados.get("quantidade") or ""
    if escolha in ("sugerida", "metade", "dobro", "nao"):
        return escolha
    if escolha == "outro":
        valor = numero(dados.get("quantidade_outro"))
        if valor is None:
            raise RespostaInvalida("Escreva quantas unidades comprar.")
        return _para_texto(valor)
    raise RespostaInvalida("Escolha quantas unidades comprar.")


def _salvar_prazo(compra, dados, usuario):
    """O prazo de entrega: fica nesta compra e, quem pode, grava na ficha do fornecedor.

    É a informação que mais fazia falta e que ninguém registrou: o SET grava a data da nota
    e não o prazo. Gravada na ficha, vale para a lista de compra e para todas as compras
    seguintes deste fornecedor, sem ninguém perguntar de novo.
    """
    from apps.fornecedores.models import PRAZO_MAXIMO, Fornecedor  # noqa: PLC0415

    respostas = compra.respostas
    escolha = dados.get("prazo") or ""
    if escolha == "nao_sei":
        respostas.pop("prazo", None)
        respostas["prazo_nao_sabe"] = True
        return ""
    if escolha == "outro":
        valor = numero(dados.get("prazo_outro"), maximo=Decimal(PRAZO_MAXIMO), inteiro=True)
        if not valor:
            raise RespostaInvalida(f"Escreva o prazo em dias, de 1 a {PRAZO_MAXIMO}.")
        dias = int(valor)
    elif escolha.isdigit() and int(escolha) in dict(PRAZOS):
        dias = int(escolha)
    else:
        raise RespostaInvalida("Escolha quanto tempo o fornecedor leva para entregar.")
    respostas["prazo"] = dias
    respostas.pop("prazo_nao_sabe", None)
    if not (usuario and usuario.has_perm("fornecedores.change_fornecedor")):
        respostas["prazo_na_ficha"] = False
        return ("O prazo vale para esta compra. Gravar na ficha do fornecedor é de quem "
                "cuida dos fornecedores.")
    ficha, _ = Fornecedor.objects.get_or_create(nome=compra.fornecedor)
    antes = {"prazo_dias": ficha.prazo_dias}
    if ficha.prazo_dias != dias:
        ficha.prazo_dias = dias
        ficha.atualizado_por = usuario
        ficha.save(update_fields=["prazo_dias", "atualizado_por", "atualizado_em"])
        registrar("fornecedor.prazo_alterado", usuario=usuario, recurso=ficha,
                  recurso_rotulo=ficha.nome, antes=antes, depois={"prazo_dias": dias},
                  motivo="informado na compra guiada")
    respostas["prazo_na_ficha"] = True
    return f"Prazo de {dias} dias gravado na ficha do fornecedor: vale também para a lista de compra."


def _salvar_encomendas(compra, dados, importacao):
    respostas = compra.respostas
    acao = dados.get("acao") or "continuar"
    encomendas = dict(respostas.get("encomendas") or {})
    if acao == "adicionar":
        codigo = (dados.get("codigo") or "").strip()[:60]
        unidades = numero(dados.get("unidades"))
        if not codigo or not importacao.itens.filter(codigo=codigo).exists():
            raise RespostaInvalida("Produto não encontrado na última importação.")
        if not unidades:
            raise RespostaInvalida("Escreva quantas unidades o cliente encomendou.")
        atual = _resolver(encomendas.get(codigo), ZERO) or ZERO
        encomendas[codigo] = _para_texto(atual + unidades)
        respostas["encomendas"] = encomendas
        return "Encomenda posta no pedido."
    if acao == "tirar":
        encomendas.pop((dados.get("codigo") or "").strip(), None)
        respostas["encomendas"] = encomendas
        return "Encomenda tirada do pedido."
    # Continuar: as sugestões da equipe marcadas, com a quantidade de cada uma.
    equipe = {}
    for chave in dados.getlist("equipe"):
        if not str(chave).isdigit():
            continue
        unidades = numero(dados.get(f"equipe-{chave}"))
        if unidades:
            equipe[str(chave)] = _para_texto(unidades)
    respostas["equipe"] = equipe
    return ""


def _salvar_conferencia(compra, dados, importacao):
    """As quantidades mudadas na conferência e o recado ao fornecedor.

    Só o campo que a pessoa MEXEU vira decisão: a tela manda junto o número que mostrou
    (`era-<código>`), e o que voltou igual continua seguindo a conta. Sem isso, salvar a
    conferência congelaria todas as linhas no número do momento.
    """
    respostas = compra.respostas
    proposta = montar(compra, importacao)
    quantidades = dict(respostas.get("quantidades") or {})
    encomendas = dict(respostas.get("encomendas") or {})
    outros = dict(respostas.get("outros") or {})
    for linha in proposta.linhas:
        campo = f"q-{linha.codigo}"
        if campo not in dados:
            continue
        # Campo apagado é zero: é o que a tela mostra na hora (total R$ 0,00), e é o
        # que a pessoa quis ao apagar o número.
        bruto = (dados.get(campo) or "").strip()
        novo = ZERO if not bruto else numero(bruto)
        era = numero(dados.get(f"era-{linha.codigo}"))
        if novo is None or novo == era:
            continue
        if novo < linha.encomenda:
            # Menos do que o cliente encomendou: a encomenda diminui junto.
            if linha.codigo in encomendas:
                encomendas[linha.codigo] = _para_texto(novo)
            reposicao = ZERO
        else:
            reposicao = novo - linha.encomenda
        if linha.a_mao:
            # Posto à mão e zerado: volta para a lista dos outros, de onde veio.
            if reposicao > ZERO:
                outros[linha.codigo] = _para_texto(reposicao)
            else:
                outros.pop(linha.codigo, None)
            quantidades.pop(linha.codigo, None)
            continue
        outros.pop(linha.codigo, None)
        quantidades[linha.codigo] = "0" if reposicao <= ZERO else _para_texto(reposicao)
    # Os outros produtos do fornecedor (1.47.0): só o que ganhou número entra na compra.
    for linha in os_demais(proposta, importacao):
        if linha.a_mao:
            continue  # já tratada acima, como linha da compra
        bruto = (dados.get(f"q-{linha.codigo}") or "").strip()
        novo = numero(bruto) if bruto else None
        if novo is not None and novo > ZERO:
            outros[linha.codigo] = _para_texto(novo)
            # A decisão mais nova é esta: a resposta de quando ele era da conta sai.
            quantidades.pop(linha.codigo, None)
    respostas["quantidades"] = quantidades
    respostas["outros"] = outros
    respostas["encomendas"] = {codigo: valor for codigo, valor in encomendas.items()
                               if (_resolver(valor, ZERO) or ZERO) > ZERO}
    respostas["recado"] = (dados.get("recado") or "").strip()[:300]


def _tirar_os_que_duram_demais(compra, importacao):
    """Zera, como decisão da pessoa, as linhas que durariam mais de um ano."""
    longe = montar(compra, importacao).longe
    if not longe:
        return ""
    quantidades = dict(compra.respostas.get("quantidades") or {})
    for linha in longe:
        quantidades[linha.codigo] = "0"
    compra.respostas["quantidades"] = quantidades
    valor = sum((linha.valor_do_pedido for linha in longe), ZERO)
    if len(longe) == 1:
        return f"Saiu do pedido 1 produto que durava mais de um ano ({reais(valor)})."
    return f"Saíram do pedido {len(longe)} produtos que duravam mais de um ano ({reais(valor)})."


# --------------------------------------------------------------------------- encomendas


def achar_produtos(importacao, termo, fornecedor):
    """Produtos para encomenda: primeiro os deste fornecedor, depois os outros."""
    termo = (termo or "").strip()[:60]
    if importacao is None or len(termo) < 2:
        return []
    consulta = importacao.itens.filter(procura.filtro(termo, "descricao")
                                       | Q(codigo__istartswith=termo)
                                       | Q(codigo_barras__istartswith=termo))
    consulta = consulta.annotate(deste=Count("id", filter=Q(fornecedor=fornecedor)))
    return list(procura.por_relevancia(consulta, termo, "descricao", "codigo",
                                       desempate=("-deste", "-vendas_12m", "descricao"))
                [:QUANTOS_ACHADOS])


def sugestoes_da_equipe(compra, importacao):
    """O que a equipe pediu e ainda não foi comprado, deste fornecedor."""
    abertas = SugestaoDeCompra.objects.filter(
        situacao__in=(SugestaoDeCompra.Situacao.ABERTA, SugestaoDeCompra.Situacao.COMPRAR))
    codigos = importacao.itens.filter(fornecedor=compra.fornecedor).values("codigo")
    return list(abertas.filter(Q(fornecedor__iexact=compra.fornecedor) | Q(codigo__in=codigos))
                .select_related("criada_por").order_by("-criada_em")[:20])


# --------------------------------------------------------------------------- o pedido


def resumo(compra, proposta):
    """As decisões numa frase, para a lista das compras guiadas já feitas."""
    respostas = compra.respostas or {}
    partes = [f"próxima compra em {proposta.proxima_compra} dias",
              f"prazo de {proposta.prazo_dias} dias"
              + (" (assumido)" if proposta.prazo_assumido else ""),
              f"venda de base: {dict(MEDIAS).get(proposta.media, '').lower()}"]
    escolhidos = [tipo.grupo for tipo in proposta.tipos if tipo.escolhido]
    if escolhidos and len(escolhidos) < len(proposta.tipos):
        partes.append("tipos: " + ", ".join(escolhidos))
    if proposta.entra != ENTRA_PADRAO:
        partes.append(dict(ENTRA)[proposta.entra].lower())
    if proposta.orcamento is not None:
        partes.append(f"orçamento até {reais(proposta.orcamento)}")
    if proposta.decididas:
        partes.append(f"{proposta.decididas} quantidade{'s' if proposta.decididas != 1 else ''}"
                      " escolhida" + ("s" if proposta.decididas != 1 else "") + " à mão")
    if proposta.encomendas:
        partes.append(f"{len(proposta.encomendas)} encomenda"
                      f"{'s' if len(proposta.encomendas) != 1 else ''}")
    if respostas.get("recado"):
        partes.append("com recado ao fornecedor")
    texto = "; ".join(partes)
    return (texto[0].upper() + texto[1:])[:500] if texto else ""


@transaction.atomic
def gerar_pedido(compra, proposta, usuario, *, emitido_por="", empresa=None):
    """Grava o pedido do fornecedor, com a folha anexada, e fecha a compra guiada.

    É o mesmo registro da lista de compra e da tela de Pedidos
    (`apps/pedidos/servicos.registrar_pedido`): a Líder de loja continua precisando da
    aprovação da gerência, e gerar duas vezes o mesmo pedido no mesmo dia reaproveita o
    primeiro. As sugestões da equipe que entraram ganham a resposta, se quem gera pode
    responder a elas. Devolve o pedido, ou None quando a compra já tinha virado pedido.
    """
    from apps.pedidos import folha as folha_guardada, servicos as pedidos  # noqa: PLC0415

    from . import pedido as folha_do_pedido  # noqa: PLC0415
    from .models import DadosDaEmpresa  # noqa: PLC0415

    # Dois cliques em "Gerar o pedido" chegam como dois pedidos ao mesmo tempo. A linha da
    # compra fica presa até o fim desta transação: o segundo espera, acha a compra já
    # concluída e não grava outro pedido.
    travada = CompraGuiada.objects.select_for_update().get(pk=compra.pk)
    if travada.situacao != CompraGuiada.Situacao.ANDAMENTO:
        return None

    bloco = proposta.bloco()
    if not bloco.itens:
        raise RespostaInvalida("Não há o que pedir: todas as quantidades estão em zero.")
    recado = (compra.respostas or {}).get("recado", "")
    empresa = empresa or DadosDaEmpresa.atual()
    try:
        registro = pedidos.registrar_pedido(usuario, bloco, data_corte=proposta.data_corte,
                                            observacao=recado)
    except pedidos.NaoDeuCerto as erro:
        raise RespostaInvalida(str(erro)) from None
    aviso = folha_guardada.AVISO_SEM_APROVACAO if registro.esperando_aprovacao else ""
    folha = folha_do_pedido.montar([bloco], empresa, data_corte=proposta.data_corte,
                                   emitido_por=emitido_por, observacao=recado, aviso=aviso)
    nome = folha_do_pedido.nome_do_arquivo([bloco], proposta.data_corte)
    if aviso:
        nome = folha_guardada.com_o_aviso_no_nome(nome)
    pedidos.guardar_a_folha(usuario, registro, folha, nome)

    _responder_a_equipe(compra, registro, usuario)

    compra.situacao = CompraGuiada.Situacao.CONCLUIDA
    compra.concluida_em = timezone.now()
    compra.data_corte = proposta.data_corte
    compra.pedido_numero = registro.numero
    compra.valor = proposta.total
    compra.resumo = resumo(compra, proposta)
    compra.save()
    registrar("compras.compra_guiada_concluida", usuario=usuario, recurso=compra,
              recurso_rotulo=f"pedido {registro.numero} · {compra.fornecedor}"[:200],
              depois={"pedido": registro.numero, "valor": str(proposta.total),
                      "itens": len(bloco.itens), "resumo": compra.resumo,
                      "respostas": {chave: valor for chave, valor in (compra.respostas or {}).items()
                                    if chave != "respondidos"}})
    return registro


def _responder_a_equipe(compra, registro, usuario):
    equipe = (compra.respostas or {}).get("equipe") or {}
    if not equipe or not (usuario and usuario.has_perm("compras.responder_sugestao")):
        return
    from . import equipe as servico_da_equipe  # noqa: PLC0415

    situacao = (SugestaoDeCompra.Situacao.COMPRAR if registro.esperando_aprovacao
                else SugestaoDeCompra.Situacao.COMPRADA)
    for sugestao in SugestaoDeCompra.objects.filter(pk__in=[int(c) for c in equipe if str(c).isdigit()]):
        if sugestao.situacao == situacao:
            continue
        servico_da_equipe.responder(
            sugestao, situacao=situacao, usuario=usuario,
            resposta=f"Entrou no pedido {registro.numero} a {compra.fornecedor} (compra guiada).")


def em_andamento(usuario):
    return list(CompraGuiada.objects.filter(criada_por=usuario,
                                            situacao=CompraGuiada.Situacao.ANDAMENTO)[:5])


def ultimas_concluidas(quantas=6):
    return list(CompraGuiada.objects.filter(situacao=CompraGuiada.Situacao.CONCLUIDA)
                .select_related("criada_por").order_by("-concluida_em")[:quantas])


def anteriores_do_fornecedor(nome, menos=None, quantas=3):
    """As compras guiadas já feitas deste fornecedor: o que a pessoa de antes decidiu."""
    consulta = CompraGuiada.objects.filter(fornecedor=nome,
                                           situacao=CompraGuiada.Situacao.CONCLUIDA)
    if menos is not None:
        consulta = consulta.exclude(pk=menos.pk)
    return list(consulta.select_related("criada_por").order_by("-concluida_em")[:quantas])
