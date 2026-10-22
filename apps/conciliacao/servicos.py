"""Guardar o extrato que alguém trouxe e registrar o que foi conferido.

Toda conferência é de uma pessoa, não do sistema: cada linha conferida guarda quem
conferiu e quando, e o mesmo evento vai para a trilha de auditoria. É dinheiro saindo
da conta da loja; daqui a seis meses alguém vai perguntar quem marcou aquilo.
"""

from django.db import transaction
from django.utils import timezone

from apps.auditoria.servicos import registrar

from . import conferencia, leitores
from .models import ExtratoImportado, LinhaExtrato

TAMANHO_MAXIMO = 5 * 1024 * 1024


class ExtratoRecusado(Exception):
    """O arquivo não entra, e a mensagem é a que a pessoa vai ler na tela."""


def importar(arquivo, usuario, banco=""):
    """Lê o arquivo do banco e guarda o extrato. Devolve o `ExtratoImportado`."""
    if arquivo is None:
        raise ExtratoRecusado("Escolha o arquivo do extrato antes de enviar.")
    if arquivo.size == 0:
        raise ExtratoRecusado("O arquivo está vazio.")
    if arquivo.size > TAMANHO_MAXIMO:
        raise ExtratoRecusado(
            f"O arquivo tem {arquivo.size // 1024} KB e o limite é "
            f"{TAMANHO_MAXIMO // 1024 // 1024} MB. Baixe o extrato de um mês por vez."
        )
    dados = arquivo.read()
    digital = leitores.impressao_digital(dados)
    ja_existe = ExtratoImportado.objects.filter(impressao_digital=digital).first()
    if ja_existe:
        raise ExtratoRecusado(
            f"Este mesmo extrato já foi importado em "
            f"{timezone.localtime(ja_existe.importado_em):%d/%m/%Y às %H:%M}. "
            f"Abra o que já está na lista em vez de importar de novo."
        )

    leitura = leitores.ler(arquivo.name, dados)
    if leitura.erro:
        raise ExtratoRecusado(leitura.erro)
    if not leitura.movimentos:
        raise ExtratoRecusado("O arquivo não tem nenhum movimento legível.")

    with transaction.atomic():
        extrato = ExtratoImportado.objects.create(
            banco=banco.strip() or leitura.banco, conta=leitura.conta,
            arquivo=arquivo.name[:200], formato=leitura.formato,
            periodo_inicio=leitura.inicio, periodo_fim=leitura.fim,
            importado_por=usuario if getattr(usuario, "is_authenticated", False) else None,
            impressao_digital=digital,
        )
        LinhaExtrato.objects.bulk_create([
            LinhaExtrato(
                extrato=extrato, data=m.data, valor=m.valor,
                descricao=m.descricao[:300], documento=m.documento[:60],
                identificador=m.identificador[:120],
            )
            for m in leitura.movimentos
        ])
    registrar("conciliacao.extrato_importado", usuario=usuario, servico="conciliacao",
              recurso=extrato, recurso_rotulo=str(extrato), depois={
                  "arquivo": arquivo.name, "formato": leitura.formato,
                  "movimentos": len(leitura.movimentos), "descartadas": leitura.descartadas,
              })
    extrato.descartadas = leitura.descartadas
    return extrato


def _conta_pelo_codigo(importacao, id_set):
    from apps.financeiro.models import Lancamento

    if importacao is None or not id_set:
        return None
    return Lancamento.objects.filter(
        importacao=importacao, tipo=Lancamento.Tipo.PAGAR, id_set=id_set
    ).first()


def _linha_que_ja_usa(conta, linha):
    """A outra linha do banco já amarrada nesta conta, se houver.

    Uma conta do SET paga UMA saída da conta bancária. Duas linhas amarradas na mesma
    conta somariam o mesmo dinheiro duas vezes em `resumir`, e com isso a tela declararia
    o extrato inteiro conferido enquanto uma retirada de verdade não tem lançamento
    nenhum no SET — que é exatamente o que a conciliação existe para encontrar.
    """
    return (LinhaExtrato.objects
            .filter(situacao=LinhaExtrato.Situacao.CONFERIDA, lancamento_id_set=conta.id_set)
            .exclude(pk=linha.pk)
            .order_by("data", "pk")
            .first())


