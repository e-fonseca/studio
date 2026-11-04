"""Execução da importação e leitura do estado dos dados.

A importação é sempre: achar o arquivo de origem, fazer uma cópia própria, ler a
cópia, gravar a foto no banco do sistema e registrar o resultado. Se qualquer
passo falhar, a importação fica marcada como falhou com o motivo, e os dados da
importação anterior continuam valendo -- o painel nunca mostra meia foto.
"""

import logging
import threading
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import connection as db_connection, transaction
from django.utils import timezone

from apps.auditoria.servicos import registrar
from apps.core import versao

from . import diagnostico
from .conferencia import conferir, localizar_backup, momento_do_arquivo  # noqa: F401
from .fontes import firebird
from .fontes.firebird import ErroFonte
from .models import (CompraImportada, Importacao, ItemCompraImportada, ItemVendaImportada,
                     ProdutoImportado, VendaImportada, VendaMensalDoProduto)

registrador = logging.getLogger(__name__)


def _conf(nome, padrao=None):
    return getattr(settings, nome, padrao)


ROTULOS_DETALHE = {
    "fornecedores_com_prazo": "fornecedores com prazo de entrega próprio",
    "prazo_geral_dias": "prazo médio da loja, em dias",
    "compras_mes": "meses com compra apurados",
    "produtos_com_pedido_em_aberto": "produtos com pedido de compra em aberto",
    "compras_com_prazo_medido": "compras com data de pedido e de entrega",
    "compras_com_entrega_no_mesmo_dia": "compras com entrega no mesmo dia do pedido",
    "itens_de_compra_sem_cabecalho": "itens de compra sem cabeçalho (ignorados)",
    "itens_de_venda_sem_cabecalho": "itens de venda sem cabeçalho (ignorados)",
    "vendas_mes": "meses com venda apurados",
    "bytes_fora_da_tabela_de_caracteres": "caracteres do SET fora da tabela (descartados)",
    "lancamentos_financeiros": "lançamentos do financeiro lidos",
    "financeiro_desde": "pago e recebido lidos do SET desde",
    "contas_a_pagar_em_aberto": "contas a pagar em aberto",
    "contas_a_receber_em_aberto": "contas a receber em aberto",
    "clientes_cadastrados": "clientes cadastrados (sem o cliente do balcão)",
    "clientes_com_compra_12m": "clientes com compra nos últimos 12 meses",
    "fichas_de_fornecedor": "fichas de fornecedor lidas do cadastro do SET",
    "compras_importadas": "compras do SET lidas uma a uma",
    "vendas_importadas": "vendas do SET lidas uma a uma (12 meses)",
    "itens_de_venda_importados": "produtos vendidos lidos um a um (12 meses)",
    "itens_de_venda_sem_custo": "produtos vendidos sem o custo gravado no SET",
    "itens_de_venda_com_custo_estimado": "desses, os que o cadastro ainda sabe o custo (estimativa)",
    "vendas_com_vendedor": "vendas com o vendedor preenchido no SET",
    "produtos_com_codigo_de_barras": "produtos com código de barras no SET",
    "caixas_importados": "turnos de caixa lidos do SET",
    "caixas_abertos": "turnos de caixa ainda abertos no SET",
}


def _resumo_do_detalhe(detalhe):
    """Linhas curtas para o log. Lista grande entra como contagem, não despejada inteira.

    Quem lê o log é alguém conferindo a importação, não um programa: a tabela
    mês a mês já está no painel, aqui basta saber quantos meses entraram.
    """
    linhas = []
    for chave, valor in sorted((detalhe or {}).items()):
        rotulo = ROTULOS_DETALHE.get(chave, chave)
        if isinstance(valor, (list, tuple, dict)):
            linhas.append(f"{rotulo}: {len(valor)}")
        else:
            linhas.append(f"{rotulo}: {valor}")
    return linhas


