"""Regras do fluxo da base de processos. Toda transição passa por aqui.

As views só chamam estas funções; a regra fica no servidor, não na tela.
Arrastar ou clicar em um cartão não contorna nenhuma verificação.
"""

import re

from django.db import transaction
from django.utils import timezone

from apps.auditoria.servicos import registrar

from .models import Afirmacao, Anexo, ExecucaoTeste, Processo, VersaoProcesso

Estado = Processo.Estado


class RegraViolada(Exception):
    """Ação recusada por regra de negócio. A mensagem é mostrada ao usuário."""


class SemPermissao(RegraViolada):
    pass


# Padrões simples para impedir senha e CPF nos procedimentos (seção 5 e LGPD).
_SENHA = re.compile(r"\b(senha|password|pwd|pin)\b\s*[:=é]\s*\S+", re.IGNORECASE)
_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")

CAMPOS_PARA_TESTE = {
    "objetivo": "objetivo",
    "gatilho": "gatilho",
    "passos": "passos",
    "evidencia_conclusao": "evidência de conclusão",
}


def verificar_texto_seguro(campos):
    """Recusa texto que pareça conter senha ou CPF completo."""
    for nome, valor in campos.items():
        if not isinstance(valor, str):
            continue
        if _SENHA.search(valor):
            raise RegraViolada(
                f"O campo “{nome}” parece conter uma senha. Não registre senhas nos procedimentos; "
                "escreva, por exemplo, “pedir acesso à gerência”."
            )
        if _CPF.search(valor):
            raise RegraViolada(
                f"O campo “{nome}” parece conter um CPF. Use exemplos anonimizados (ex.: CPF ***.***.***-00)."
            )


def _exigir(usuario, permissao):
    if not usuario.has_perm(permissao):
        raise SemPermissao("Seu perfil não permite esta ação. Fale com a gerência se precisar dela.")


def _bloquear(processo):
    """Relê o processo com trava de linha para evitar transições concorrentes."""
    return Processo.objects.select_for_update().get(pk=processo.pk)


def _mudar_estado(processo, novo, usuario, motivo=""):
    anterior = processo.estado
    processo.estado = novo
    registrar(
        "processo.estado_alterado",
        usuario=usuario,
        recurso=processo,
        antes={"estado": anterior},
        depois={"estado": novo},
        motivo=motivo,
    )


@transaction.atomic
def criar_processo(usuario, **dados):
    _exigir(usuario, "processos.documentar_processo")
    verificar_texto_seguro(dados)
    processo = Processo.objects.create(**dados)
    registrar("processo.criado", usuario=usuario, recurso=processo,
              depois={"titulo": processo.titulo, "area": processo.area, "criticidade": processo.criticidade})
    return processo


@transaction.atomic
def atualizar_cadastro(usuario, processo, **dados):
    """Altera título, área, criticidade, responsáveis e prazo (não o procedimento)."""
    _exigir(usuario, "processos.documentar_processo")
    verificar_texto_seguro(dados)
    processo = _bloquear(processo)
    antes, depois = {}, {}
    for campo, valor in dados.items():
        atual = getattr(processo, campo)
        if atual != valor:
            antes[campo] = str(atual) if atual is not None else None
            depois[campo] = str(valor) if valor is not None else None
            setattr(processo, campo, valor)
    if depois:
        processo.save()
        registrar("processo.cadastro_alterado", usuario=usuario, recurso=processo, antes=antes, depois=depois)
    return processo