def conferir(linha, id_set, usuario, importacao):
    """Amarra a linha do banco a uma conta do SET."""
    conta = _conta_pelo_codigo(importacao, id_set)
    if conta is None:
        raise ExtratoRecusado("Essa conta não está na última sincronização do SET.")
    outra = _linha_que_ja_usa(conta, linha)
    if outra is not None:
        raise ExtratoRecusado(
            f"Essa conta do SET já está marcada na saída de {outra.data:%d/%m/%Y}, de "
            f"R$ {outra.valor_absoluto:.2f}. Uma conta paga uma saída só. Se o banco tem "
            "duas saídas iguais e o SET tem uma conta só, falta lançar a outra no SET: "
            "desfaça a outra linha, ou marque esta como \"não é conta do SET\" "
            "anotando o que ela é.")
    candidata = conferencia.Candidata(conta=conta, distancia_em_dias=0)
    linha.situacao = LinhaExtrato.Situacao.CONFERIDA
    linha.lancamento_id_set = conta.id_set
    linha.lancamento_rotulo = candidata.rotulo[:300]
    linha.conferida_em = timezone.now()
    linha.conferida_por = usuario if getattr(usuario, "is_authenticated", False) else None
    linha.save(update_fields=["situacao", "lancamento_id_set", "lancamento_rotulo",
                              "conferida_em", "conferida_por"])
    registrar("conciliacao.linha_conferida", usuario=usuario, servico="conciliacao",
              recurso=linha, recurso_rotulo=str(linha), depois={
                  "data": str(linha.data), "valor": str(linha.valor),
                  "conta_no_set": conta.id_set, "conta": linha.lancamento_rotulo,
              })
    return linha


def conferir_as_obvias(extrato, importacao, usuario):
    """Confirma de uma vez as linhas que têm uma candidata só. Devolve quantas.

    "Uma candidata só" não basta: as candidatas de todas as linhas são lidas de uma vez,
    antes do laço, então duas saídas do mesmo valor podem apontar para A MESMA conta do
    SET e as duas aparecerem como obviedade. A primeira é obviedade; a segunda é
    pergunta, e fica para a pessoa decidir na tela.
    """
    quantas = 0
    usadas = set()
    for confronto in conferencia.confrontar(extrato, importacao):
        if confronto.situacao != "uma":
            continue
        unica = confronto.unica
        if unica.conta.id_set in usadas or unica.ja_usada:
            continue
        conferir(confronto.linha, unica.conta.id_set, usuario, importacao)
        usadas.add(unica.conta.id_set)
        quantas += 1
    return quantas


def marcar_sem_conta(linha, usuario, observacao=""):
    """A saída existe no banco e não tem conta no SET: tarifa, imposto, retirada."""
    linha.situacao = LinhaExtrato.Situacao.SEM_CONTA
    linha.lancamento_id_set = 0
    linha.lancamento_rotulo = ""
    linha.observacao = (observacao or "").strip()[:300]
    linha.conferida_em = timezone.now()
    linha.conferida_por = usuario if getattr(usuario, "is_authenticated", False) else None
    linha.save(update_fields=["situacao", "lancamento_id_set", "lancamento_rotulo",
                              "observacao", "conferida_em", "conferida_por"])
    registrar("conciliacao.linha_sem_conta", usuario=usuario, servico="conciliacao",
              recurso=linha, recurso_rotulo=str(linha),
              depois={"data": str(linha.data), "valor": str(linha.valor),
                      "observacao": linha.observacao})
    return linha


def desfazer(linha, usuario):
    """Volta a linha para pendente. Errar a conferência é normal; não dá para ficar preso."""
    antes = {"situacao": linha.situacao, "conta_no_set": linha.lancamento_id_set,
             "conta": linha.lancamento_rotulo}
    linha.situacao = LinhaExtrato.Situacao.PENDENTE
    linha.lancamento_id_set = 0
    linha.lancamento_rotulo = ""
    linha.observacao = ""
    linha.conferida_em = None
    linha.conferida_por = None
    linha.save(update_fields=["situacao", "lancamento_id_set", "lancamento_rotulo",
                              "observacao", "conferida_em", "conferida_por"])
    registrar("conciliacao.conferencia_desfeita", usuario=usuario, servico="conciliacao",
              recurso=linha, recurso_rotulo=str(linha), antes=antes)
    return linha


def apagar(extrato, usuario):
    """Apaga um extrato inteiro, com as linhas e as conferências dele."""
    rotulo = str(extrato)
    registrar("conciliacao.extrato_apagado", usuario=usuario, servico="conciliacao",
              recurso_rotulo=rotulo, antes={"arquivo": extrato.arquivo,
                                            "linhas": extrato.linhas.count()})
    extrato.delete()
    return rotulo