def _depois_de_concluir(importacao, *, usuario, extracao, automatica, forcar):
    """Os passos de DEPOIS de a foto estar gravada e já valendo para a loja.

    Por que cada passo se protege por conta própria: estes passos rodavam dentro do
    `try` da importação, e o `except` dele APAGA a foto e marca FALHOU. Então uma falha
    ao escrever a linha da auditoria, ou um tempo esgotado ao podar as fotos velhas —
    que é um DELETE em massa sobre oito tabelas —, apagava a foto boa que acabara de ser
    gravada e dizia que a importação falhou. Pior: a poda já tinha tirado as fotos
    anteriores, então a loja ficava sem dado nenhum, nem o novo nem o velho.

    A foto, aqui, já está gravada e commitada. Nada deste arquivo tem o direito de
    desfazê-la por causa de um passo de arrumação.
    """
    try:
        registrar("importacao.concluida", usuario=usuario, servico="importacao",
                  recurso=importacao, depois={
                      "arquivo": Path(importacao.arquivo).name,
                      "data_corte": extracao.data_corte.isoformat(),
                      "produtos": len(extracao.produtos),
                      "automatica": automatica,
                      "forcada": forcar,
                  })
    except Exception:  # noqa: BLE001 - ver o cabeçalho
        registrador.exception("Não consegui registrar na auditoria a importação %s",
                              importacao.pk)
    try:
        limpar_antigas()
    except Exception:  # noqa: BLE001 - ver o cabeçalho
        registrador.exception("Não consegui apagar as fotos antigas depois da importação %s",
                              importacao.pk)
    _adiantar_o_painel(importacao)


def _adiantar_o_painel(importacao, registrar_em=None):
    """Deixa as contas da abertura prontas, para quem entrar não esperar por elas.

    `registrar_em` é onde a linha do log vai parar, quando não é a mesma foto que foi
    aquecida: sem backup novo, quem continua valendo é a foto ANTERIOR, mas o log é da
    execução de agora — escrever no registro de ontem seria mexer no passado.

    São ~2,2 s sobre onze mil produtos, e quem esperava por elas era justamente quem
    tinha acabado de digitar a senha, porque a primeira tela depois de entrar (a Visão
    geral até a 1.42.0, o Dashboard desde a 1.43.0) mostra estas contas. Ver
    apps/painel/aquecer.py.

    **Tudo aqui dentro é engolido, inclusive a importação do módulo.** Esta função é
    chamada no fim de `executar`, de dentro do `try` cujo `except` APAGA os produtos,
    os lançamentos, os clientes e os caixas que a importação acabou de gravar — e isso
    depois de `limpar_antigas()` já ter podado as fotos anteriores. Um ImportError aqui
    transformaria uma importação boa numa loja sem dado nenhum. Tela lenta é um
    aborrecimento; isso seria um desastre.
    """
    try:
        from apps.painel.aquecer import aquecer  # noqa: PLC0415 - evita importação circular

        gasto = aquecer(importacao)
        onde = registrar_em if registrar_em is not None else importacao
        if gasto:
            onde.anotar(f"Contas do painel adiantadas em {gasto:.1f}s: quem abrir "
                        "o sistema já encontra a tela pronta.")
            onde.save(update_fields=["log"])
    except Exception:  # noqa: BLE001 - ver o parágrafo acima
        registrador.exception("Não consegui adiantar as contas do painel da importação %s",
                              importacao.pk)


