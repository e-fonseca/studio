"""Registrar o pedido, guardar o que voltou dele e contar o que está em aberto."""

from decimal import Decimal

from django.db import models, transaction
from django.utils import timezone

from apps.auditoria.servicos import registrar
from apps.compras import ajustes, pedido as folha_do_pedido

from . import leitura
from .models import AnexoDoPedido, ItemDoPedido, Pedido

ZERO = Decimal("0")


class NaoDeuCerto(Exception):
    """O que impediu a gravação, numa frase que serve de recado na tela."""


def aprova(usuario):
    """Se o pedido feito por esta pessoa já nasce valendo.

    Sem usuário (um comando, um teste de sistema) o pedido nasce esperando: nada vira
    pedido de verdade sem uma pessoa da gerência por trás.
    """
    return bool(usuario and usuario.is_authenticated and usuario.has_perm("pedidos.aprovar_pedido"))


@transaction.atomic
def registrar_pedido(usuario, bloco, data_corte=None, observacao=""):
    """Guarda um pedido com as linhas que a lista de compra tem AGORA.

    O pedido é a foto do que foi pedido naquele dia, não um apontador para a lista:
    a lista de compra é refeita a cada sincronização e, sem isto, conferir a nota de
    hoje contra "o pedido" daria a quantidade de amanhã.
    """
    itens = folha_do_pedido.itens_do_pedido(bloco)
    if not itens:
        raise NaoDeuCerto(f"Não há o que pedir a {bloco.nome}: todas as quantidades estão em zero.")

    repetido = mesmo_pedido_de_hoje(bloco.nome, itens)
    if repetido is not None:
        # Gerar a mesma folha duas vezes é reimprimir, não pedir de novo. Sem esta
        # regra, imprimir para conferir e imprimir para mandar viraria dois pedidos, e
        # a nota do fornecedor conferiria contra o dobro do que foi pedido.
        return repetido

    quem = usuario if usuario and usuario.is_authenticated else None
    # Pedido da gerência nasce valendo, aprovado por quem fez. Pedido da Líder de loja
    # nasce esperando: "Nenhuma compra é confirmada sem aprovação prévia" (descrição do
    # cargo, 31/10/2026).
    valendo = aprova(usuario)
    agora = timezone.now()
    novo = Pedido.objects.create(
        numero=Pedido.proximo_numero(),
        fornecedor=bloco.nome,
        situacao=Pedido.Situacao.ABERTO if valendo else Pedido.Situacao.AGUARDANDO,
        data_corte=data_corte,
        prazo_dias=bloco.prazo_dias,
        observacao=observacao[:300],
        criado_em=agora,
        criado_por=quem,
        aprovado_em=agora if valendo else None,
        aprovado_por=quem if valendo else None,
    )
    ItemDoPedido.objects.bulk_create([
        ItemDoPedido(
            pedido=novo,
            codigo=item.codigo,
            codigo_barras=getattr(item, "codigo_barras", "") or "",
            descricao=item.descricao,
            grupo=item.grupo or "",
            quantidade=item.quantidade or ZERO,
            custo=item.custo,
            valor=item.valor_do_pedido or ZERO,
            escolhida_a_mao=bool(item.foi_ajustada),
        )
        for item in itens
    ])
    registrar("pedido.registrado", usuario=usuario, recurso=novo,
              recurso_rotulo=f"pedido {novo.numero} · {novo.fornecedor}",
              depois={"numero": novo.numero, "itens": len(itens),
                      "valor": str(novo.valor_total), "situacao": novo.situacao})
    return novo


@transaction.atomic
def aprovar_pedido(usuario, pedido):
    """Faz valer o pedido que a Líder de loja montou. Só a gerência chega aqui.

    Aprovar não manda nada ao fornecedor: o pedido passa a "Pedido feito, esperando a
    mercadoria", e a folha que vale é a que a tela anexa logo depois, sem o aviso.
    """
    if not pedido.esperando_aprovacao:
        raise NaoDeuCerto(
            f"O pedido {pedido.numero} não está esperando aprovação: ele está "
            f"{pedido.get_situacao_display().lower()}."
        )
    if not aprova(usuario):
        raise NaoDeuCerto("Só a gerência aprova pedido.")
    pedido.situacao = Pedido.Situacao.ABERTO
    pedido.aprovado_em = timezone.now()
    pedido.aprovado_por = usuario
    pedido.save(update_fields=["situacao", "aprovado_em", "aprovado_por"])
    registrar("pedido.aprovado", usuario=usuario, recurso=pedido,
              recurso_rotulo=f"pedido {pedido.numero} · {pedido.fornecedor}",
              antes={"situacao": Pedido.Situacao.AGUARDANDO},
              depois={"situacao": pedido.situacao, "valor": str(pedido.valor_total),
                      "feito_por": pedido.quem_fez})
    return pedido


