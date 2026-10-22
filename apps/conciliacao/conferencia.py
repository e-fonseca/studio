"""Confrontar o extrato do banco com as contas que o SET diz que foram pagas.

A pergunta que isto responde é a do Edson: saiu dinheiro da conta — essa saída está
lançada no SET? E o contrário: o SET diz que pagou, o banco confirma?

Como o par é procurado
----------------------
Para cada **saída** do extrato, o sistema procura entre as contas a pagar **já baixadas**
do SET uma que tenha o **mesmo valor** e data de pagamento **perto** da data do banco
(cinco dias para cada lado, porque o SET costuma ser baixado no dia seguinte, e feriado
empurra mais).

Valor igual é condição, não pontuação: duas contas de R$ 1.362,00 e R$ 1.362,01 são
contas diferentes, e aproximar valores num confronto de dinheiro seria inventar.

Entre as candidatas que sobram, ganha a mais perto na data, e o nome do fornecedor
desempata: se a descrição do banco diz "PIX QUITERIA FLOR MILHO" e uma das candidatas é
da QUITÉRIA, é ela. A comparação de nome ignora acento e as palavras que não distinguem
ninguém (PIX, TED, PAGAMENTO, LTDA).

O sistema **não** marca nada sozinho
------------------------------------
Mesmo quando há uma única candidata, quem confirma é a pessoa — com um clique, ou com o
botão que confirma de uma vez todas as linhas que têm uma candidata só. Conciliação
bancária marcada automaticamente é conciliação que ninguém olhou, e o erro aparece
meses depois, quando já não dá para lembrar.

Entradas de dinheiro (crédito) ficam de fora do confronto: elas são venda, cartão e
transferência, e a conta a pagar não tem nada a ver com elas. Aparecem na tela, contadas
à parte, para o extrato continuar batendo com o que o banco mandou.
"""

import unicodedata
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from apps.financeiro.models import Lancamento

from .models import LinhaExtrato

ZERO = Decimal("0")
DIAS_DE_FOLGA = 5

# Palavras que aparecem em quase toda descrição de banco e não identificam ninguém.
PALAVRAS_VAZIAS = {
    "PIX", "TED", "DOC", "TEV", "TRANSFERENCIA", "TRANSF", "PAGAMENTO", "PAGTO", "PAG",
    "ENVIADO", "RECEBIDO", "DEBITO", "CREDITO", "BOLETO", "TITULO", "COBRANCA", "CONTA",
    "LTDA", "ME", "EPP", "EIRELI", "SA", "S", "A", "DE", "DA", "DO", "DOS", "DAS", "E",
    "COMERCIO", "COM", "INDUSTRIA", "IND", "CIA", "EMPRESA", "BANCO", "AUTORIZADO",
}


def _palavras(texto):
    """As palavras que identificam alguém, sem acento e em maiúsculas."""
    sem = unicodedata.normalize("NFKD", texto or "").upper()
    sem = "".join(c for c in sem if not unicodedata.combining(c))
    limpo = "".join(c if c.isalnum() else " " for c in sem)
    return {p for p in limpo.split() if len(p) > 2 and p not in PALAVRAS_VAZIAS}


def parecencia(descricao_do_banco, nome_do_fornecedor):
    """De 0 a 1: quanto o nome do fornecedor aparece na descrição do banco."""
    do_banco = _palavras(descricao_do_banco)
    do_fornecedor = _palavras(nome_do_fornecedor)
    if not do_banco or not do_fornecedor:
        return 0.0
    return len(do_banco & do_fornecedor) / len(do_fornecedor)


@dataclass
class Candidata:
    conta: Lancamento
    distancia_em_dias: int
    parecencia: float = 0.0
    ja_usada: bool = False

    @property
    def nota(self):
        """Quem fica em primeiro. Data perto pesa mais; o nome desempata."""
        return (-self.distancia_em_dias) + self.parecencia * 3 - (10 if self.ja_usada else 0)

    @property
    def rotulo(self):
        """O que vai ficar guardado na linha depois de conferida."""
        partes = [self.conta.descricao or "conta sem descrição"]
        if self.conta.contraparte:
            partes.append(self.conta.contraparte)
        if self.conta.parcela:
            partes.append(f"parcela {self.conta.parcela}")
        return " · ".join(partes)