@transaction.atomic
def salvar_versao(usuario, processo, *, versao_base, resumo_mudanca, **conteudo):
    """Cria uma nova versão do procedimento.

    `versao_base` é o número da versão que a pessoa estava editando. Se outra
    pessoa salvou antes, a edição é recusada para não sobrescrever o trabalho dela.
    Mudar o procedimento depois do teste ou da validação devolve o processo para
    documentação: a versão nova precisa ser testada de novo. A última versão
    validada continua registrada como referência.
    """
    _exigir(usuario, "processos.documentar_processo")
    verificar_texto_seguro({**conteudo, "resumo_mudanca": resumo_mudanca})
    processo = _bloquear(processo)
    atual = processo.versao_atual.numero if processo.versao_atual_id else 0
    if versao_base != atual:
        raise RegraViolada(
            f"Outra pessoa salvou a versão {atual} enquanto você editava a versão {versao_base}. "
            "Abra o processo de novo e refaça sua alteração sobre a versão mais recente."
        )
    if processo.versao_atual_id and all(
        getattr(processo.versao_atual, c) == conteudo.get(c, "") for c in VersaoProcesso.CAMPOS_CONTEUDO
    ):
        raise RegraViolada("Nada mudou em relação à versão atual.")

    versao = VersaoProcesso.objects.create(
        processo=processo, numero=atual + 1, autor=usuario, resumo_mudanca=resumo_mudanca, **conteudo
    )
    processo.versao_atual = versao
    if processo.estado != Estado.EM_DOCUMENTACAO:
        motivo = "Nova versão do procedimento." if processo.estado == Estado.A_LEVANTAR else (
            "Procedimento alterado; a nova versão precisa ser testada e validada de novo."
        )
        _mudar_estado(processo, Estado.EM_DOCUMENTACAO, usuario, motivo)
    # versao_validada continua apontando para a última versão validada, que segue
    # como referência até a nova ser validada.
    processo.save()
    registrar("processo.versao_criada", usuario=usuario, recurso=processo,
              depois={"versao": versao.numero}, motivo=resumo_mudanca)
    return versao


def pendencias_para_teste(processo):
    """Lista o que falta para o processo poder ir para teste."""
    faltas = []
    versao = processo.versao_atual
    if versao is None:
        return ["Escrever a primeira versão do procedimento."]
    for campo, rotulo in CAMPOS_PARA_TESTE.items():
        if not getattr(versao, campo).strip():
            faltas.append(f"Preencher {rotulo}.")
    if not processo.titular_id:
        faltas.append("Definir o responsável titular.")
    if not processo.substituto_id:
        faltas.append("Definir o substituto.")
    if processo.titular_id and processo.titular_id == processo.substituto_id:
        faltas.append("O substituto precisa ser uma pessoa diferente do titular.")
    return faltas


@transaction.atomic
def enviar_para_teste(usuario, processo):
    _exigir(usuario, "processos.documentar_processo")
    processo = _bloquear(processo)
    if processo.estado != Estado.EM_DOCUMENTACAO:
        raise RegraViolada("Só processos em documentação podem ir para teste.")
    faltas = pendencias_para_teste(processo)
    if faltas:
        raise RegraViolada("Antes de enviar para teste: " + " ".join(faltas))
    _mudar_estado(processo, Estado.EM_TESTE, usuario)
    processo.save()
    return processo


@transaction.atomic
def registrar_teste(usuario, processo, *, resultado, usou_somente_documentacao, dificuldades=""):
    _exigir(usuario, "processos.registrar_teste")
    verificar_texto_seguro({"dificuldades": dificuldades})
    processo = _bloquear(processo)
    if processo.estado != Estado.EM_TESTE:
        raise RegraViolada("Este processo não está aguardando teste.")
    versao = processo.versao_atual
    if usuario.pk in (versao.autor_id, processo.titular_id):
        raise RegraViolada(
            "O teste precisa ser feito por outra pessoa, que não escreveu esta versão "
            "e não é a titular do processo."
        )
    if resultado != ExecucaoTeste.Resultado.CONCLUIU and not dificuldades.strip():
        raise RegraViolada("Descreva as dificuldades encontradas.")
    teste = ExecucaoTeste.objects.create(
        processo=processo, versao=versao, executor=usuario, resultado=resultado,
        usou_somente_documentacao=usou_somente_documentacao, dificuldades=dificuldades,
    )
    registrar("processo.teste_registrado", usuario=usuario, recurso=processo,
              depois={"versao": versao.numero, "resultado": resultado,
                      "usou_somente_documentacao": usou_somente_documentacao})
    if not teste.aprovado:
        _mudar_estado(processo, Estado.EM_DOCUMENTACAO, usuario,
                      "O teste não foi concluído só com a documentação; ajuste o procedimento.")
        processo.save()
    return teste


@transaction.atomic
def validar(usuario, processo, observacao=""):
    _exigir(usuario, "processos.validar_processo")
    processo = _bloquear(processo)
    if processo.estado != Estado.EM_TESTE:
        raise RegraViolada("Só processos em teste podem ser validados.")
    teste_ok = processo.testes.filter(versao=processo.versao_atual, usou_somente_documentacao=True).exclude(
        resultado=ExecucaoTeste.Resultado.NAO_CONCLUIU
    )
    if not teste_ok.exists():
        raise RegraViolada(
            "Falta um teste em que outra pessoa concluiu o procedimento usando somente a documentação."
        )
    _mudar_estado(processo, Estado.VALIDADO, usuario, observacao)
    processo.validado_por = usuario
    processo.validado_em = timezone.now()
    processo.versao_validada = processo.versao_atual
    processo.save()
    return processo