def para_aprovar():
    """Os pedidos esperando a gerência: quantos são e quanto somam."""
    esperando = Pedido.objects.filter(situacao=Pedido.Situacao.AGUARDANDO)
    valor = (ItemDoPedido.objects.filter(pedido__in=esperando)
             .aggregate(soma=models.Sum("valor"))["soma"])
    return esperando.count(), valor or ZERO


def mesmo_pedido_de_hoje(fornecedor, itens):
    """Um pedido aberto, deste fornecedor, feito hoje e com as mesmas linhas.

    "As mesmas linhas" é código e quantidade: trocar a quantidade de um item é outro
    pedido, e aí um pedido novo é o certo.
    """
    assinatura = sorted((item.codigo, item.quantidade or ZERO) for item in itens)
    hoje = timezone.localdate()
    # O que espera aprovação conta: imprimir duas vezes o pedido que a Líder de loja
    # montou também é reimprimir, e a gerência acharia dois pedidos para aprovar.
    candidatos = Pedido.objects.filter(
        fornecedor=fornecedor, criado_em__date=hoje,
        situacao__in=(Pedido.Situacao.ABERTO, Pedido.Situacao.AGUARDANDO),
    ).prefetch_related("itens")
    for candidato in candidatos:
        atual = sorted((linha.codigo, linha.quantidade) for linha in candidato.itens.all())
        if atual == assinatura:
            return candidato
    return None


@transaction.atomic
def anexar(usuario, pedido, arquivo, *, tipo, observacao="", tamanho_maximo):
    """Guarda um documento do pedido e lê o que der para ler dentro dele.

    Guardar e ler são duas coisas, e nessa ordem: o anexo fica guardado mesmo quando a
    leitura não dá certo, porque o "controle futuro" que o Edson pediu é o arquivo
    estar aqui. O que não foi lido vira recado na tela, não arquivo perdido.
    """
    nome, extensao, erro = leitura.validar(arquivo, tamanho_maximo)
    if erro:
        raise NaoDeuCerto(erro)
    if tipo not in AnexoDoPedido.Tipo.values:
        raise NaoDeuCerto("Escolha o que é este arquivo: pedido, romaneio, nota fiscal ou outro.")

    resumo = AnexoDoPedido.calcular_sha256(arquivo)
    if pedido.anexos.filter(sha256=resumo).exists():
        raise NaoDeuCerto("Este arquivo já está anexado a este pedido.")

    documento = leitura.ler_do_envio(arquivo, nome)
    anexo = AnexoDoPedido(
        pedido=pedido, tipo=tipo, nome_original=nome, extensao=extensao,
        tamanho=arquivo.size, sha256=resumo, observacao=observacao[:200],
        documento=documento.formato, numero_do_documento=documento.numero[:40],
        emitente=documento.emitente[:200], emitente_documento=documento.emitente_documento[:24],
        emitido_em=documento.emitido_em, valor_do_documento=documento.valor,
        itens_lidos=[item.como_dicionario() for item in documento.itens],
        erro_de_leitura=documento.aviso[:300],
        enviado_por=usuario if usuario and usuario.is_authenticated else None,
    )
    anexo.arquivo.save(resumo, arquivo, save=False)
    anexo.save()
    registrar("pedido.anexo_enviado", usuario=usuario, recurso=pedido,
              recurso_rotulo=f"pedido {pedido.numero} · {pedido.fornecedor}",
              depois={"anexo_id": anexo.pk, "nome": nome, "tipo": tipo,
                      "sha256": resumo, "itens_lidos": len(documento.itens)})
    return anexo


@transaction.atomic
def guardar_a_folha(usuario, pedido, relatorio, nome_do_arquivo):
    """Guarda no pedido o PDF que acabou de ser gerado, como primeiro anexo.

    "Anexar arquivo dos pedidos" é a primeira coisa do pedido do Edson, e a folha que
    a loja mandou é a única que o sistema pode anexar sozinho: ela nasce aqui.
    """
    from django.core.files.base import ContentFile  # noqa: PLC0415

    dados = relatorio.bytes() if hasattr(relatorio, "bytes") else bytes(relatorio)
    conteudo = ContentFile(dados, name=nome_do_arquivo)
    resumo = AnexoDoPedido.calcular_sha256(conteudo)
    if pedido.anexos.filter(sha256=resumo).exists():
        return None
    anexo = AnexoDoPedido(
        pedido=pedido, tipo=AnexoDoPedido.Tipo.PEDIDO, nome_original=nome_do_arquivo[:200],
        extensao="pdf", tamanho=len(dados), sha256=resumo,
        documento="pdf", erro_de_leitura="",
        enviado_por=usuario if usuario and usuario.is_authenticated else None,
    )
    anexo.arquivo.save(resumo, conteudo, save=False)
    anexo.save()
    return anexo