def executar(*, origem=Importacao.Origem.BANCO, arquivo=None, usuario=None, automatica=False,
             forcar=False):
    """Roda a importação e devolve o registro, concluído ou com a falha anotada.

    `forcar` é o botão "Forçar atualização com o último backup" da tela de
    importações: lê o backup mais recente de novo mesmo que ele seja o mesmo da
    importação anterior, em vez de terminar como Sem backup novo. Forçar não é
    somar: a leitura grava uma foto nova e as telas passam a ler só ela, então
    reler o mesmo backup tem que dar exatamente os mesmos números. Forçar
    também não passa por cima de arquivo quebrado -- aí o sistema trocaria
    número bom por número pela metade.
    """
    if origem != Importacao.Origem.BANCO:
        raise ErroFonte("Por enquanto a importação automática lê a cópia do banco. Relatórios entram como plano B.")

    importacao = Importacao.objects.create(
        origem=origem,
        situacao=Importacao.Situacao.EM_ANDAMENTO,
        automatica=automatica,
        acionada_por=usuario if getattr(usuario, "is_authenticated", False) else None,
        forcada=forcar,
        etapa="Procurando o backup",
        progresso=5,
        versao_sistema=versao.atual().curta[:40],
    )
    quem = "tarefa automática" if automatica else (
        getattr(usuario, "get_username", lambda: "sistema")() if usuario else "sistema"
    )
    importacao.anotar(
        f"Importação {'forçada' if forcar else 'iniciada'} por {quem}. "
        f"Versão do sistema {importacao.versao_sistema}."
    )
    importacao.save(update_fields=["log"])

    def marcar(etapa, progresso):
        """Mostra em que pé está a importação. É o que a barra da tela acompanha.

        A mesma chamada alimenta a barra de progresso e o log da execução, para
        que depois se possa reconstruir onde a importação demorou ou parou.
        """
        importacao.etapa = etapa[:60]
        importacao.progresso = progresso
        importacao.anotar(f"{etapa} ({progresso}%)")
        importacao.save(update_fields=["etapa", "progresso", "log"])

    anterior = ultima_concluida()
    try:
        # Tanto o --arquivo quanto a configuração aceitam um arquivo ou a pasta onde o
        # backup é salvo; sendo pasta, vale sempre o arquivo mais novo dela.
        alvo = arquivo or _conf("IMPORTACAO_BACKUP_ORIGEM")
        if not alvo:
            raise ErroFonte(
                "Não sei onde está o backup do SET. Informe a pasta em CABANA_SET_BACKUP "
                "(config\\cabana.env) ou passe --arquivo."
            )
        # Conferir tamanho e data ANTES de ler: é o que diz se o arquivo é mesmo o
        # backup mais recente e se ele está inteiro. A conferência inteira vai para o
        # log, inclusive quando passa, para depois dar para conferir o que foi visto.
        conferencia = conferir(alvo, anterior=anterior)
        for linha in conferencia.linhas_para_log():
            importacao.anotar(linha)
        importacao.save(update_fields=["log"])
        if not conferencia.achou:
            indicado = Path(alvo)
            raise ErroFonte(
                f"Não encontrei nenhum backup em {indicado}."
                if indicado.is_dir() else
                f"Não encontrei o arquivo de origem: {indicado}"
            )
        caminho = conferencia.caminho
        if not conferencia.pode_importar(forcar):
            raise ErroFonte(
                f"A conferência do backup não deixou importar: {conferencia.por_que_nao(forcar)}"
            )
        if not caminho.is_file():
            raise ErroFonte(f"Não encontrei o arquivo de origem: {caminho}")
        importacao.arquivo = str(caminho)[:500]
        importacao.arquivo_modificado_em = conferencia.modificado_em
        importacao.arquivo_bytes = conferencia.bytes
        importacao.anotar(
            f"Backup escolhido: {caminho} "
            f"({importacao.arquivo_bytes / 1048576:.1f} MB, gravado em "
            f"{timezone.localtime(importacao.arquivo_modificado_em):%d/%m/%Y %H:%M})."
        )
        importacao.save(update_fields=["arquivo", "arquivo_modificado_em", "arquivo_bytes", "log"])

        # Backup do mesmo arquivo e da mesma data: não há o que importar de novo. Os dados
        # anteriores continuam valendo e o painel segue avisando a idade deles.
        #
        # A versão do sistema entra na conta porque o backup é só metade da pergunta: a
        # outra metade é o que o programa sabe ler dele. Quando a atualização acrescenta
        # uma tabela nova — foi o caso dos caixas na 1.19.0 —, a foto anterior não tem
        # aquele dado, e pular por "backup igual" deixaria a tela nova vazia até o SET
        # gerar um backup diferente. Versão nova relê o mesmo backup uma vez.
        mesmo_backup = anterior is not None and (
            anterior.arquivo == importacao.arquivo
            and anterior.arquivo_modificado_em == importacao.arquivo_modificado_em
            and anterior.arquivo_bytes == importacao.arquivo_bytes
        )
        if mesmo_backup and forcar:
            importacao.anotar(
                "Forçada: o backup é o mesmo da importação anterior e vai ser lido de novo. "
                "A leitura grava uma foto nova e as telas passam a ler só ela, então os "
                "números têm que dar iguais aos da anterior: sincroniza, não soma."
            )
            importacao.save(update_fields=["log"])
            mesmo_backup = False
        if mesmo_backup and anterior.versao_sistema != importacao.versao_sistema:
            importacao.anotar(
                f"O backup é o mesmo da importação anterior, mas o sistema mudou da versão "
                f"{anterior.versao_sistema or '—'} para a {importacao.versao_sistema}: "
                f"lendo de novo para a foto ter tudo o que a versão nova sabe ler."
            )
            importacao.save(update_fields=["log"])
            mesmo_backup = False
        if mesmo_backup:
            importacao.situacao = Importacao.Situacao.SEM_NOVIDADE
            importacao.concluida_em = timezone.now()
            importacao.etapa = "Sem backup novo"
            importacao.progresso = 100
            importacao.data_corte = anterior.data_corte
            importacao.mensagem = (
                f"O backup não mudou desde a importação anterior "
                f"({timezone.localtime(anterior.iniciada_em):%d/%m/%Y %H:%M}). Nada a atualizar."
            )
            importacao.anotar(importacao.mensagem)
            importacao.save()
            # Sem backup novo, quem continua valendo é a foto ANTERIOR — e é ela que
            # as telas vão ler. Adiantar as contas dela aqui é o que faz diferença no
            # dia a dia: a chave carrega o DIA, e o backup do SET costuma ser um por
            # noite, então as sincronizações das 12:30 e das 19:30 quase sempre caem
            # aqui. Sem isto, a primeira pessoa de cada dia pagaria a conta inteira.
            _adiantar_o_painel(anterior, registrar_em=importacao)
            return importacao

        copia = firebird.preparar_copia(
            caminho,
            _conf("IMPORTACAO_PASTA_TRABALHO", Path(settings.BASE_DIR) / "var" / "copia-set"),
            cliente_gbak=_conf("IMPORTACAO_FIREBIRD_GBAK"),
            progresso=marcar,
        )
        extracao = firebird.extrair(
            copia, biblioteca_cliente=_conf("IMPORTACAO_FIREBIRD_CLIENTE"), progresso=marcar,
        )

        marcar("Gravando os produtos", 90)
        # Importado aqui, e não no topo, porque financeiro e clientes dependem de
        # importacao.models: no topo o Django ainda não terminou de carregar os apps.
        from apps.caixa.models import CaixaImportado, MovimentoCaixa
        from apps.clientes.models import ClienteImportado
        from apps.financeiro.models import Lancamento
        from apps.fornecedores.models import FornecedorImportado

        with transaction.atomic():
            ProdutoImportado.objects.bulk_create(
                [ProdutoImportado(importacao=importacao, **dados) for dados in extracao.produtos],
                batch_size=1000,
            )
            Lancamento.objects.bulk_create(
                [Lancamento(importacao=importacao, **dados) for dados in extracao.lancamentos],
                batch_size=1000,
            )
            ClienteImportado.objects.bulk_create(
                [ClienteImportado(importacao=importacao, **dados) for dados in extracao.clientes],
                batch_size=1000,
            )
            FornecedorImportado.objects.bulk_create(
                [FornecedorImportado(importacao=importacao, **dados)
                 for dados in extracao.fichas_fornecedor],
                batch_size=1000,
            )
            _gravar_compras(importacao, extracao.compras)
            _gravar_caixas(importacao, extracao.caixas, CaixaImportado, MovimentoCaixa)
            _gravar_vendas(importacao, extracao.vendas)
            _gravar_vendas_por_mes(importacao, extracao.vendas_por_mes)
            importacao.data_corte = extracao.data_corte
            importacao.mes_a_mes_desde = extracao.mes_a_mes_desde
            importacao.produtos = len(extracao.produtos)
            importacao.dias_abertos_12m = extracao.dias_abertos_12m
            importacao.dias_abertos_90d = extracao.dias_abertos_90d
            importacao.detalhe = extracao.detalhe
            importacao.situacao = Importacao.Situacao.CONCLUIDA
            importacao.concluida_em = timezone.now()
            importacao.etapa = "Concluída"
            importacao.progresso = 100
            importacao.mensagem = (
                f"{len(extracao.produtos)} produtos, dados até {extracao.data_corte:%d/%m/%Y}."
            )
            for linha in _resumo_do_detalhe(extracao.detalhe):
                importacao.anotar(linha)
            importacao.anotar(
                f"Concluída: {len(extracao.produtos)} produtos gravados, dados até "
                f"{extracao.data_corte:%d/%m/%Y}, {extracao.dias_abertos_12m} dias com venda em 12 meses. "
                f"Duração {int((timezone.now() - importacao.iniciada_em).total_seconds())}s."
            )
            importacao.save()

        _depois_de_concluir(importacao, usuario=usuario, extracao=extracao,
                            automatica=automatica, forcar=forcar)
        return importacao
    except Exception as erro:  # noqa: BLE001 - qualquer falha precisa ficar registrada e visível
        registrador.exception("Importação %s falhou", importacao.pk)
        _apagar_a_foto(importacao)
        importacao.situacao = Importacao.Situacao.FALHOU
        importacao.concluida_em = timezone.now()
        importacao.etapa = "Parou com erro"
        importacao.mensagem = str(erro)[:2000]
        importacao.anotar(f"ERRO ({type(erro).__name__}): {erro}")
        importacao.anotar("Os dados da importação anterior continuam valendo.")
        importacao.save()
        registrar("importacao.falhou", usuario=usuario, servico="importacao", recurso=importacao,
                  resultado="falha", motivo=str(erro)[:500])
        return importacao


