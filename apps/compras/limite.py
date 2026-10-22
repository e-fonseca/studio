"""Antes de comprar: a conta que diz quanto a loja pode comprar e o que já comprou demais.

A tela do painel mostra o estrago depois de feito. Esta responde a pergunta na hora
da compra, que é quando dá para evitar: quanto cabe este mês, o que a compra do ano
passado virou e se vale comprar este produto agora.

A regra do teto é uma só e qualquer pessoa refaz na calculadora: a loja vendeu, em 12
meses, tanto em mercadoria avaliada pelo custo; dividido por 12, é quanto sai da
prateleira num mês médio. Comprar acima disso, mês após mês, só engorda o estoque. Não é
proibição: é o ponto em que a compra passa a virar dinheiro parado.

Nada aqui depende de digitação. Tudo sai da última importação do SET.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.db.models import DecimalField, F, Sum

from apps.compras.calculos import Item, Parametros, Situacao, calcular
from apps.fornecedores import servicos as fornecedores

ZERO = Decimal("0")
CENTAVO = Decimal("0.01")
MESES_DA_JANELA = 12
QUANTOS_FORNECEDORES = 10
QUANTOS_RESULTADOS = 8
# Acima de 80% do teto o mês já pede atenção; acima de 100%, a compra passou do ponto.
ATENCAO = 80


def _reais(valor):
    return (valor or ZERO).quantize(CENTAVO)


@dataclass
class Teto:
    """Quanto cabe de compra no mês e quanto já foi comprado."""

    mensal: Decimal = ZERO
    comprado: Decimal = ZERO
    sobra: Decimal = ZERO  # positivo quando ainda cabe, negativo quando a compra passou
    usado: int = 0  # porcentagem do teto já consumida
    largura: int = 0  # a mesma porcentagem, limitada a 100, para a barra da tela
    nivel: str = "bom"  # bom, atencao, ruim
    rotulo_mes: str = ""
    dia_do_corte: object = None
    custo_vendido_12m: Decimal = ZERO
    comprometido: Decimal = ZERO  # o que já está marcado para sair do caixa

    @property
    def estourou(self):
        return self.comprado > self.mensal

    @property
    def diferenca(self):
        """O quanto falta ou o quanto passou, sempre positivo: o sinal quem dá é a frase da tela."""
        return abs(self.sobra)


@dataclass
class CompraDoFornecedor:
    """O que a loja comprou de um fornecedor em 12 meses e o que aquilo virou."""

    nome: str
    comprado: Decimal = ZERO
    vendido: Decimal = ZERO  # do que existe hoje desse fornecedor, quanto saiu, avaliado pelo custo
    na_prateleira: Decimal = ZERO
    sem_giro: Decimal = ZERO  # parte da prateleira que não vendeu nenhuma unidade em 12 meses
    itens: int = 0
    itens_sem_giro: int = 0
    reputacao: object = None
    relacao: str = ""
    relacao_rotulo: str = ""
    largura: int = 0

    @property
    def aproveitamento(self):
        """De cada real comprado, quanto já saiu em venda.

        Só aparece quando saiu menos do que entrou, que é o caso que interessa. Vendido
        maior que comprado é comum (sai o que foi comprado em anos anteriores) e a conta
        viraria sempre 100%, o que não diria nada.
        """
        if self.comprado <= ZERO or self.vendido >= self.comprado:
            return None
        return int(self.vendido * 100 / self.comprado)

    @property
    def sem_compra_no_periodo(self):
        """Tem prateleira desse fornecedor, mas nada entrou nos 12 meses."""
        return self.comprado <= ZERO


MESES_NOME = ["", "janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
              "agosto", "setembro", "outubro", "novembro", "dezembro"]

# O veredito que aparece em letra grande, por situação do cálculo de reposição.
#
# Cada frase aqui tem que dizer a conta que ESTA tela faz, que é sobre os doze meses:
# `conferir` monta o item com `vendas_12m` e `dias_abertos_12m`. A frase da ruptura dizia
# "vendeu nos últimos 90 dias", que é a régua da tela de Sugestões e de nenhum número
# daqui: produto que vendeu duas unidades em novembro e está zerado desde então recebia
# "vendeu nos últimos 90 dias", e é esta a única frase que a pessoa lê antes de comprar.
VEREDITOS = {
    Situacao.RUPTURA: ("pode", "Pode comprar", "Está zerado e vendeu nos últimos 12 meses."),
    Situacao.COMPRAR: ("pode", "Pode comprar", "O estoque chegou no ponto de repor."),
    Situacao.SAUDAVEL: ("espere", "Não precisa agora", "O que está na prateleira ainda cobre a venda."),
    Situacao.EXCESSO: ("nao", "Não compre", "Já tem mais do que a venda do próprio produto consome."),
    Situacao.SEM_GIRO: ("nao", "Não compre", "Não vendeu nenhuma unidade em 12 meses."),
    # demanda zero e prateleira vazia: o produto não vendeu nada no ano e não tem saldo.
    # Isso não é falta de dado, é resposta: só repor por pedido de cliente.
    Situacao.SEM_DADOS: ("nao", "Não compre por conta própria",
                         "Não vendeu nenhuma unidade em 12 meses e está zerado. Só repor se for pedido de cliente."),
}


@dataclass
class Veredito:
    """A resposta para um produto, do jeito que ela aparece na tela."""

    codigo: str
    descricao: str
    grupo: str
    fornecedor: str
    resposta: str  # pode, espere, nao
    titulo: str
    motivo: str
    estoque: Decimal = ZERO
    cobertura: str = ""
    vendas_12m: Decimal = ZERO
    compras_12m: Decimal = ZERO
    sugerida: Decimal = ZERO
    custo_compra: Decimal = None
    valor_parado: Decimal = ZERO
    ultima_compra: object = None
    ultima_venda: object = None

    @property
    def estoque_negativo(self):
        """O SET tem 1.456 produtos com saldo abaixo de zero; ali o número não vale sozinho."""
        return (self.estoque or ZERO) < ZERO


@dataclass
class AntesDeComprar:
    importacao: object
    teto: Teto = field(default_factory=Teto)
    fornecedores: list = field(default_factory=list)
    total_comprado: Decimal = ZERO  # só os produtos com fornecedor, que é o que a tabela mostra
    comprado_12m: Decimal = ZERO  # todos os produtos, para comparar com o que saiu
    total_prateleira: Decimal = ZERO
    total_sem_giro: Decimal = ZERO

    @property
    def comprou_mais_do_que_saiu(self):
        return self.comprado_12m > self.teto.custo_vendido_12m

    @property
    def diferenca_do_ano(self):
        """A distância entre o que entrou e o que saiu em 12 meses, sempre positiva."""
        return abs(self.comprado_12m - self.teto.custo_vendido_12m)


def _valor_do_mes(detalhe, chave, ano, mes):
    for linha in detalhe.get(chave, []):
        if linha[0] == ano and linha[1] == mes:
            return Decimal(str(linha[2])).quantize(CENTAVO)
    return ZERO


def teto_de(importacao, hoje=None, resumo_caixa=None) -> Teto:
    """Só o teto de compra do mês, sem montar a tela "Antes de comprar" inteira.

    A lista de compra e o pedido ao fornecedor precisam DISTO e de nada mais daquela
    tela. As duas chamavam `montar`, que traz os onze mil produtos do SET para a memória
    e monta a tabela de todos os fornecedores — para jogar tudo fora menos este objeto.
    Era uma varredura de onze mil linhas em Python a cada abertura da tela mais pesada do
    sistema, e duas quando a pessoa fechava o pedido. Aqui a soma sai do banco.

    A soma é a mesma do laço de `montar`: produto sem custo ou sem venda entra como zero
    nos dois lugares — no banco porque multiplicação com nulo é nula e não entra na soma.
    """
    if importacao is None:
        return Teto()
    corte = importacao.data_corte or hoje or date.today()
    custo_vendido = importacao.itens.aggregate(
        total=Sum(F("vendas_12m") * F("custo"),
                  output_field=DecimalField(max_digits=20, decimal_places=4)),
    )["total"] or ZERO
    return _montar_teto(importacao.detalhe or {}, corte, custo_vendido, resumo_caixa)


def montar(importacao, hoje=None, resumo_caixa=None) -> AntesDeComprar:
    """Monta a tela inteira a partir de uma importação concluída."""
    dados = AntesDeComprar(importacao=importacao)
    if importacao is None:
        return dados

    produtos = list(importacao.itens.all())
    corte = importacao.data_corte or hoje or date.today()
    detalhe = importacao.detalhe or {}

    custo_vendido = ZERO
    comprado = ZERO
    por_fornecedor = {}
    for produto in produtos:
        custo = produto.custo or ZERO
        vendido = (produto.vendas_12m or ZERO) * custo
        custo_vendido += vendido
        comprado += produto.valor_compras_12m or ZERO
        nome = (produto.fornecedor or "").strip()
        if not nome:
            continue
        linha = por_fornecedor.setdefault(nome, CompraDoFornecedor(nome=nome))
        linha.comprado += produto.valor_compras_12m or ZERO
        linha.vendido += vendido
        parado = max(produto.estoque or ZERO, ZERO) * custo
        linha.na_prateleira += parado
        linha.itens += 1
        if (produto.vendas_12m or ZERO) <= ZERO:
            linha.sem_giro += parado
            linha.itens_sem_giro += 1

    dados.teto = _montar_teto(detalhe, corte, custo_vendido, resumo_caixa)
    dados.comprado_12m = _reais(comprado)

    cadastro = fornecedores.cadastrados()
    lista = [f for f in por_fornecedor.values() if f.comprado > ZERO or f.na_prateleira > ZERO]
    for linha in lista:
        linha.comprado = _reais(linha.comprado)
        linha.vendido = _reais(linha.vendido)
        linha.na_prateleira = _reais(linha.na_prateleira)
        linha.sem_giro = _reais(linha.sem_giro)
        ficha = cadastro.get(linha.nome)
        if ficha is not None:
            linha.reputacao = ficha.reputacao
            linha.relacao = ficha.relacao
            linha.relacao_rotulo = ficha.get_relacao_display() if ficha.relacao else ""

    dados.total_comprado = _reais(sum((f.comprado for f in lista), ZERO))
    dados.total_prateleira = _reais(sum((f.na_prateleira for f in lista), ZERO))
    dados.total_sem_giro = _reais(sum((f.sem_giro for f in lista), ZERO))

    # Ordem: o fornecedor com mais dinheiro parado primeiro, que é o que precisa de conversa.
    lista.sort(key=lambda f: (-(f.sem_giro or ZERO), -(f.na_prateleira or ZERO), f.nome))
    maior = max((f.na_prateleira for f in lista), default=ZERO)
    for linha in lista:
        linha.largura = 0 if maior <= ZERO else max(1, int(linha.na_prateleira * 100 / maior))
    dados.fornecedores = lista[:QUANTOS_FORNECEDORES]
    return dados


def _montar_teto(detalhe, corte, custo_vendido, resumo_caixa):
    teto = Teto()
    teto.custo_vendido_12m = _reais(custo_vendido)
    teto.mensal = _reais(custo_vendido / MESES_DA_JANELA)
    teto.comprado = _valor_do_mes(detalhe, "compras_mes", corte.year, corte.month)
    teto.sobra = _reais(teto.mensal - teto.comprado)
    teto.rotulo_mes = MESES_NOME[corte.month]
    teto.dia_do_corte = corte
    if teto.mensal > ZERO:
        teto.usado = int(teto.comprado * 100 / teto.mensal)
    teto.largura = min(teto.usado, 100)
    teto.nivel = "ruim" if teto.usado > 100 else ("atencao" if teto.usado >= ATENCAO else "bom")
    if resumo_caixa is not None:
        teto.comprometido = _reais(resumo_caixa.compromisso_total)
    return teto


def quantos_casam(importacao, procurado):
    """Quantos produtos casam com a busca. A tela mostra poucos e avisa quando há mais."""
    procurado = (procurado or "").strip()
    if importacao is None or not procurado:
        return 0
    return importacao.itens.filter(descricao__icontains=procurado).count()


def conferir(importacao, procurado, hoje=None, quantos=QUANTOS_RESULTADOS):
    """Responde "posso comprar este produto?" para o que casar com o texto procurado."""
    procurado = (procurado or "").strip()
    if importacao is None or not procurado:
        return []

    itens = importacao.itens.filter(descricao__icontains=procurado)
    por_codigo = importacao.itens.filter(codigo__iexact=procurado)
    produtos = list(por_codigo) + [p for p in itens[:quantos * 2] if p.codigo.lower() != procurado.lower()]

    parametros = Parametros()
    dias = importacao.dias_abertos_12m or 1
    prazos = fornecedores.prazos_informados()
    vereditos = []
    for produto in produtos[:quantos]:
        informado = prazos.get((produto.fornecedor or "").strip())
        resultado = calcular(
            Item(
                sku=produto.codigo,
                descricao=produto.descricao,
                estoque_utilizavel=produto.estoque,
                vendas_liquidas=produto.vendas_12m,
                dias_janela=dias,
                prazo_reposicao_dias=(informado if informado is not None else produto.prazo_reposicao_dias),
                custo_unitario=produto.custo,
                reservas_nao_deduzidas=produto.reservado or ZERO,
                comprado_na_janela=produto.compras_12m,
                recebimentos_pendentes=produto.pedido_em_aberto or ZERO,
            ),
            parametros,
            importacao.data_corte,
            hoje,
        )
        resposta, titulo, motivo = VEREDITOS.get(
            resultado.situacao, ("espere", "Sem dados para afirmar", resultado.motivo))
        vereditos.append(Veredito(
            codigo=produto.codigo,
            descricao=produto.descricao,
            grupo=produto.grupo,
            fornecedor=produto.fornecedor,
            resposta=resposta,
            titulo=titulo,
            motivo=motivo,
            estoque=produto.estoque,
            cobertura=resultado.cobertura_texto,
            vendas_12m=produto.vendas_12m,
            compras_12m=produto.compras_12m,
            sugerida=resultado.compra_sugerida,
            custo_compra=resultado.custo_compra,
            valor_parado=_reais(resultado.valor_excesso or ZERO),
            ultima_compra=produto.ultima_compra,
            ultima_venda=produto.ultima_venda,
        ))
    # Primeiro o que não se deve comprar: é por isso que a tela existe.
    ordem = {"nao": 0, "pode": 1, "espere": 2}
    vereditos.sort(key=lambda v: (ordem.get(v.resposta, 3), v.descricao))
    return vereditos