@dataclass
class Confronto:
    """Uma linha do extrato e as contas do SET que podem ser ela."""

    linha: LinhaExtrato
    candidatas: list = field(default_factory=list)

    @property
    def entrada(self):
        return not self.linha.saiu

    @property
    def situacao(self):
        """O que a tela mostra: já conferida, uma só, várias, nenhuma, ou entrada."""
        if self.linha.situacao == LinhaExtrato.Situacao.CONFERIDA:
            return "conferida"
        if self.linha.situacao == LinhaExtrato.Situacao.SEM_CONTA:
            return "sem_conta"
        if self.entrada:
            return "entrada"
        if len(self.candidatas) == 1:
            return "uma"
        if self.candidatas:
            return "varias"
        return "nenhuma"

    @property
    def unica(self):
        return self.candidatas[0] if len(self.candidatas) == 1 else None


def _pagas(importacao):
    """As contas a pagar já baixadas no SET, que são as que o banco pode confirmar."""
    if importacao is None:
        return Lancamento.objects.none()
    return Lancamento.objects.filter(
        importacao=importacao, tipo=Lancamento.Tipo.PAGAR, pagamento__isnull=False
    )


def candidatas_para(linha, contas, usados=(), dias=DIAS_DE_FOLGA):
    """As contas que podem ser esta linha do banco, da mais provável para a menos."""
    if not linha.saiu:
        return []
    procurado = linha.valor_absoluto
    achadas = []
    for conta in contas:
        valor = conta.valor_pago or conta.valor or ZERO
        if valor != procurado:
            continue
        if not conta.pagamento:
            continue
        distancia = abs((conta.pagamento - linha.data).days)
        if distancia > dias:
            continue
        achadas.append(Candidata(
            conta=conta, distancia_em_dias=distancia,
            parecencia=parecencia(linha.descricao, conta.contraparte),
            ja_usada=conta.id_set in usados,
        ))
    return sorted(achadas, key=lambda c: c.nota, reverse=True)


def confrontar(extrato, importacao, dias=DIAS_DE_FOLGA):
    """Todas as linhas do extrato, cada uma com as contas que podem ser ela."""
    linhas = list(extrato.linhas.all())
    if not linhas:
        return []
    primeira = min(l.data for l in linhas)
    ultima = max(l.data for l in linhas)
    # Uma consulta só para o extrato inteiro: o confronto roda a cada abertura da tela.
    contas = list(_pagas(importacao).filter(
        pagamento__gte=primeira - timedelta(days=dias),
        pagamento__lte=ultima + timedelta(days=dias),
    ))
    # Conta já amarrada a outra linha não pode ser oferecida como se estivesse livre.
    usados = set(
        LinhaExtrato.objects.filter(situacao=LinhaExtrato.Situacao.CONFERIDA)
        .exclude(lancamento_id_set=0)
        .values_list("lancamento_id_set", flat=True)
    )
    confrontos = []
    for linha in linhas:
        candidatas = []
        if linha.situacao == LinhaExtrato.Situacao.PENDENTE:
            candidatas = candidatas_para(linha, contas, usados=usados, dias=dias)
        confrontos.append(Confronto(linha=linha, candidatas=candidatas))
    return confrontos


@dataclass
class Resumo:
    """Os números do topo da tela do extrato."""

    linhas: int = 0
    saidas: int = 0
    entradas: int = 0
    conferidas: int = 0
    sem_conta: int = 0
    com_uma: int = 0
    com_varias: int = 0
    sem_par: int = 0
    valor_saidas: Decimal = ZERO
    valor_entradas: Decimal = ZERO
    valor_conferido: Decimal = ZERO

    @property
    def pendentes(self):
        return self.com_uma + self.com_varias + self.sem_par

    @property
    def valor_a_conferir(self):
        return self.valor_saidas - self.valor_conferido

    @property
    def tudo_conferido(self):
        return self.saidas > 0 and self.pendentes == 0


def resumir(confrontos):
    resumo = Resumo()
    for confronto in confrontos:
        linha = confronto.linha
        resumo.linhas += 1
        if confronto.entrada:
            resumo.entradas += 1
            resumo.valor_entradas += linha.valor
        else:
            resumo.saidas += 1
            resumo.valor_saidas += linha.valor_absoluto
        situacao = confronto.situacao
        if situacao == "conferida":
            resumo.conferidas += 1
            if linha.saiu:
                resumo.valor_conferido += linha.valor_absoluto
        elif situacao == "sem_conta":
            resumo.sem_conta += 1
        elif situacao == "uma":
            resumo.com_uma += 1
        elif situacao == "varias":
            resumo.com_varias += 1
        elif situacao == "nenhuma":
            resumo.sem_par += 1
    return resumo