def em_andamento(minutos_limite=60):
    """Importação que já começou e ainda não terminou. Evita duas rodando juntas."""
    limite = timezone.now() - timedelta(minutes=minutos_limite)
    return (
        Importacao.objects.filter(situacao=Importacao.Situacao.EM_ANDAMENTO, iniciada_em__gte=limite)
        .order_by("-iniciada_em")
        .first()
    )


def executar_em_segundo_plano(*, usuario=None, arquivo=None, forcar=False):
    """Dispara a importação numa thread para a tela não ficar presa esperando.

    Ler a cópia leva minutos; quem clicou volta para o painel e acompanha o
    estado ali. A thread fecha a própria conexão com o banco ao terminar.
    """
    def tarefa():
        try:
            executar(usuario=usuario, arquivo=arquivo, forcar=forcar)
        finally:
            db_connection.close()

    thread = threading.Thread(target=tarefa, name="importacao-set", daemon=True)
    thread.start()
    return thread


def _gravar_compras(importacao, compras):
    """Grava cabeçalho e itens das compras em dois lotes, para não fazer uma consulta por item."""
    cabecalhos = []
    for dados in compras:
        dados = dict(dados)
        dados.pop("linhas", None)
        cabecalhos.append(CompraImportada(importacao=importacao, **dados))
    CompraImportada.objects.bulk_create(cabecalhos, batch_size=500)
    por_id = {compra.id_set: compra for compra in cabecalhos}
    itens = [
        ItemCompraImportada(compra=por_id[dados["id_set"]], **linha)
        for dados in compras
        for linha in dados.get("linhas", ())
    ]
    ItemCompraImportada.objects.bulk_create(itens, batch_size=1000)
    return len(cabecalhos), len(itens)