@transaction.atomic
def editar_pedido(usuario, pedido, *, quantidades, prazo_dias=None, observacao=None):
    """Muda as quantidades de um pedido aberto, e tira a linha que foi para zero.

    Pedido do Edson em 20/10/2026: *"permitir editar pedido"*. O fornecedor liga
    dizendo que só tem seis das dez, ou a loja muda de ideia antes de mandar o papel:
    sem isto a saída era cancelar e fazer outro pedido, e aí o número do pedido que a
    loja já tinha falado ao telefone deixava de existir.

    `quantidades` é {código: quantidade}; código que não vier fica como está. Quantidade
    zero TIRA a linha, porque pedir zero unidade não é pedido — é a mesma regra da folha
    (`apps.compras.pedido.itens_do_pedido`).

    O valor da linha é recalculado pelo custo de referência que já estava guardado: o
    custo não se edita aqui, ele é a foto do dia e é contra ele que a nota é conferida.
    """
    if not pedido.pode_mudar:
        raise NaoDeuCerto(
            "Só pedido em aberto pode ser editado. Este pedido já foi "
            f"{pedido.get_situacao_display().lower()}."
        )
    _so_quem_pode(usuario, pedido, "mudado")

    antes = {"itens": {linha.codigo: str(linha.quantidade) for linha in pedido.itens.all()},
             "prazo_dias": pedido.prazo_dias, "observacao": pedido.observacao,
             "valor": str(pedido.valor_total)}

    mudaram, removidos = [], []
    for linha in list(pedido.itens.all()):
        if linha.codigo not in quantidades:
            continue
        nova = _quantidade(quantidades[linha.codigo])
        if nova == linha.quantidade:
            continue
        if nova <= ZERO:
            removidos.append(linha.codigo)
            linha.delete()
            continue
        linha.quantidade = nova
        linha.valor = (nova * linha.custo).quantize(Decimal("0.01")) if linha.custo is not None else ZERO
        # Quantidade mexida à mão é decisão de gente, e é o que sai em marrom no papel.
        linha.escolhida_a_mao = True
        linha.save(update_fields=["quantidade", "valor", "escolhida_a_mao"])
        mudaram.append(linha.codigo)

    if not pedido.itens.exists():
        # Pedido sem linha nenhuma não é pedido editado, é pedido desistido — e
        # desistir tem caminho próprio, com motivo. Melhor recusar do que deixar um
        # pedido vazio no ar e o fornecedor esperando.
        raise NaoDeuCerto(
            "Um pedido não pode ficar sem nenhum item. Para desistir dele, "
            "use Cancelar o pedido e informe o motivo."
        )

    campos = []
    if prazo_dias is not None and prazo_dias != pedido.prazo_dias:
        pedido.prazo_dias = prazo_dias
        campos.append("prazo_dias")
    if observacao is not None and observacao[:300] != pedido.observacao:
        pedido.observacao = observacao[:300]
        campos.append("observacao")

    if not (mudaram or removidos or campos):
        return pedido, False

    pedido.editado_em = timezone.now()
    pedido.editado_por = usuario if usuario and usuario.is_authenticated else None
    pedido.save(update_fields=[*campos, "editado_em", "editado_por"])
    registrar("pedido.editado", usuario=usuario, recurso=pedido,
              recurso_rotulo=f"pedido {pedido.numero} · {pedido.fornecedor}",
              antes=antes,
              depois={"itens": {linha.codigo: str(linha.quantidade)
                                for linha in pedido.itens.all()},
                      "prazo_dias": pedido.prazo_dias, "observacao": pedido.observacao,
                      "valor": str(pedido.valor_total),
                      "mudaram": mudaram, "removidos": removidos})
    return pedido, True