@transaction.atomic
def devolver(usuario, processo, motivo):
    _exigir(usuario, "processos.documentar_processo")
    if not motivo.strip():
        raise RegraViolada("Informe o motivo da devolução.")
    processo = _bloquear(processo)
    if processo.estado not in (Estado.EM_TESTE, Estado.VALIDADO):
        raise RegraViolada("Só processos em teste ou validados podem ser devolvidos para documentação.")
    if processo.estado == Estado.VALIDADO:
        # Devolver um processo validado significa que a versão validada não serve mais.
        _exigir(usuario, "processos.validar_processo")
        processo.validado_por = None
        processo.validado_em = None
        processo.versao_validada = None
    _mudar_estado(processo, Estado.EM_DOCUMENTACAO, usuario, motivo)
    processo.save()
    return processo


@transaction.atomic
def registrar_afirmacao(usuario, processo, *, tipo, texto, fonte):
    _exigir(usuario, "processos.documentar_processo")
    verificar_texto_seguro({"texto": texto})
    aprovado_por = None
    if tipo == Afirmacao.Tipo.REGRA:
        _exigir(usuario, "processos.aprovar_regra")
        aprovado_por = usuario
    afirmacao = Afirmacao.objects.create(
        processo=processo, tipo=tipo, texto=texto, fonte=fonte, registrado_por=usuario,
        aprovado_por=aprovado_por,
    )
    registrar("processo.afirmacao_registrada", usuario=usuario, recurso=processo,
              depois={"tipo": tipo, "afirmacao_id": afirmacao.pk})
    return afirmacao


# Tipos aceitos e a assinatura (bytes iniciais) que o conteúdo precisa ter.
TIPOS_ANEXO = {
    "pdf": [b"%PDF-"],
    "png": [b"\x89PNG\r\n\x1a\n"],
    "jpg": [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
    "xlsx": [b"PK\x03\x04"],
    "docx": [b"PK\x03\x04"],
    "csv": None,
    "txt": None,
}


def _validar_arquivo(arquivo, tamanho_maximo):
    nome = arquivo.name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    extensao = nome.rsplit(".", 1)[-1].lower() if "." in nome else ""
    if extensao not in TIPOS_ANEXO:
        raise RegraViolada("Tipo de arquivo não aceito. Envie PDF, PNG, JPG, XLSX, DOCX, CSV ou TXT.")
    if arquivo.size > tamanho_maximo:
        raise RegraViolada(f"O arquivo passa do limite de {tamanho_maximo // (1024 * 1024)} MB.")
    inicio = arquivo.read(16)
    arquivo.seek(0)
    assinaturas = TIPOS_ANEXO[extensao]
    if assinaturas is None:
        if b"\x00" in inicio:
            raise RegraViolada("O conteúdo não parece ser texto. Confira o arquivo.")
    elif not any(inicio.startswith(a) for a in assinaturas):
        raise RegraViolada("O conteúdo do arquivo não corresponde à extensão. Confira o arquivo.")
    return nome[:200], extensao


@transaction.atomic
def anexar(usuario, processo, arquivo, *, descricao, contem_imagem_de_pessoa, autorizacao_registrada,
           tamanho_maximo):
    _exigir(usuario, "processos.documentar_processo")
    nome, extensao = _validar_arquivo(arquivo, tamanho_maximo)
    if contem_imagem_de_pessoa and not autorizacao_registrada:
        raise RegraViolada("Imagens ou gravações com pessoas precisam de autorização registrada antes do envio.")
    sha = Anexo.calcular_sha256(arquivo)
    if processo.anexos.filter(sha256=sha).exists():
        raise RegraViolada("Este arquivo já está anexado a este processo.")
    anexo = Anexo(
        processo=processo, nome_original=nome, tipo=extensao, tamanho=arquivo.size, sha256=sha,
        descricao=descricao, contem_imagem_de_pessoa=contem_imagem_de_pessoa,
        autorizacao_registrada=autorizacao_registrada, enviado_por=usuario,
    )
    anexo.arquivo.save(sha, arquivo, save=False)
    anexo.save()
    registrar("processo.anexo_enviado", usuario=usuario, recurso=processo,
              depois={"anexo_id": anexo.pk, "nome": nome, "sha256": sha, "tamanho": arquivo.size})
    return anexo
