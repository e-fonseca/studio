"""O dinheiro vivo do caixa: o que deveria estar na gaveta no fim do turno.

Pedido do Edson em 13/10/2026: "contabilizar caixa em dinheiro, inicio, o que saiu,
sangrias e saldo".

Por que não basta o saldo que o SET já grava
--------------------------------------------
O `SALDOFINAL` do SET, e a conta que a tela de Caixa já faz, somam **tudo** o que o
turno recebeu: dinheiro, PIX e os dois cartões. Esse número responde "quanto este turno
movimentou", que é uma pergunta boa, mas não responde a que interessa na hora de fechar
a gaveta: **quanto papel deveria estar lá dentro**. PIX e cartão não entram na gaveta.

A conta daqui é essa outra:

    dinheiro na gaveta = saldo inicial
                       + o que foi recebido EM DINHEIRO
                       + entradas de dinheiro
                       − sangrias
                       − pagamentos feitos pelo caixa

Entrada, sangria e pagamento não têm forma de pagamento gravada no SET (conferido no
backup de 20/09/2026: o campo vem vazio nos três tipos), e é assim mesmo — sangria é
dinheiro saindo da gaveta, entrada é dinheiro entrando e pagamento pelo caixa sai da
gaveta. Quem tem forma de pagamento é só o recebimento de venda.

A forma que é dinheiro
----------------------
No SET da Cabana o dinheiro aparece como **AVISTA**, ao lado de PIX, CARTAO DEBITO e
CARTAO CREDITO. A lista de formas é do SET e muda sem avisar, então aqui ela não é
adivinhada: cada forma cai em uma de três caixas — é dinheiro, não é dinheiro, ou **não
sei**. Forma que o sistema não conhece nunca entra na conta calada; ela aparece na tela
dizendo que não foi classificada, para alguém olhar. Chutar que uma forma nova é
dinheiro faria a gaveta "faltar" sem explicação, que é o pior que esta tela poderia
fazer com quem confere caixa.
"""

import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal

ZERO = Decimal("0")

# Dinheiro vivo. "AVISTA" é como o SET da Cabana chama; os outros estão aqui porque são
# os nomes que o mesmo campo costuma receber e custam nada.
EM_DINHEIRO = {"AVISTA", "A VISTA", "DINHEIRO", "ESPECIE", "EM ESPECIE", "VISTA"}

# Não é dinheiro: não entra na gaveta, por mais que entre no caixa.
SEM_DINHEIRO = {
    "PIX", "CARTAO", "CARTAO DEBITO", "CARTAO CREDITO", "CARTAO DE DEBITO",
    "CARTAO DE CREDITO", "DEBITO", "CREDITO", "CHEQUE", "BOLETO", "PRAZO",
    "CREDIARIO", "TRANSFERENCIA", "TED", "DOC", "DEPOSITO", "CONVENIO", "VALE",
}


def _chave(nome):
    """Sem acento, sem espaço sobrando e em maiúsculas, para comparar nome do SET."""
    texto = unicodedata.normalize("NFKD", (nome or "").strip().upper())
    return " ".join("".join(c for c in texto if not unicodedata.combining(c)).split())


def classificar(nome):
    """Devolve 'dinheiro', 'outra' ou 'desconhecida' para uma forma de pagamento."""
    chave = _chave(nome)
    if not chave:
        return "desconhecida"
    if chave in EM_DINHEIRO:
        return "dinheiro"
    if chave in SEM_DINHEIRO:
        return "outra"
    # "CARTAO MASTER", "PIX LOJA": o começo do nome já diz o que é.
    for conhecida in SEM_DINHEIRO:
        if chave.startswith(conhecida + " "):
            return "outra"
    for conhecida in EM_DINHEIRO:
        if chave.startswith(conhecida + " "):
            return "dinheiro"
    return "desconhecida"


@dataclass
class Gaveta:
    """O dinheiro vivo de um turno, ou de um período inteiro."""

    inicio: Decimal = ZERO
    recebido: Decimal = ZERO       # vendas pagas em dinheiro
    entradas: Decimal = ZERO       # dinheiro colocado no caixa
    sangrias: Decimal = ZERO       # dinheiro retirado
    pagamentos: Decimal = ZERO     # contas pagas pela gaveta
    outras_formas: Decimal = ZERO  # PIX e cartão, que não entram na gaveta
    nao_classificado: Decimal = ZERO
    formas_desconhecidas: list = field(default_factory=list)
    turnos: int = 0

    @property
    def entrou(self):
        """Tudo o que engrossou a gaveta, sem contar o saldo de abertura."""
        return self.recebido + self.entradas

    @property
    def saiu(self):
        """O que saiu da gaveta: sangria mais conta paga pelo caixa."""
        return self.sangrias + self.pagamentos

    @property
    def saldo(self):
        """O que deveria estar na gaveta. Pode ser negativo, e aí é erro de lançamento."""
        return self.inicio + self.entrou - self.saiu

    @property
    def tem_duvida(self):
        return bool(self.formas_desconhecidas)

    @property
    def fatia_em_dinheiro(self):
        """Quanto de cada R$ 100 recebidos veio em papel. Serve para dimensionar o risco."""
        total = self.recebido + self.outras_formas
        if not total:
            return ZERO
        return (self.recebido * 100 / total).quantize(Decimal("0.1"))