@transaction.atomic
def cancelar_pedido(usuario, pedido, motivo):
    """Descarta um pedido aberto, com o motivo escrito junto.

    Pedido do Edson em 20/10/2026: *"descartar/cancelar (informar motivo)"*. O motivo é
    obrigatório: pedido cancelado sem motivo é a pergunta "por que este não chegou?" sem
    resposta, três meses depois.

    O pedido NÃO é apagado, e as linhas ficam: é a regra dele de não eliminar histórico,
    e é o que permite ver depois o que se deixou de comprar daquele fornecedor.
    """
    motivo = (motivo or "").strip()
    if not motivo:
        raise NaoDeuCerto("Escreva o motivo do cancelamento.")
    if pedido.foi_cancelado:
        raise NaoDeuCerto(f"O pedido {pedido.numero} já está cancelado.")
    if not pedido.pode_mudar:
        raise NaoDeuCerto(
            "Só pedido em aberto pode ser cancelado. Este pedido já foi "
            f"{pedido.get_situacao_display().lower()}."
        )
    _so_quem_pode(usuario, pedido, "cancelado")

    antes = pedido.situacao
    pedido.situacao = Pedido.Situacao.CANCELADO
    pedido.motivo_cancelamento = motivo[:300]
    pedido.cancelado_em = timezone.now()
    pedido.cancelado_por = usuario if usuario and usuario.is_authenticated else None
    pedido.save(update_fields=["situacao", "motivo_cancelamento", "cancelado_em", "cancelado_por"])
    registrar("pedido.cancelado", usuario=usuario, recurso=pedido,
              recurso_rotulo=f"pedido {pedido.numero} · {pedido.fornecedor}",
              antes={"situacao": antes},
              depois={"situacao": pedido.situacao, "valor": str(pedido.valor_total)},
              motivo=motivo[:300])
    return pedido


def _so_quem_pode(usuario, pedido, como):
    """Depois de aprovado, o pedido só é mudado ou cancelado pela gerência.

    A tela já esconde os botões; isto é para o envio que chega sem passar por ela.
    """
    if usuario is not None and not pedido.pode_ser_mudado_por(usuario):
        raise NaoDeuCerto(
            f"O pedido {pedido.numero} já foi aprovado: agora ele só é {como} pela gerência."
        )


def _quantidade(bruto):
    """O número digitado na tela do pedido, pela MESMA régua da lista de compra.

    Reaproveita `apps.compras.ajustes.quantidade_informada` em vez de ter um segundo
    jeito de ler quantidade: ali está a regra de que vírgula manda e o ponto é milhar,
    com o teto de sanidade e as mensagens prontas. Dois leitores de número em telas que
    pedem a mesma coisa é a origem de "2.5 aqui é dois e meio e lá é vinte e cinco".
    """
    try:
        return ajustes.quantidade_informada(bruto)
    except ajustes.ErroDeAjuste as erro:
        raise NaoDeuCerto(str(erro)) from None


def marcar_recebido(usuario, pedido, recebido=True):
    """Diz que a mercadoria chegou (ou desfaz, quando alguém marcou sem querer)."""
    if pedido.foi_cancelado:
        # Sem esta guarda, "recebido" em cima de um cancelado apagava o cancelamento e
        # deixava o motivo escrito num pedido que a tela mostra como recebido.
        raise NaoDeuCerto(
            f"O pedido {pedido.numero} está cancelado: não dá para marcar como recebido."
        )
    if pedido.esperando_aprovacao:
        # Mercadoria de pedido que ninguém aprovou não devia ter vindo; e "voltar para
        # esperando mercadoria" aprovaria o pedido pela porta dos fundos.
        raise NaoDeuCerto(
            f"O pedido {pedido.numero} ainda espera a aprovação da gerência: só depois "
            "dela a mercadoria pode ser dada como recebida."
        )
    antes = pedido.situacao
    if recebido:
        pedido.situacao = Pedido.Situacao.RECEBIDO
        pedido.recebido_em = timezone.now()
        pedido.recebido_por = usuario if usuario and usuario.is_authenticated else None
    else:
        pedido.situacao = Pedido.Situacao.ABERTO
        pedido.recebido_em = None
        pedido.recebido_por = None
    pedido.save(update_fields=["situacao", "recebido_em", "recebido_por"])
    registrar("pedido.situacao_alterada", usuario=usuario, recurso=pedido,
              recurso_rotulo=f"pedido {pedido.numero} · {pedido.fornecedor}",
              antes={"situacao": antes}, depois={"situacao": pedido.situacao})
    return pedido


def em_aberto():
    """Quantos pedidos esperam mercadoria. Vira tarefa e lembrete nas outras telas."""
    return Pedido.objects.filter(situacao=Pedido.Situacao.ABERTO).count()


def sem_documento():
    """Pedidos recebidos de que ninguém anexou nota nem romaneio.

    É a pergunta que o Edson quer poder responder depois: comprei, chegou, e o papel?
    """
    return (Pedido.objects.filter(situacao=Pedido.Situacao.RECEBIDO)
            .exclude(anexos__tipo__in=(AnexoDoPedido.Tipo.NOTA_FISCAL,
                                       AnexoDoPedido.Tipo.ROMANEIO))
            .count())
