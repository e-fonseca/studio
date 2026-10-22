"""O ajuste entrou no SET? A pergunta se responde na importação seguinte.

Pedido do Edson em 22/10/2026: *"fazer relatório comparando o que o set sistema
apresenta e o que o nosso sistema fez de leitura do inventario. precisamos ajustar essa
informação para que o set sistema apresenta informações mais precisas, através do
backup"*.

O que este sistema pode e o que não pode
----------------------------------------
Ele **não escreve no SET**, e isso não é limitação de implementação: é regra do próprio
Edson, de 05/10/2026 — *"o sistema vigente set sistemas, nao permite nenhuma
integração"* — e a razão pela qual a leitura acontece sobre uma CÓPIA do backup do dia,
nunca sobre o banco em uso. As tabelas de conferência de estoque do SET
(`CONFERENCIA_ESTOQUE`) existem e estão vazias: a loja nunca usou aquela tela.

Então o acerto do saldo é digitado no SET por uma pessoa, uma linha por vez, porque é lá
que o estoque vale. O que o sistema faz é as duas pontas disso:

1. entrega a lista do que está diferente, ordenada pelo dinheiro, em papel e planilha;
2. **confere, sozinho, se o que foi digitado entrou** — e é aqui que "através do backup"
   fecha o laço. A importação roda três vezes por dia sobre o backup novo; na primeira
   que acontecer depois da digitação, o saldo do SET ou passou a ser o contado, ou não.
   Ninguém precisa conferir à mão nem lembrar de voltar na lista.

Por que não basta comparar com o saldo antigo
---------------------------------------------
Entre a contagem e a importação seguinte a loja vendeu e recebeu mercadoria. Então um
saldo diferente do contado não quer dizer que o ajuste não foi digitado — pode ter sido
digitado e o produto ter vendido duas unidades depois. São três respostas, não duas:

* **entrou** — o saldo do SET é exatamente o contado;
* **não entrou** — o saldo do SET continua sendo o mesmo de antes da contagem;
* **mexeu** — mudou, mas não para o contado. Houve venda, compra ou ajuste parcial, e
  isso é para alguém olhar, não para o sistema afirmar.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from apps.importacao import servicos as importacao_servicos

ZERO = Decimal("0")

ENTROU = "entrou"
NAO_ENTROU = "nao_entrou"
MEXEU = "mexeu"

RECADOS = {
    ENTROU: "Ajuste entrou no SET",
    NAO_ENTROU: "Ainda não entrou no SET",
    MEXEU: "Mudou, mas não para o contado",
}


@dataclass
class LinhaConferida:
    """Uma divergência da contagem, com o que o SET diz hoje."""

    item: object | None = None
    saldo_de_hoje: Decimal | None = None
    estado: str = NAO_ENTROU

    @property
    def recado(self):
        return RECADOS[self.estado]

    @property
    def entrou(self):
        return self.estado == ENTROU

    @property
    def diferenca_de_hoje(self):
        """O que ainda falta ajustar: contado menos o saldo de hoje no SET."""
        if self.saldo_de_hoje is None:
            return None
        return (self.item.quantidade or ZERO) - self.saldo_de_hoje


@dataclass
class Conferencia:
    """O resultado da conferência inteira."""

    importacao: object | None = None
    linhas: list = field(default_factory=list)
    entraram: int = 0
    nao_entraram: int = 0
    mexeram: int = 0
    sumiram: int = 0
    disponivel: bool = False

    @property
    def total(self):
        return len(self.linhas)

    @property
    def falta_ajustar(self):
        return self.nao_entraram + self.mexeram

    @property
    def tudo_entrou(self):
        return self.disponivel and self.total > 0 and self.falta_ajustar == 0


def conferir(contagem, resumo=None):
    """Compara as divergências da contagem com o saldo do SET de hoje.

    `disponivel` fica falso quando não há foto do SET mais nova que a usada na contagem:
    comparar com a mesma foto não responderia nada, só repetiria a divergência.
    """
    from . import servicos

    conferencia = Conferencia()
    nova = importacao_servicos.ultima_concluida()
    conferencia.importacao = nova
    if nova is None:
        return conferencia
    if contagem.importacao_id and nova.pk == contagem.importacao_id:
        return conferencia
    conferencia.disponivel = True

    divergentes = (resumo or servicos.resumir(contagem)).itens_divergentes
    if not divergentes:
        return conferencia
    saldos = dict(
        nova.itens.filter(codigo__in=[item.codigo for item in divergentes])
        .values_list("codigo", "estoque")
    )
    for item in divergentes:
        saldo = saldos.get(item.codigo)
        if saldo is None:
            # Produto que saiu do cadastro do SET entre a contagem e agora. Não é
            # ajuste entrado nem ajuste faltando: é outra coisa, e some da conta.
            conferencia.sumiram += 1
            continue
        saldo = Decimal(saldo)
        if saldo == (item.quantidade or ZERO):
            estado = ENTROU
            conferencia.entraram += 1
        elif saldo == (item.saldo_set or ZERO):
            estado = NAO_ENTROU
            conferencia.nao_entraram += 1
        else:
            estado = MEXEU
            conferencia.mexeram += 1
        conferencia.linhas.append(
            LinhaConferida(item=item, saldo_de_hoje=saldo, estado=estado)
        )
    # O que ainda falta ajustar primeiro, e dentro disso o maior dinheiro: é a ordem em
    # que alguém vai sentar no SET e digitar.
    ordem = {NAO_ENTROU: 0, MEXEU: 1, ENTROU: 2}
    conferencia.linhas.sort(
        key=lambda l: (ordem[l.estado], -abs(l.item.valor_da_diferenca or ZERO))
    )
    return conferencia
