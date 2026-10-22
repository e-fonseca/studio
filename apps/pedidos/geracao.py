"""Gerar os pedidos de compra por fornecedor, a partir da lista de compra de hoje.

Pedido do Edson em 20/10/2026: *"na tela pedidos, gerar automaticamente pedidos de
compra mercadorias por fornecedor, com a quantidade sugerida pelo formula informada
anteriormente aqui"*.

Até aqui o caminho era um só: abrir a lista de compra, filtrar um fornecedor e clicar
em "Gerar o pedido". Quem chega pela tela de Pedidos vê os pedidos que já existem e
não tem como fazer o do dia. Este módulo é o outro lado: a mesma conta, o mesmo papel
e o mesmo registro, só que enxergados por fornecedor e prontos para um clique.

Duas linhas que não se cruzam, porque são regras dele:

1. **Nenhum pedido nasce sozinho.** "Automaticamente" aqui quer dizer que o sistema
   monta tudo — fornecedor, linhas, quantidade, folha — e não que ele pede. O prompt
   dele é explícito: *"Não aprovar nem emitir pedidos automaticamente"*. O clique é
   de uma pessoa, e cada clique gera o pedido daquele fornecedor.
2. **O teto do mês é uma informação, não uma trava.** A tela diz quais fornecedores
   cabem no mês e quais passam, e o botão que gera de uma vez só pega os que cabem —
   *"Não ultrapassar o orçamento sem autorização"*. Gerar um que passa do teto
   continua possível, um a um, porque quem decide é quem está comprando.
"""

from dataclasses import dataclass
from decimal import Decimal

from apps.compras import lista_de_compra, pedido as folha_do_pedido
from apps.compras.models import DadosDaEmpresa

from . import servicos

ZERO = Decimal("0")


@dataclass
class PedidoPrevisto:
    """Um fornecedor da lista de compra, do jeito que ele sairia em pedido hoje."""

    bloco: object
    nome: str
    quantos: int = 0
    unidades: Decimal = ZERO
    valor: Decimal = ZERO
    prazo_dias: int = None
    prazo_assumido: bool = False
    ajustados: int = 0
    # Cabe no que sobrou do teto do mês? Vem da mesma priorização da lista de compra.
    cabe_no_mes: bool = True
    # O pedido deste fornecedor já foi feito hoje, com estas mesmas linhas. A tela
    # mostra o número em vez de um botão: clicar de novo não faria nada (o serviço
    # reaproveita), e um botão que não faz nada é pior do que nenhum.
    ja_pedido = None

    @property
    def ja_foi_pedido(self):
        return self.ja_pedido is not None


def previstos(importacao, *, teto=None, media="", urgencia=""):
    """Os pedidos que a lista de compra de hoje geraria, um por fornecedor.

    A ordem é a da lista de compra priorizada: quem tapa o buraco maior primeiro, e
    os que não cabem no mês depois. Devolve `(previstos, lista)` porque a tela precisa
    da lista para dizer de quando é o dado e qual janela de venda virou a conta.
    """
    lista = lista_de_compra.montar(importacao, urgencia=urgencia, media=media)
    lista = lista_de_compra.priorizar(lista, teto)
    cabem = [b.nome for b in lista.primeiro]
    ordenados = list(lista.primeiro) + [b for b in lista.fornecedores
                                        if b.nome not in set(cabem)]
    saida = []
    for bloco in ordenados:
        if bloco.nome == lista_de_compra.SEM_FORNECEDOR:
            # Produto sem fornecedor no cadastro do SET não vira pedido: não há a quem
            # mandar a folha. A lista de compra continua mostrando, e é lá que se
            # conserta o cadastro.
            continue
        itens = folha_do_pedido.itens_do_pedido(bloco)
        if not itens:
            # Fornecedor cuja lista inteira está marcada para não comprar agora.
            continue
        previsto = PedidoPrevisto(
            bloco=bloco,
            nome=bloco.nome,
            quantos=len(itens),
            unidades=sum((item.quantidade or ZERO for item in itens), ZERO),
            valor=sum((item.valor_do_pedido or ZERO for item in itens), ZERO),
            prazo_dias=bloco.prazo_dias,
            prazo_assumido=bloco.prazo_assumido,
            ajustados=sum(1 for item in itens if item.foi_ajustada),
            cabe_no_mes=bloco.nome in set(cabem),
        )
        previsto.ja_pedido = servicos.mesmo_pedido_de_hoje(bloco.nome, itens)
        saida.append(previsto)
    return saida, lista


def um(previstos_de_hoje, nome):
    """O previsto de um fornecedor, pelo nome. None quando ele não está mais na lista."""
    for previsto in previstos_de_hoje:
        if previsto.nome == nome:
            return previsto
    return None


def gerar(usuario, blocos, *, data_corte, emitido_por, empresa=None):
    """Registra um pedido por fornecedor e anexa a folha DELE, não o maço inteiro.

    Devolve `(guardados, pulados)`: pulados são os fornecedores que não deram pedido
    porque não sobrou linha nenhuma com quantidade. Era o loop que vivia dentro da
    view da lista de compra; mora aqui porque agora as duas telas pedem a mesma coisa,
    e um pedido guardado com a folha de outro fornecedor é o tipo de erro que só
    aparece quando a mercadoria chega.
    """
    empresa = empresa or DadosDaEmpresa.atual()
    guardados, pulados = [], []
    for bloco in blocos:
        try:
            registro = servicos.registrar_pedido(usuario, bloco, data_corte=data_corte)
        except servicos.NaoDeuCerto:
            pulados.append(bloco.nome)
            continue
        folha = folha_do_pedido.montar([bloco], empresa, data_corte=data_corte,
                                       emitido_por=emitido_por)
        servicos.guardar_a_folha(usuario, registro, folha,
                                 folha_do_pedido.nome_do_arquivo([bloco], data_corte))
        guardados.append(registro)
    return guardados, pulados
