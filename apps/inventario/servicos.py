"""Regras da contagem: achar o produto, somar o que foi contado, apurar a diferença."""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from django.db.models import Q
from django.utils import timezone

from apps.auditoria.servicos import registrar
from apps.core import barras
from apps.importacao import servicos as importacao_servicos

from .models import Contagem, ItemContado

ZERO = Decimal("0")


class ErroDeContagem(Exception):
    """Mensagem pronta para a tela, em português de quem está na prateleira."""


@dataclass
class Resumo:
    contados: int = 0
    conferem: int = 0
    divergentes: int = 0
    faltando: Decimal = ZERO
    sobrando: Decimal = ZERO
    valor_da_falta: Decimal = ZERO
    valor_da_sobra: Decimal = ZERO
    nao_contados: int = 0
    itens_divergentes: list = field(default_factory=list)

    @property
    def diferenca_em_dinheiro(self):
        return self.valor_da_sobra - self.valor_da_falta


def quantidade_informada(bruto):
    """Aceita 3, 3,5 e 3.5, que é como as pessoas digitam quantidade."""
    limpo = (bruto or "").strip().replace(" ", "").replace(",", ".")
    if not limpo:
        return None
    try:
        valor = Decimal(limpo)
    except (InvalidOperation, ValueError):
        return None
    if valor < 0 or valor > Decimal("999999"):
        return None
    return valor.quantize(Decimal("0.001"))


def procurar_produto(importacao, termo):
    """Acha o produto pelo código de barras, pelo código ou pelo nome exato.

    A ordem importa: no meio da contagem o que chega é quase sempre o leitor, e o código
    de barras é o único jeito de ter certeza de que é aquele produto e não outro de nome
    parecido. Nome só casa quando um único produto casa.
    """
    termo = (termo or "").strip()
    if importacao is None or not termo:
        return None
    itens = importacao.itens
    # O leitor pela câmera corta o zero da frente do EAN-13 (ver apps/core/barras.py),
    # então procura-se o que foi lido e também a forma com o zero.
    for forma in barras.variantes(termo):
        achado = itens.filter(codigo_barras__iexact=forma).first()
        if achado is not None:
            return achado
    achado = itens.filter(codigo__iexact=termo).first()
    if achado is not None:
        return achado
    parecidos = list(itens.filter(descricao__icontains=termo)[:2])
    return parecidos[0] if len(parecidos) == 1 else None


def registrar_contagem(contagem, termo, quantidade, usuario, observacao=""):
    """Soma o que foi contado de um produto. Devolve o item contado."""
    if not contagem.aberta:
        raise ErroDeContagem("Esta contagem já foi fechada. Abra uma nova para continuar contando.")
    if quantidade is None:
        raise ErroDeContagem(
            "Informe quantas unidades você contou. Pode ser com vírgula, como 2,5."
        )
    importacao = contagem.importacao or importacao_servicos.ultima_concluida()
    produto = procurar_produto(importacao, termo)
    if produto is None:
        raise ErroDeContagem(
            f"Não encontrei nenhum produto com “{termo}”. Passe o leitor de novo, ou "
            "procure pelo código do produto; se o nome vier parecido em vários produtos, "
            "o sistema não arrisca escolher um."
        )

    item, criado = ItemContado.objects.get_or_create(
        contagem=contagem,
        codigo=produto.codigo,
        defaults={
            "descricao": produto.descricao,
            "codigo_barras": produto.codigo_barras,
            "saldo_set": produto.estoque or ZERO,
            "custo": produto.custo,
            "contado_por": usuario if getattr(usuario, "is_authenticated", False) else None,
        },
    )
    anterior = item.quantidade
    item.quantidade = (item.quantidade or ZERO) + quantidade
    item.contado_em = timezone.now()
    if observacao:
        item.observacao = observacao[:200]
    if getattr(usuario, "is_authenticated", False):
        item.contado_por = usuario
    item.save()

    registrar(
        "inventario.item_contado", usuario=usuario, recurso=item,
        recurso_rotulo=f"{produto.codigo} {produto.descricao}"[:200],
        antes=None if criado else {"quantidade": str(anterior)},
        depois={"quantidade": str(item.quantidade), "saldo_set": str(item.saldo_set),
                "contagem": contagem.nome},
    )
    return item


def apagar_item(item, usuario):
    """Tira um produto da contagem, para quando alguém bipou o que não devia."""
    if not item.contagem.aberta:
        raise ErroDeContagem("Esta contagem já foi fechada.")
    registrar(
        "inventario.item_removido", usuario=usuario, recurso=item.contagem,
        recurso_rotulo=item.contagem.nome,
        antes={"codigo": item.codigo, "quantidade": str(item.quantidade)},
    )
    item.delete()