def do_turno(caixa):
    """A gaveta de um turno só."""
    gaveta = Gaveta(
        inicio=caixa.saldo_inicial or ZERO,
        entradas=caixa.entradas or ZERO,
        sangrias=caixa.sangrias or ZERO,
        pagamentos=caixa.pagamentos or ZERO,
        turnos=1,
    )
    desconhecidas = []
    for nome, valor in (caixa.por_forma or {}).items():
        quanto = Decimal(valor or 0)
        especie = classificar(nome)
        if especie == "dinheiro":
            gaveta.recebido += quanto
        elif especie == "outra":
            gaveta.outras_formas += quanto
        else:
            gaveta.nao_classificado += quanto
            desconhecidas.append(nome or "sem forma")
    gaveta.formas_desconhecidas = sorted(set(desconhecidas))
    return gaveta


@dataclass
class Periodo:
    """O dinheiro vivo de vários turnos.

    Por que isto não é uma `Gaveta` somada
    --------------------------------------
    Somar o saldo de abertura de todos os turnos daria um número sem significado: a
    abertura de um turno é, em tese, o que ficou na gaveta do turno anterior, então
    somá-las conta o mesmo dinheiro muitas vezes.

    Encadear também não serve nesta loja. No backup de 20/09/2026, em **642 dos 949**
    turnos a abertura NÃO é o fecho em dinheiro do turno anterior: a abertura é digitada
    no SET a cada turno, e a gaveta é esvaziada por sangria quase todo dia. Encadeando os
    dois anos e meio o saldo dá negativo, o que não descreve gaveta nenhuma.

    Então o período mostra só o que é inequívoco — **quanto entrou e quanto saiu de
    papel** — e, ao lado, a gaveta do **último turno**, que é o único saldo que existe de
    verdade agora.
    """

    entrou: Decimal = ZERO
    recebido: Decimal = ZERO
    entradas: Decimal = ZERO
    saiu: Decimal = ZERO
    sangrias: Decimal = ZERO
    pagamentos: Decimal = ZERO
    outras_formas: Decimal = ZERO
    nao_classificado: Decimal = ZERO
    formas_desconhecidas: list = field(default_factory=list)
    turnos: int = 0
    ultima: Gaveta = field(default_factory=Gaveta)
    ultimo_turno = None

    @property
    def tem_duvida(self):
        return bool(self.formas_desconhecidas)

    @property
    def sobrou(self):
        """O papel que entrou menos o papel que saiu.

        Perto de zero é o normal de uma loja que faz sangria: o dinheiro vai para o
        cofre ou para o banco. Muito positivo quer dizer dinheiro parado na gaveta.

        Pode dar **negativo**, e isso não é erro: no backup de 20/09/2026 dá
        −R$ 5.815,01 em dois anos e meio. O motivo é o saldo de abertura, que é
        digitado no SET a cada turno e não entra nesta conta — a loja retira por
        sangria dinheiro que já estava na gaveta antes do período começar.
        """
        return self.entrou - self.saiu

    @property
    def saiu_mais_do_que_entrou(self):
        """Para a tela explicar o sinal em vez de mostrar um número negativo calado."""
        return self.sobrou < 0

    @property
    def fatia_em_dinheiro(self):
        """De cada R$ 100 recebidos, quanto veio em papel."""
        total = self.recebido + self.outras_formas
        if not total:
            return ZERO
        return (self.recebido * 100 / total).quantize(Decimal("0.1"))


def do_periodo(caixas):
    """Os números de dinheiro vivo de um período, para o topo da tela."""
    periodo = Periodo()
    desconhecidas = set()
    mais_novo = None
    for caixa in caixas:
        uma = do_turno(caixa)
        periodo.recebido += uma.recebido
        periodo.entradas += uma.entradas
        periodo.sangrias += uma.sangrias
        periodo.pagamentos += uma.pagamentos
        periodo.outras_formas += uma.outras_formas
        periodo.nao_classificado += uma.nao_classificado
        periodo.turnos += 1
        desconhecidas.update(uma.formas_desconhecidas)
        if mais_novo is None or (caixa.aberto_em and caixa.aberto_em > mais_novo.aberto_em):
            mais_novo = caixa
    periodo.entrou = periodo.recebido + periodo.entradas
    periodo.saiu = periodo.sangrias + periodo.pagamentos
    periodo.formas_desconhecidas = sorted(desconhecidas)
    if mais_novo is not None:
        periodo.ultima = do_turno(mais_novo)
        periodo.ultimo_turno = mais_novo
    return periodo
