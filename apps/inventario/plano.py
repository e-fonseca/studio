"""O plano de inventário: de quanto em quanto tempo cada produto é contado.

Pedido do Edson em 22/10/2026: *"controle inventario padrão aplicado no mercado varejo
produtos de artesanatos, utilizar as melhores praticas, estipular prazos de tempos em
tempos realizar o inventario"*.

O que o varejo faz, e por que não é "contar a loja toda"
--------------------------------------------------------
Parar a loja para contar doze mil produtos é o que ninguém faz duas vezes: leva dias,
erra no fim do segundo dia e só acontece uma vez por ano, quando acontece. O padrão do
varejo é **contagem cíclica**: conta-se um pedaço por vez, sempre, e o pedaço é escolhido
pela curva ABC — o produto que sustenta a loja é contado muitas vezes por ano, o que
quase não vende é contado duas.

Os prazos deste plano, que são os usados no varejo:

| Classe | O que é | Contar a cada |
|---|---|---|
| A | os primeiros 80% do faturamento | 30 dias |
| B | dos 80% aos 95% | 90 dias |
| C | os últimos 5% | 180 dias |
| sem venda | nenhuma unidade em 12 meses | 180 dias |

E, por cima disso, **a contagem geral uma vez por ano** (365 dias), que é a que fecha o
ano para a contabilidade.

Numa loja de artesanato a classe A é pequena e muito valiosa: peça de vime, cerâmica e
tecido sai de lugar, vai para a vitrine, volta arranhada e é vendida sem baixa. É aí que
o saldo descola, e é por isso que ela é contada todo mês e não uma vez por ano.

"Sem venda" fica com o prazo de C, e não com um prazo maior, de propósito: é a prateleira
que ninguém mexe, e prateleira que ninguém mexe é onde a falta demora mais a aparecer.

De onde saem os números
-----------------------
* A classe vem de `apps/core/curva_abc.py`, a mesma que o painel mostra.
* "Quando foi contado" é a última contagem **fechada** em que o código apareceu.
  Contagem aberta não conta porque ainda não é resultado — a pessoa está no meio dela.
* "Nunca contado" não é um detalhe desta loja, é o estado dela: a loja nunca fez
  contagem física, e eram 1.456 produtos com saldo negativo no SET em 20/09/2026.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models import Max
from django.utils import timezone

from apps.core import curva_abc

from .models import Contagem, ItemContado

ZERO = Decimal("0")

# De quanto em quanto tempo contar, por classe. Dias.
CADENCIA = {"A": 30, "B": 90, "C": 180, "": 180}
# A contagem geral que fecha o ano.
CADENCIA_GERAL = 365

# Quantos produtos a tela sugere contar agora. É uma tarde de trabalho, não uma lista
# que ninguém começa: cinquenta itens de prateleira contam-se em cerca de uma hora.
QUANTOS_SUGERIDOS = 50


@dataclass
class ClasseDoPlano:
    """Uma linha do plano: a classe, o prazo dela e quanto está vencido."""

    letra: str
    titulo: str = ""
    explicacao: str = ""
    cada_dias: int = 0
    produtos: int = 0
    nunca_contados: int = 0
    vencidos: int = 0
    em_dia: int = 0
    valor_vencido: Decimal = ZERO

    @property
    def rotulo(self):
        """"Classe A — sustentam a loja", ou "Sem venda — não venderam no ano"."""
        nome = f"Classe {self.letra}" if self.letra else "Sem venda"
        return f"{nome} — {self.titulo}" if self.titulo else nome

    @property
    def a_contar(self):
        """Vencidos mais nunca contados: é o que falta contar nesta classe."""
        return self.vencidos + self.nunca_contados

    @property
    def em_falta(self):
        return self.a_contar > 0

    @property
    def fatia_em_dia(self):
        """Quanto da classe está em dia, de 0 a 100, para a barra da tela."""
        if not self.produtos:
            return 0
        return int(self.em_dia * 100 / self.produtos)


@dataclass
class ProdutoDoPlano:
    """Um produto que está esperando contagem, com o motivo de estar na frente."""

    codigo: str
    descricao: str = ""
    grupo: str = ""
    classe: str = ""
    estoque: Decimal = ZERO
    custo: Decimal | None = None
    contado_em: datetime | None = None
    dias_sem_contar: int | None = None
    prazo_dias: int = 0

    @property
    def valor(self):
        if self.custo is None:
            return None
        return (max(self.estoque, ZERO) * self.custo).quantize(Decimal("0.01"))

    @property
    def nunca_contado(self):
        return self.contado_em is None

    @property
    def atraso_dias(self):
        """Dias além do prazo. Nunca contado não tem atraso: tem ausência."""
        if self.dias_sem_contar is None:
            return None
        return max(0, self.dias_sem_contar - self.prazo_dias)


@dataclass
class Plano:
    """O plano inteiro, como a tela o mostra."""

    classes: list = field(default_factory=list)
    sugeridos: list = field(default_factory=list)
    produtos: int = 0
    nunca_contados: int = 0
    a_contar: int = 0
    valor_a_contar: Decimal = ZERO
    ultima_contagem: object | None = None
    dias_desde_a_ultima: int | None = None

    @property
    def geral_vencida(self):
        """A contagem geral está vencida quando nunca houve, ou passou de um ano.

        Produto que nunca passou pelo leitor é contagem geral que nunca fechou: não há
        como dizer que a loja foi contada se sobrou prateleira inteira de fora.
        """
        if self.nunca_contados:
            return True
        return (self.dias_desde_a_ultima or 0) > CADENCIA_GERAL

    @property
    def em_dia(self):
        return self.a_contar == 0


def _ultima_contagem_por_codigo():
    """{código: quando foi contado pela última vez}, só de contagem FECHADA."""
    linhas = (
        ItemContado.objects
        .filter(contagem__situacao=Contagem.Situacao.FECHADA)
        .values("codigo")
        .annotate(quando=Max("contado_em"))
    )
    return {linha["codigo"]: linha["quando"] for linha in linhas}


def montar(importacao, hoje=None):
    """O plano de contagem a partir da última foto do SET."""
    plano = Plano()
    if importacao is None:
        return plano
    agora = hoje or timezone.now()
    contadas = _ultima_contagem_por_codigo()

    # A curva sai de TODOS os produtos da foto, e não só dos que têm peça na prateleira.
    # É a mesma população do painel, e tem de ser: a classe do produto é a mesma coisa
    # nas duas telas, e calculá-la só entre os que têm estoque faria o mesmo produto ser
    # classe A aqui e B no painel — o defeito que a 1.34.0 consertou entre o Painel e a
    # Visão geral, de volta por outra porta.
    classes_por_codigo = curva_abc.por_produto(
        importacao.itens.values_list("codigo", "receita_12m")
    )
    # Mas no PLANO entra só o produto que tem (ou deveria ter) peça na prateleira:
    # contar o que está zerado não acha divergência nenhuma e afogaria a lista.
    produtos = list(
        importacao.itens.exclude(estoque=0)
        .values("codigo", "descricao", "grupo", "estoque", "custo")
    )

    classes = {
        letra: ClasseDoPlano(
            letra=letra,
            titulo=curva_abc.TITULOS[letra],
            explicacao=curva_abc.EXPLICACOES[letra],
            cada_dias=CADENCIA[letra],
        )
        for letra in (*curva_abc.LETRAS, "")
    }
    esperando = []
    for produto in produtos:
        letra = classes_por_codigo.get(produto["codigo"], "")
        classe = classes[letra]
        classe.produtos += 1
        plano.produtos += 1

        quando = contadas.get(produto["codigo"])
        dias = None if quando is None else (agora - quando).days
        prazo = CADENCIA[letra]
        vencido = quando is None or dias > prazo

        item = ProdutoDoPlano(
            codigo=produto["codigo"],
            descricao=produto["descricao"] or "",
            grupo=produto["grupo"] or "",
            classe=letra,
            estoque=Decimal(produto["estoque"] or 0),
            custo=produto["custo"],
            contado_em=quando,
            dias_sem_contar=dias,
            prazo_dias=prazo,
        )
        if quando is None:
            classe.nunca_contados += 1
            plano.nunca_contados += 1
        elif vencido:
            classe.vencidos += 1
        else:
            classe.em_dia += 1
        if vencido:
            valor = item.valor or ZERO
            classe.valor_vencido += valor
            plano.a_contar += 1
            plano.valor_a_contar += valor
            esperando.append(item)

    # A ordem é a do dinheiro na prateleira, dentro da classe mais urgente primeiro:
    # contar a classe A atrasada antes da classe C atrasada é o que o varejo faz, e
    # dentro dela o que vale mais é o que mais custa estar errado.
    ordem = {"A": 0, "B": 1, "C": 2, "": 3}
    esperando.sort(key=lambda i: (ordem[i.classe], -(i.valor or ZERO)))
    plano.sugeridos = esperando[:QUANTOS_SUGERIDOS]

    for classe in classes.values():
        classe.valor_vencido = classe.valor_vencido.quantize(Decimal("0.01"))
    plano.valor_a_contar = plano.valor_a_contar.quantize(Decimal("0.01"))
    # Classe sem nenhum produto sai da tela: linha de zero não ajuda ninguém a decidir.
    plano.classes = [classes[letra] for letra in (*curva_abc.LETRAS, "")
                     if classes[letra].produtos]

    ultima = Contagem.objects.filter(situacao=Contagem.Situacao.FECHADA).first()
    plano.ultima_contagem = ultima
    if ultima is not None and ultima.fechada_em:
        plano.dias_desde_a_ultima = (agora - ultima.fechada_em).days
    return plano


def nome_sugerido(plano, hoje=None):
    """O nome que a contagem sugerida ganha, para a pessoa não ter que inventar um.

    Leva a classe mais urgente e a data, porque é assim que ela vai ser procurada
    depois: "contagem da classe A" não diz qual das doze.
    """
    dia = (hoje or timezone.now()).strftime("%d/%m")
    if not plano.sugeridos:
        return f"Contagem de {dia}"
    letra = plano.sugeridos[0].classe
    nome = f"classe {letra}" if letra else "produtos sem venda"
    return f"Contagem cíclica da {nome} · {dia}"


def vencimento(classe_letra, contado_em):
    """Quando este produto vence a próxima contagem. None quando nunca foi contado."""
    if contado_em is None:
        return None
    return contado_em + timedelta(days=CADENCIA.get(classe_letra, CADENCIA["C"]))