def resumir(contagem):
    """Os números do topo da tela e a lista do que está diferente."""
    resumo = Resumo()
    itens = list(contagem.itens.all())
    resumo.contados = len(itens)
    for item in itens:
        if item.bate:
            resumo.conferem += 1
            continue
        resumo.divergentes += 1
        resumo.itens_divergentes.append(item)
        valor = item.valor_da_diferenca or ZERO
        if item.diferenca < 0:
            resumo.faltando += -item.diferenca
            resumo.valor_da_falta += -valor
        else:
            resumo.sobrando += item.diferenca
            resumo.valor_da_sobra += valor
    # A maior diferença em dinheiro primeiro: é por onde a loja começa a ajustar.
    resumo.itens_divergentes.sort(key=lambda i: abs(i.valor_da_diferenca or ZERO), reverse=True)
    importacao = contagem.importacao
    if importacao is not None:
        resumo.nao_contados = importacao.itens.exclude(
            codigo__in=[item.codigo for item in itens]
        ).count()
    return resumo


def fechar(contagem, usuario):
    if not contagem.aberta:
        raise ErroDeContagem("Esta contagem já estava fechada.")
    contagem.situacao = Contagem.Situacao.FECHADA
    contagem.fechada_em = timezone.now()
    contagem.fechada_por = usuario if getattr(usuario, "is_authenticated", False) else None
    contagem.save(update_fields=["situacao", "fechada_em", "fechada_por"])
    registrar("inventario.contagem_fechada", usuario=usuario, recurso=contagem,
              recurso_rotulo=contagem.nome,
              depois={"itens": contagem.itens.count()})
    return contagem


def abrir(nome, usuario, observacao=""):
    contagem = Contagem.objects.create(
        nome=nome[:120],
        observacao=observacao[:2000],
        aberta_por=usuario if getattr(usuario, "is_authenticated", False) else None,
        importacao=importacao_servicos.ultima_concluida(),
    )
    registrar("inventario.contagem_aberta", usuario=usuario, recurso=contagem,
              recurso_rotulo=contagem.nome)
    return contagem


def divergencias_em_texto(contagem):
    """A lista de ajustes em texto separado por tabulação, para abrir numa planilha.

    Texto, e não planilha pronta, porque é o que o Excel do servidor abre sem instalar
    nada e é o que a pessoa vai usar com o SET aberto ao lado, linha por linha.
    """
    linhas = ["codigo\tproduto\tsaldo_no_set\tcontado\tdiferenca\tvalor_da_diferenca"]
    for item in resumir(contagem).itens_divergentes:
        valor = item.valor_da_diferenca
        linhas.append(
            f"{item.codigo}\t{item.descricao}\t{item.saldo_set}\t{item.quantidade}\t"
            f"{item.diferenca}\t{'' if valor is None else valor}"
        )
    return "\n".join(linhas) + "\n"


def contagens():
    return Contagem.objects.all()


def em_andamento():
    return Contagem.objects.filter(situacao=Contagem.Situacao.ABERTA).first()


def consultar(pk):
    return Contagem.objects.filter(pk=pk).prefetch_related("itens").first()


def produtos_nao_contados(contagem, quantos=20):
    """O que ainda não passou pelo leitor, do que mais vale para o que menos vale.

    Vinte, e não cinquenta: no celular cada linha é um cartão, e cinquenta cartões
    faziam a tela da contagem passar de quinze mil pixels — ninguém chega ao fim, e o
    que importa (o que está diferente do SET) fica enterrado. Quem quer a lista inteira
    do que falta contar tem a folha de contagem do plano, que é feita para isso.
    """
    importacao = contagem.importacao
    if importacao is None:
        return []
    contados = list(contagem.itens.values_list("codigo", flat=True))
    return list(
        importacao.itens.exclude(codigo__in=contados)
        .filter(Q(estoque__gt=0) | Q(estoque__lt=0))
        .order_by("-estoque")[:quantos]
    )


# Foto tirada pela câmera do celular. A tela manda sempre JPEG, feito do quadro do
# vídeo; qualquer outra coisa é recusada, porque ninguém precisa enviar arquivo aqui.
TAMANHO_MAXIMO_DA_FOTO = 4 * 1024 * 1024
TIPOS_DE_FOTO = ("image/jpeg", "image/jpg")


def guardar_foto(item, arquivo, usuario):
    """Guarda a foto da prateleira junto do item contado."""
    if arquivo is None:
        raise ErroDeContagem("Nenhuma foto chegou. Tente tirar de novo.")
    if arquivo.size > TAMANHO_MAXIMO_DA_FOTO:
        raise ErroDeContagem("A foto ficou grande demais. Tire outra, mais perto do produto.")
    if (getattr(arquivo, "content_type", "") or "").lower() not in TIPOS_DE_FOTO:
        raise ErroDeContagem("Só foto tirada pela câmera desta tela é aceita aqui.")
    if not item.contagem.aberta:
        raise ErroDeContagem("Esta contagem já foi fechada.")
    if item.foto:
        item.foto.delete(save=False)  # a última foto é a que vale; não acumula arquivo
    item.foto = arquivo
    item.foto_em = timezone.now()
    item.save(update_fields=["foto", "foto_em"])
    registrar("inventario.foto_guardada", usuario=usuario, recurso=item,
              recurso_rotulo=f"{item.codigo} {item.descricao}"[:200],
              depois={"bytes": arquivo.size})
    return item
