"""Organizar a prateleira: o que está sem etiqueta, o que está danificado, o que parou.

Pedido do Edson em 22/10/2026: *"precisamos organizar os produtos sem etiqueta,
danificados, produtos muito tempo parados (...) planejar relatório de descartes de
produtos sem aproveitamento, planejar relatório de produtos para conserto/reparo,
realizar classificação desses produtos"*.

São três grupos e duas origens, e isso explica a tela
-----------------------------------------------------
**Sem etiqueta** e **danificado** só se descobrem com a peça na mão: é a pessoa que está
contando que vê. Vêm da contagem, marcados no leitor ou na tela do computador.

**Parado** é o contrário: ninguém vê olhando a peça, porque a peça está perfeita — o que
está errado é que ela não sai desde março. Isso só a venda diz, e vem da foto do SET.

Os três estão na mesma tela porque a pergunta é a mesma: *o que eu faço com esta peça?*
E as respostas são as que ele pediu — refazer a etiqueta, mandar consertar, descartar.

A classificação, e por que ela é em dois tempos
-----------------------------------------------
Quem está na prateleira marca **"danificado"**, e só isso: na hora da contagem não se
decide se uma luminária de vime descascada vale um conserto ou vai para o lixo, e
obrigar a decidir ali faria a pessoa marcar o que for mais rápido. Quem decide é a
gerência, depois, nesta tela, com o custo da peça à vista — e aí o danificado vira
**para conserto** ou **para descarte**. É essa a classificação do pedido dele.

Nada sai da lista sozinho: sai quando alguém diz que a providência foi tomada. Etiqueta
refeita, peça de volta da oficina, peça descartada com a baixa digitada no SET. Sem isso
a tela seria um histórico que só cresce.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from apps.auditoria.servicos import registrar
from apps.compras.sugestoes import so_mercadoria

from .models import Contagem, ItemContado

ZERO = Decimal("0")

# Quantos meses sem vender uma unidade para a peça entrar na lista de parados, tendo
# estoque. Seis meses é o que o varejo usa para revisão de giro: abaixo disso ainda
# cabe sazonalidade (a peça de Natal não vende em março e nem por isso está encalhada),
# e esta loja tem produto de estação — a sugestão de compra já olha o ano passado.
MESES_PARADO = 6
# A partir de um ano sem vender, a peça deixa de ser "devagar" e passa a ser dinheiro
# parado: é a linha que a lista destaca.
MESES_ENCALHADO = 12

QUANTOS_PARADOS = 200


# O rótulo do botão na hora da contagem. É mais curto que o nome do estado de propósito:
# "Danificado, a classificar" diz o certo no título do grupo da tela Organizar, mas como
# botão quebra em duas linhas e estica cada linha da contagem.
ROTULO_CURTO = {
    "ok": "Perfeita",
    "sem_etiqueta": "Sem etiqueta",
    "danificado": "Danificada",
}


def na_prateleira():
    """Os estados que quem está contando pode marcar, com o rótulo curto do botão.

    Conserto e descarte ficam de fora: decidir entre os dois é da gerência, na tela
    Organizar, com o custo da peça à vista.
    """
    return [(valor, ROTULO_CURTO[valor]) for valor in ROTULO_CURTO]


class ErroDeOrganizacao(Exception):
    """Mensagem pronta para a tela."""


@dataclass
class Parado:
    """Um produto com peça na prateleira e sem venda há muito tempo."""

    codigo: str
    descricao: str = ""
    grupo: str = ""
    fornecedor: str = ""
    estoque: Decimal = ZERO
    custo: Decimal | None = None
    ultima_venda: date | None = None
    dias_sem_vender: int | None = None

    @property
    def valor(self):
        if self.custo is None:
            return None
        return (max(self.estoque, ZERO) * self.custo).quantize(Decimal("0.01"))

    @property
    def nunca_vendeu(self):
        return self.ultima_venda is None

    @property
    def meses_sem_vender(self):
        if self.dias_sem_vender is None:
            return None
        return self.dias_sem_vender // 30

    @property
    def encalhado(self):
        """Um ano ou mais sem vender, ou nunca vendido: é o grupo que a tela destaca."""
        if self.dias_sem_vender is None:
            return True
        return self.dias_sem_vender >= MESES_ENCALHADO * 30


@dataclass
class Grupo:
    """Um dos grupos da tela, com o que fazer escrito e com os botões que fazem.

    Os botões moram aqui, e não no modelo da tela, porque é o grupo que define a
    providência: "etiqueta refeita" só existe para quem está sem etiqueta, e oferecer
    "para descarte" numa peça já classificada seria oferecer refazer a decisão no lugar
    de registrar que ela foi cumprida.
    """

    chave: str
    titulo: str
    o_que_fazer: str
    itens: list = field(default_factory=list)
    valor: Decimal = ZERO
    # (rótulo do botão, estado de destino): transforma a peça noutro estado.
    classificar_em: tuple = ()
    # O rótulo do botão que diz "a providência foi tomada", quando existe.
    resolver_rotulo: str = ""
    # O nome da rota do relatório deste grupo, quando ele tem um.
    relatorio: str = ""
    # Quantas linhas a TELA mostra. O relatório traz todas. No celular cada linha vira um
    # cartão, e sessenta cartões de produto parado fazem uma página de dezoito mil pixels
    # em que ninguém chega ao fim — foi o que aconteceu com a tela de Pedidos na 1.37.0.
    limite: int = 30

    @property
    def quantos(self):
        return len(self.itens)

    @property
    def na_tela(self):
        return self.itens[:self.limite]

    @property
    def escondidos(self):
        return max(0, self.quantos - self.limite)

    @property
    def vazio(self):
        return not self.itens

    @property
    def de_produto(self):
        """Os parados são produtos do SET, não peças contadas: a linha é outra."""
        return self.chave == "parado"


def esperando(estado=None):
    """Os itens contados que ainda esperam providência, do mais caro para o mais barato.

    Olha TODAS as contagens, abertas e fechadas: uma peça quebrada não espera a contagem
    fechar para continuar quebrada.
    """
    consulta = (
        ItemContado.objects
        .filter(resolvido_em__isnull=True)
        .exclude(estado=ItemContado.Estado.OK)
        .select_related("contagem", "estado_por")
    )
    if estado:
        consulta = consulta.filter(estado=estado)
    itens = list(consulta)
    itens.sort(key=lambda i: i.valor_no_custo or ZERO, reverse=True)
    return itens


def parados(importacao, hoje=None, quantos=QUANTOS_PARADOS):
    """Produtos com peça na prateleira e sem venda há mais de `MESES_PARADO` meses."""
    if importacao is None:
        return []
    hoje = hoje or timezone.localdate()
    corte = hoje - timedelta(days=MESES_PARADO * 30)
    # Só mercadoria de revenda. Sem isto a lista traz "CONSUMO PROPRIO - CESTO/PAPEL",
    # que nunca vendeu porque nunca foi para vender: é o material que a loja usa. Já foi
    # defeito uma vez, entre o "Parado sem vender" do painel e a lista de compra, e a
    # definição de mercadoria mora em apps/compras/sugestoes.py para ser uma só.
    consulta = (
        so_mercadoria(importacao.itens)
        .filter(estoque__gt=0)
        .filter(Q(ultima_venda__isnull=True) | Q(ultima_venda__lt=corte))
        .values("codigo", "descricao", "grupo", "fornecedor", "estoque", "custo",
                "ultima_venda")
    )
    saida = []
    for produto in consulta:
        venda = produto["ultima_venda"]
        saida.append(Parado(
            codigo=produto["codigo"],
            descricao=produto["descricao"] or "",
            grupo=produto["grupo"] or "",
            fornecedor=produto["fornecedor"] or "",
            estoque=Decimal(produto["estoque"] or 0),
            custo=produto["custo"],
            ultima_venda=venda,
            dias_sem_vender=None if venda is None else (hoje - venda).days,
        ))
    # O mais caro primeiro: é o dinheiro parado que decide o que a loja liquida antes.
    saida.sort(key=lambda p: p.valor or ZERO, reverse=True)
    return saida[:quantos]


def grupos(importacao, hoje=None):
    """Os grupos da tela, na ordem em que a loja age sobre eles.

    A ordem é a da fila de trabalho: primeiro o que depende de uma decisão (classificar
    o danificado), depois o que depende de uma providência (etiqueta, oficina, baixa),
    e por último o que depende de uma política da loja (o parado, que se liquida ou se
    devolve, e isso não é um botão).
    """
    saida = [
        Grupo("danificado", "Danificados, a classificar",
              "Decidir entre conserto e descarte, com o custo da peça à vista.",
              esperando(ItemContado.Estado.DANIFICADO),
              classificar_em=(("Para conserto", ItemContado.Estado.CONSERTO),
                              ("Para descarte", ItemContado.Estado.DESCARTE))),
        Grupo("sem_etiqueta", "Sem etiqueta",
              "Refazer a etiqueta. O sistema imprime a folha com o código de barras de "
              "cada uma.",
              esperando(ItemContado.Estado.SEM_ETIQUETA),
              resolver_rotulo="Etiqueta refeita"),
        Grupo("conserto", "Para conserto",
              "Peça que vale o reparo e volta para a venda.",
              esperando(ItemContado.Estado.CONSERTO),
              resolver_rotulo="Voltou da oficina", relatorio="inventario:conserto"),
        Grupo("descarte", "Para descarte",
              "Peça sem aproveitamento. A baixa é digitada no SET por uma pessoa, e só "
              "depois dela o estoque e o custo da loja ficam certos.",
              esperando(ItemContado.Estado.DESCARTE),
              resolver_rotulo="Baixa dada no SET", relatorio="inventario:descarte"),
        Grupo("parado", "Parados na prateleira",
              f"Sem vender uma unidade há mais de {MESES_PARADO} meses. Liquidar, "
              "devolver ao fornecedor ou descartar.",
              parados(importacao, hoje=hoje), relatorio="inventario:parados",
              # Parado é lista de consulta, não fila de trabalho: a loja olha os de maior
              # dinheiro e decide a política. Dez cabem numa tela de celular sem esticar
              # a página; o relatório traz os duzentos.
              limite=10),
    ]
    for grupo in saida:
        # O ZERO do início não é enfeite: `sum` de lista vazia devolve o int 0, que não
        # tem quantize, e grupo vazio é o caso NORMAL desta tela.
        grupo.valor = sum(
            (((item.valor_no_custo if isinstance(item, ItemContado) else item.valor) or ZERO)
             for item in grupo.itens), ZERO,
        ).quantize(Decimal("0.01"))
    return saida


def marcar(item, estado, usuario, observacao=""):
    """Marca como o produto foi encontrado, ou para onde ele vai.

    Marcar de novo o mesmo estado é permitido e não cria evento: a pessoa clica duas
    vezes no celular com a mão ocupada, e um histórico cheio de linhas iguais atrapalha
    quem for ler a trilha depois.
    """
    estados = {valor for valor, _ in ItemContado.Estado.choices}
    if estado not in estados:
        raise ErroDeOrganizacao("Esse estado não existe.")
    if item.resolvido_em and estado != item.estado:
        raise ErroDeOrganizacao(
            "Este item já foi resolvido. Para mexer nele de novo, conte a peça outra vez."
        )
    anterior = item.estado
    if anterior == estado and not observacao:
        return item
    item.estado = estado
    item.estado_em = timezone.now()
    item.estado_por = usuario if getattr(usuario, "is_authenticated", False) else None
    campos = ["estado", "estado_em", "estado_por"]
    if observacao:
        item.observacao = observacao[:200]
        campos.append("observacao")
    item.save(update_fields=campos)
    registrar(
        "inventario.estado_marcado", usuario=usuario, recurso=item,
        recurso_rotulo=f"{item.codigo} {item.descricao}"[:200],
        antes={"estado": anterior},
        depois={"estado": estado, "contagem": item.contagem.nome,
                "observacao": item.observacao},
    )
    return item


def resolver(item, usuario):
    """Diz que a providência foi tomada e tira o item da fila da tela Organizar."""
    if item.estado == ItemContado.Estado.OK:
        raise ErroDeOrganizacao("Este item está marcado como perfeito: não há o que resolver.")
    if item.resolvido_em:
        return item
    item.resolvido_em = timezone.now()
    item.resolvido_por = usuario if getattr(usuario, "is_authenticated", False) else None
    item.save(update_fields=["resolvido_em", "resolvido_por"])
    registrar(
        "inventario.providencia_tomada", usuario=usuario, recurso=item,
        recurso_rotulo=f"{item.codigo} {item.descricao}"[:200],
        depois={"estado": item.estado, "contagem": item.contagem.nome},
    )
    return item


def reabrir(item, usuario):
    """Desfaz a providência, para o caso de alguém ter clicado no item errado."""
    if not item.resolvido_em:
        return item
    item.resolvido_em = None
    item.resolvido_por = None
    item.save(update_fields=["resolvido_em", "resolvido_por"])
    registrar(
        "inventario.providencia_desfeita", usuario=usuario, recurso=item,
        recurso_rotulo=f"{item.codigo} {item.descricao}"[:200],
        depois={"estado": item.estado},
    )
    return item


def contar_por_estado():
    """Quantos itens esperam providência em cada estado, para o resumo do topo."""
    resumo = {valor: 0 for valor, _ in ItemContado.Estado.choices}
    consulta = (
        ItemContado.objects.filter(resolvido_em__isnull=True)
        .exclude(estado=ItemContado.Estado.OK)
        .values_list("estado", flat=True)
    )
    for estado in consulta:
        resumo[estado] = resumo.get(estado, 0) + 1
    return resumo


def itens_para_etiqueta():
    """Os itens sem etiqueta que têm código de barras para imprimir.

    Peça sem código de barras no cadastro do SET não tem etiqueta para refazer: o
    número precisa nascer no SET primeiro, e isso não é coisa que este sistema faça.
    """
    return [item for item in esperando(ItemContado.Estado.SEM_ETIQUETA) if item.codigo_barras]


def contagens_com_pendencia():
    """As contagens que deixaram peça esperando providência, para a tela Inventário."""
    codigos = (
        ItemContado.objects.filter(resolvido_em__isnull=True)
        .exclude(estado=ItemContado.Estado.OK)
        .values_list("contagem_id", flat=True)
    )
    return Contagem.objects.filter(pk__in=set(codigos))