def _gravar_vendas(importacao, vendas):
    """Grava cabeçalho e itens das vendas em dois lotes, como nas compras.

    O bulk_create do PostgreSQL devolve as chaves, então o item encontra a sua venda sem
    uma consulta por linha: são 16 mil vendas e 32 mil itens em 12 meses.

    O item é casado com a venda pela ORDEM da lista, e não pelo id_set: o bulk_create
    devolve na mesma ordem que recebeu, e id_set pode repetir ou vir vazio em venda velha
    do SET — casar por ele penduraria o item na venda errada.
    """
    cabecalhos = []
    for dados in vendas:
        cabecalhos.append(VendaImportada(
            importacao=importacao,
            **{chave: valor for chave, valor in dados.items() if chave != "linhas"},
        ))
    VendaImportada.objects.bulk_create(cabecalhos, batch_size=1000)
    anteriores = _tabela_de_antes(importacao)
    itens = []
    for venda, dados in zip(cabecalhos, vendas):
        for linha in dados.get("linhas", ()):
            if linha.get("preco_tabela_do_cadastro") and dados.get("id_set", 0) > 0:
                antes = anteriores.get((dados["id_set"], linha["codigo"]))
                if antes is not None:
                    linha = {**linha, "preco_tabela": antes}
            itens.append(ItemVendaImportada(venda=venda, **linha))
    ItemVendaImportada.objects.bulk_create(itens, batch_size=1000)
    return len(cabecalhos), len(itens)


