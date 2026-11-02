"""O catálogo das permissões do Aux SET: o que cada uma abre, em português.

Pedido de 02/11/2026 (prompt de controle de acesso): "Criar permissões por recurso e ação,
com códigos estáveis. Adapte o catálogo aos módulos reais. Não criar permissões sem
aplicação efetiva no backend."

O código de cada permissão é o do Django (`app.codigo`) e não muda: é ele que as telas
conferem no servidor (`permission_required`, `has_perm`). O que este arquivo acrescenta é
o que a gerência precisa para decidir sem programador: o nome em português, o que a
permissão abre, e duas marcas que valem regra:

- **dinheiro**: mostra ou mexe em custo, valor, lucro, conta a pagar, caixa ou banco.
- **administracao**: dá poder sobre acessos, configurações ou segredos guardados.

Quem administra acessos só dá, tira ou mexe em quem tem permissão com uma dessas marcas
se ele mesmo tiver a permissão (`apps/contas/autorizacao.py`). O motivo: quem cria a
conta também define a senha dela, e aí tudo o que ele pudesse dar a outro, ele teria
para si numa conta de fachada.

Dois testes amarram o catálogo ao código (`apps/contas/tests/test_catalogo.py`): toda
permissão conferida por alguma tela está aqui, e toda permissão daqui é conferida por
alguma tela. Permissão que não protege nada não entra.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Permissao:
    codigo: str
    modulo: str
    nome: str
    abre: str
    dinheiro: bool = False
    administracao: bool = False

    @property
    def marcada(self):
        """Só quem tem esta permissão pode dá-la a outra pessoa."""
        return self.dinheiro or self.administracao


# A ordem dos módulos é a do menu de cima, e Acessos por último.
MODULOS = (
    "Indicadores",
    "Compras",
    "Pedidos",
    "Fornecedores",
    "Vendas",
    "Estoque",
    "Dinheiro",
    "Base de processos",
    "Tempo",
    "Sistema",
    "Acessos",
)

CATALOGO = (
    # Indicadores --------------------------------------------------------------------
    Permissao("importacao.ver_painel", "Indicadores", "Ver os indicadores",
              "Dashboard, Visão geral, indicadores de compra, painel completo e o "
              "histórico de versões, que cita os números de cada conserto.", dinheiro=True),
    # Compras ------------------------------------------------------------------------
    Permissao("compras.ver_compras", "Compras", "Ver a lista de compra",
              "Antes de comprar, lista de compra com a folha para o fornecedor, sugestões "
              "do sistema, últimas compras e comparar com o ano passado.", dinheiro=True),
    Permissao("compras.ajustar_compra", "Compras", "Mudar a lista de compra",
              "Quantidade à mão, regra do alerta e carros-chefe. Vale para todo mundo e não "
              "passa por aprovação.", dinheiro=True),
    Permissao("compras.sugerir_compra", "Compras", "Sugerir compra",
              "Anotar o que o cliente pediu e a loja não tinha."),
    Permissao("compras.responder_sugestao", "Compras", "Responder as sugestões da equipe",
              "Dizer se vai comprar o que a equipe sugeriu."),
    # Pedidos ------------------------------------------------------------------------
    Permissao("pedidos.view_pedido", "Pedidos", "Ver pedidos e receber mercadoria",
              "Os pedidos ao fornecedor, com os valores, a folha de cada um e a conferência "
              "da nota.", dinheiro=True),
    Permissao("pedidos.anexar_documento", "Pedidos", "Anexar nota e romaneio",
              "Anexar documentos ao pedido e marcar que a mercadoria chegou."),
    Permissao("pedidos.registrar_pedido", "Pedidos", "Fazer pedido ao fornecedor",
              "Montar o pedido. Sem a permissão de aprovar, ele nasce esperando a gerência.",
              dinheiro=True),
    Permissao("pedidos.aprovar_pedido", "Pedidos", "Aprovar pedido",
              "Fazer valer o pedido que outra pessoa montou. Quem aprova também faz pedido "
              "que já nasce aprovado.", dinheiro=True),
    # Fornecedores -------------------------------------------------------------------
    Permissao("fornecedores.view_fornecedor", "Fornecedores", "Ver fornecedores",
              "Lista, ficha e produtos de cada fornecedor, com o que a loja comprou dele.",
              dinheiro=True),
    Permissao("fornecedores.change_fornecedor", "Fornecedores", "Mudar a ficha do fornecedor",
              "Prazo de entrega, estrelas e o documento que ele emite."),
    # Vendas -------------------------------------------------------------------------
    Permissao("importacao.ver_vendas", "Vendas", "Ver as vendas",
              "Vendas do dia, com a planilha, e ticket médio.", dinheiro=True),
    Permissao("importacao.ver_margem", "Vendas", "Ver custo e margem",
              "Margem e lucro de cada produto, com a planilha.", dinheiro=True),
    Permissao("clientes.ver_clientes", "Vendas", "Ver clientes",
              "Quem compra, quanto e quando.", dinheiro=True),
    # Estoque ------------------------------------------------------------------------
    Permissao("importacao.consultar_produtos", "Estoque", "Consulta de balcão",
              "Produto, estoque e fornecedor, sem custo e sem valores."),
    Permissao("inventario.contar_estoque", "Estoque", "Contar o estoque",
              "Contagem pelo celular ou pelo leitor."),
    Permissao("inventario.fechar_contagem", "Estoque", "Fechar contagem e organizar",
              "Fechar a contagem, tirar a lista de ajustes para o SET e organizar as "
              "próximas contagens."),
    # Dinheiro -----------------------------------------------------------------------
    Permissao("financeiro.ver_financeiro", "Dinheiro", "Ver o financeiro",
              "Contas a pagar e a receber, despesas e pagamentos.", dinheiro=True),
    Permissao("financeiro.lancar_pagamento", "Dinheiro", "Lançar pagamento previsto",
              "Anotar quando uma conta vai ser paga.", dinheiro=True),
    Permissao("caixa.ver_caixa", "Dinheiro", "Ver o caixa",
              "Abertura, sangria e fechamento da gaveta.", dinheiro=True),
    Permissao("caixa.controlar_descontos", "Dinheiro", "Controlar descontos e metas",
              "O desconto de cada venda contra as regras, anotar a aprovação do grupo e "
              "mudar as regras de desconto, as metas e o prêmio.", dinheiro=True),
    Permissao("conciliacao.conciliar_banco", "Dinheiro", "Conciliar o banco",
              "Extrato do banco contra o que o SET diz que foi pago.", dinheiro=True),
    # Base de processos --------------------------------------------------------------
    Permissao("processos.view_processo", "Base de processos", "Ver processos",
              "O quadro e cada processo da base."),
    Permissao("processos.ver_anexo", "Base de processos", "Abrir anexos dos processos",
              "Baixar os arquivos anexados aos processos."),
    Permissao("processos.documentar_processo", "Base de processos", "Escrever processos",
              "Criar e mudar o texto de um processo."),
    Permissao("processos.registrar_teste", "Base de processos", "Registrar teste",
              "Anotar que o processo foi seguido e como foi."),
    Permissao("processos.validar_processo", "Base de processos", "Validar processo",
              "Dizer que o processo escrito está certo."),
    Permissao("processos.aprovar_regra", "Base de processos", "Aprovar regra",
              "Aprovar a regra de negócio de um processo."),
    # Tempo --------------------------------------------------------------------------
    Permissao("tempo.anotar_tempo", "Tempo", "Anotar o tempo do dia",
              "Dizer se choveu e ver o tempo ao lado das vendas."),
    Permissao("tempo.configurar_tempo", "Tempo", "Ligar a busca do tempo",
              "A busca automática na internet e a cidade da loja.", administracao=True),
    # Sistema ------------------------------------------------------------------------
    Permissao("importacao.ver_importacoes", "Sistema", "Ver as importações",
              "Quando cada leitura do backup do SET rodou, e o registro dela."),
    Permissao("importacao.executar_importacao", "Sistema", "Importar agora",
              "Ler o backup do SET fora do horário.", administracao=True),
    Permissao("compras.change_dadosdaempresa", "Sistema", "Dados da empresa",
              "Razão social, CNPJ e endereços que saem no pedido.", administracao=True),
    Permissao("alertas.configurar_email", "Sistema", "Alertas por e-mail e Telegram",
              "Guarda a senha do e-mail da loja e o que sai do servidor.", administracao=True),
    Permissao("backup.configurar_backup", "Sistema", "Cópia do programa no GitHub",
              "Guarda o token que escreve no GitHub.", administracao=True),
    Permissao("auditoria.ver_auditoria", "Sistema", "Ver a auditoria",
              "Tudo o que cada pessoa fez no sistema, com os valores de antes e depois.",
              dinheiro=True, administracao=True),
    # Acessos ------------------------------------------------------------------------
    Permissao("contas.gerenciar_usuarios", "Acessos", "Administrar pessoas",
              "Criar conta, definir senha e e-mail, dar e tirar perfil, bloquear, encerrar "
              "acesso e sessões.", administracao=True),
    Permissao("contas.editar_perfis", "Acessos", "Editar perfis",
              "Mudar o que cada perfil pode fazer, criar e retirar perfil.", administracao=True),
)

POR_CODIGO = {permissao.codigo: permissao for permissao in CATALOGO}
CODIGOS = tuple(POR_CODIGO)
MARCADAS = frozenset(p.codigo for p in CATALOGO if p.marcada)


def de(codigo):
    """A permissão do catálogo pelo código, ou None."""
    return POR_CODIGO.get(codigo)


def codigo_de(permissao):
    """`app.codigo` de um objeto Permission do Django."""
    return f"{permissao.content_type.app_label}.{permissao.codename}"


def por_modulo(codigos=None):
    """O catálogo agrupado por módulo, na ordem do menu: [(módulo, [Permissao, ...]), ...].

    Com `codigos`, só as permissões daquele conjunto.
    """
    grupos = []
    for modulo in MODULOS:
        itens = [p for p in CATALOGO if p.modulo == modulo and (codigos is None or p.codigo in codigos)]
        if itens:
            grupos.append((modulo, itens))
    return grupos


def objetos(codigos):
    """Os objetos Permission do Django para estes códigos, numa consulta só."""
    from django.contrib.auth.models import Permission  # noqa: PLC0415 - catálogo é lido cedo
    from django.db.models import Q  # noqa: PLC0415

    filtro = Q(pk__in=[])
    for codigo in codigos:
        app_label, codename = codigo.split(".")
        filtro |= Q(content_type__app_label=app_label, codename=codename)
    return list(Permission.objects.filter(filtro).select_related("content_type"))