def _tabela_de_antes(importacao):
    """O preço de tabela que a importação anterior tirou do cadastro, item a item.

    Desde julho de 2026 o SET não grava o preço de tabela na venda, e o sistema usa o do
    cadastro (1.46.0). Mas cada importação lê o cadastro DE NOVO: se o preço do produto
    subiu na semana seguinte, a venda da semana passada pareceria vendida com desconto.
    Na cópia de 20/09/2026, nos itens de junho que ainda tinham o preço gravado, o
    cadastro de hoje dava 235 cortes de preço onde houve 73.

    Por isso o preço do cadastro fica o da PRIMEIRA importação que viu a venda — horas
    depois dela, com a importação três vezes ao dia — e passa de uma foto para a seguinte.
    """
    anterior = (Importacao.objects.filter(situacao=Importacao.Situacao.CONCLUIDA)
                .exclude(pk=importacao.pk).first())
    if anterior is None:
        return {}
    return {
        (id_venda, codigo): preco
        for id_venda, codigo, preco in ItemVendaImportada.objects
        .filter(venda__importacao=anterior, preco_tabela_do_cadastro=True, preco_tabela__isnull=False)
        .values_list("venda__id_set", "codigo", "preco_tabela")
        if id_venda and id_venda > 0
    }


def _gravar_vendas_por_mes(importacao, linhas):
    """Grava a venda de cada produto em cada mês, que é a base da comparação com o ano passado."""
    VendaMensalDoProduto.objects.bulk_create(
        [VendaMensalDoProduto(importacao=importacao, **dados) for dados in linhas],
        batch_size=2000,
    )
    return len(linhas)


def _gravar_caixas(importacao, caixas, modelo_caixa, modelo_movimento):
    """Grava os turnos e, depois, os movimentos que não são venda.

    Em dois passos porque o movimento precisa do id do turno já gravado: o
    bulk_create do PostgreSQL devolve as chaves, então não é preciso reconsultar.
    """
    linhas = []
    for dados in caixas:
        lancamentos = dados.pop("lancamentos", [])
        linhas.append((modelo_caixa(importacao=importacao, **dados), lancamentos))
    gravados = modelo_caixa.objects.bulk_create([caixa for caixa, _ in linhas], batch_size=500)
    movimentos = []
    for caixa, lancamentos in zip(gravados, [l for _, l in linhas]):
        movimentos.extend(modelo_movimento(caixa=caixa, **dados) for dados in lancamentos)
    modelo_movimento.objects.bulk_create(movimentos, batch_size=1000)

def _modelos_da_foto():
    """Onde a foto de uma importação fica guardada, com o nome de cada parte.

    Uma lista só, porque três lugares precisam dela e já andaram separados: a limpeza
    automática, a conferência (`manage.py higienizar`) e o desfazer da importação que
    falhou. Separados, saiu caro: o caixa ficou fora da limpeza e as fotos dos turnos,
    950 por importação, nunca saíam do banco; e o desfazer deixava para trás as compras,
    as vendas, os fornecedores e a venda mês a mês.

    Os itens da compra, os itens da venda e os movimentos do caixa saem pela cascata do
    banco junto com a linha de cima; por isso não estão aqui.
    """
    from apps.caixa.models import CaixaImportado
    from apps.clientes.models import ClienteImportado
    from apps.financeiro.models import Lancamento
    from apps.fornecedores.models import FornecedorImportado

    return (
        ("produtos", ProdutoImportado),
        ("contas", Lancamento),
        ("clientes", ClienteImportado),
        ("fornecedores", FornecedorImportado),
        ("compras", CompraImportada),
        ("vendas", VendaImportada),
        ("turnos do caixa", CaixaImportado),
        ("vendas por mês do produto", VendaMensalDoProduto),
    )


def _apagar_a_foto(importacao):
    """Apaga tudo o que esta importação gravou. É o desfazer de quem parou no meio."""
    for _, modelo in _modelos_da_foto():
        modelo.objects.filter(importacao=importacao).delete()


def fotos_fora_do_limite(manter=None):
    """As fotos do SET que passaram do limite: uma consulta para cada tipo de dado.

    Devolve as consultas em vez de apagar, para a limpeza automática e a
    conferência (`manage.py higienizar`) trabalharem com a MESMA lista.
    """
    manter = manter or _conf("IMPORTACAO_MANTER", 10)
    ids_recentes = list(
        Importacao.objects.filter(situacao=Importacao.Situacao.CONCLUIDA)
        .order_by("-iniciada_em", "-id")
        .values_list("id", flat=True)[:manter]
    )
    fora = [(rotulo, modelo.objects.exclude(importacao_id__in=ids_recentes))
            for rotulo, modelo in _modelos_da_foto()]
    return ids_recentes, fora


def limpar_antigas(manter=None):
    """Mantém as últimas importações e apaga a foto das mais velhas (o registro fica)."""
    ids_recentes, fora = fotos_fora_do_limite(manter)
    for _, consulta in fora:
        consulta.delete()
    return len(ids_recentes)


def ultima_concluida():
    return Importacao.objects.filter(situacao=Importacao.Situacao.CONCLUIDA).first()


def ultima_tentativa():
    return Importacao.objects.first()


def ultima_com_explicacao(minutos_aviso=15):
    """Última tentativa de importação, para avisar como ela terminou.

    "recente" é o que decide se a tela mostra o aviso de conclusão: passado esse
    tempo, o resultado já foi visto e o aviso só atrapalha.
    """
    ultima = ultima_tentativa()
    if ultima is None or ultima.situacao == Importacao.Situacao.EM_ANDAMENTO:
        return None
    fim = ultima.concluida_em or ultima.iniciada_em
    return {
        "importacao": ultima,
        "recente": (timezone.now() - fim) <= timedelta(minutes=minutos_aviso),
        "deu_certo": ultima.situacao != Importacao.Situacao.FALHOU,
        "explicacao": (
            diagnostico.explicar(ultima.mensagem)
            if ultima.situacao == Importacao.Situacao.FALHOU else None
        ),
    }


@dataclass
class EstadoDados:
    """Como está a informação que o painel mostra, em linguagem de loja."""

    nivel: str  # "ok", "atencao", "vencido", "sem_dados"
    titulo: str
    detalhe: str
    importacao: object = None
    falha_posterior: object = None
    idade_dias: int = None

    @property
    def avisar(self):
        return self.nivel != "ok"


def estado_dos_dados(hoje=None):
    """Monta o aviso de atualização dos dados, que aparece no painel e no topo das páginas."""
    hoje = hoje or timezone.localdate()
    atencao = _conf("IMPORTACAO_DIAS_ATENCAO", 2)
    vencido = _conf("IMPORTACAO_DIAS_VENCIDO", 4)

    ultima = ultima_concluida()
    tentativa = ultima_tentativa()
    falha = tentativa if tentativa and tentativa.situacao == Importacao.Situacao.FALHOU and (
        ultima is None or tentativa.iniciada_em > ultima.iniciada_em
    ) else None

    if ultima is None:
        if falha is not None:
            return EstadoDados(
                nivel="sem_dados",
                titulo="Nenhum dado importado ainda",
                detalhe=f"A última tentativa falhou: {falha.mensagem}",
                falha_posterior=falha,
            )
        return EstadoDados(
            nivel="sem_dados",
            titulo="Nenhum dado importado ainda",
            detalhe="Assim que a primeira importação da cópia do banco rodar, os números aparecem aqui.",
        )

    idade = ultima.idade_dos_dados(hoje)
    quando = timezone.localtime(ultima.concluida_em or ultima.iniciada_em)
    if idade is None:
        nivel, titulo = "atencao", "Importação sem data de corte"
    elif idade <= 1:
        nivel, titulo = "ok", f"Dados de {ultima.data_corte:%d/%m/%Y}"
    elif idade < vencido:
        nivel, titulo = "atencao", f"Dados de {ultima.data_corte:%d/%m/%Y}, {idade} dias atrás"
    else:
        nivel, titulo = "vencido", f"Dados de {ultima.data_corte:%d/%m/%Y}, {idade} dias atrás"

    detalhe = f"Importado em {quando:%d/%m/%Y às %H:%M} a partir de {Path(ultima.arquivo).name or 'arquivo'}."
    if falha is not None:
        nivel = "vencido" if nivel == "vencido" else "atencao"
        detalhe += f" A importação seguinte falhou: {falha.mensagem}"
    elif nivel == "vencido":
        detalhe += " Confira se o backup do SET está rodando antes de decidir compra por estes números."
    elif nivel == "atencao" and idade is not None and idade >= atencao:
        detalhe += " A importação de ontem não trouxe movimento novo."

    return EstadoDados(nivel=nivel, titulo=titulo, detalhe=detalhe, importacao=ultima,
                       falha_posterior=falha, idade_dias=idade)
