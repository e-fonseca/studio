"""Os perfis que vêm prontos com o sistema e o que cada um pode fazer no começo.

Desde a 1.44.0 isto é o PADRÃO, não a regra: a gerência muda o que cada perfil pode pela
tela "Perfis e permissões", e o `configurar_perfis` do instalador nunca desfaz o que ela
mudou (`servicos.configurar_perfis` e o modelo `PermissaoOferecida`). O que vale é o que
está no banco; o nome em português de cada permissão está em `catalogo.py`.

Os três primeiros perfis foram definidos pelo Edson em 07/10/2026. Quem administra vê
tudo e mexe em tudo, inclusive em quem tem acesso; o administrativo cuida do dia a dia
de contas e fornecedores, sem mexer em usuário nem em auditoria; o vendedor só consulta
produto e fornecedor no balcão, e não vê custo, margem nem nada de dinheiro.

A Líder de loja veio com a Cássia (31/10/2026): *"será líder de loja / acesso moderado as
informações gerenciais / foco sera compras de mercadorias / controle de fornecedores /
gestao da equipe local / lançamentos de pagamentos / controle de estoque"*. É o
administrativo inteiro, mais montar o pedido ao fornecedor e responder a equipe. A
descrição do cargo põe o limite: *"Nenhuma compra é confirmada sem aprovação prévia"* da
Direção. Por isso o pedido que ela monta nasce esperando a aprovação da gerência.

Os quatro últimos vieram com o prompt de controle de acesso (02/11/2026), que propunha
Gerência, Administrador de acessos, Compras, Estoque, Operador e Consulta/Auditoria. A
Gerência e o Operador já existiam (Administrador gerência e Operador vendedor); os outros
quatro entram prontos para usar, e ninguém é colocado neles na atualização.

Permissão é conferida no servidor, em toda tela. Esconder o menu não protege nada: o
que protege é o permission_required de cada view.
"""

from .catalogo import CODIGOS

ADMINISTRACAO = "Administrador gerência"
LIDER = "Líder de loja"
ADMINISTRATIVO = "Operador administrativo"
VENDEDOR = "Operador vendedor"
ADMIN_ACESSOS = "Administrador de acessos"
COMPRAS = "Compras"
ESTOQUE = "Estoque"
CONSULTA = "Consulta e auditoria"

_ADMINISTRATIVO = [
    # O que até a 1.43.0 era um `importacao.ver_painel` só. Dividido na 1.44.0 para outros
    # perfis poderem ver uma parte; quem já via tudo continua vendo tudo.
    "importacao.ver_painel",
    "importacao.ver_vendas",
    "importacao.ver_margem",
    "importacao.ver_importacoes",
    "compras.ver_compras",
    "importacao.consultar_produtos",
    "fornecedores.view_fornecedor",
    "fornecedores.change_fornecedor",
    "financeiro.ver_financeiro",
    "financeiro.lancar_pagamento",
    # Conferir o extrato do banco contra o que o SET diz que foi pago é trabalho de
    # contas, do mesmo quem lança pagamento.
    "conciliacao.conciliar_banco",
    # O caixa é o dinheiro que passa pela mão de quem está na loja: quem confere a
    # sangria e o fechamento é o administrativo, não a gerência de longe.
    "caixa.ver_caixa",
    "clientes.ver_clientes",
    "processos.view_processo",
    # Documentar o próprio trabalho é a razão de ser da base de processos: quem executa
    # escreve, a gerência valida. Sem isto o módulo viraria coisa só de administrador.
    "processos.documentar_processo",
    "processos.registrar_teste",
    "processos.ver_anexo",
    # Contar a prateleira é trabalho do dia a dia de quem está na loja; quem conta é quem
    # fecha a contagem, senão a lista de ajustes fica esperando a gerência para existir.
    "inventario.contar_estoque",
    "inventario.fechar_contagem",
    # Quem está na loja é quem ouve o cliente pedir o que não tem. A sugestão de compra
    # é dessa pessoa; quem responde é a gerência.
    "compras.sugerir_compra",
    # Quem está na loja é quem viu se choveu. Anotar o dia é trabalho de balcão; ligar a
    # busca automática, que fala com a internet, é da gerência.
    "tempo.anotar_tempo",
    # Quem recebe a mercadoria é quem tem o romaneio e a nota na mão: anexar e marcar
    # "chegou" é trabalho de quem está no balcão, não da gerência de longe. Fazer o
    # pedido continua sendo da gerência, junto de mudar a quantidade.
    "pedidos.view_pedido",
    "pedidos.anexar_documento",
]

PADRAO = {
    # A gerência tem tudo o que está no catálogo, inclusive o que vier numa versão nova.
    ADMINISTRACAO: list(CODIGOS),
    LIDER: _ADMINISTRATIVO + [
        # "Gestão da equipe local": quem está na loja escreve o que o cliente pediu e a
        # líder responde, sem a sugestão esperar a gerência voltar de viagem.
        "compras.responder_sugestao",
        # Monta o pedido, e o pedido dela nasce esperando a aprovação da gerência. A
        # quantidade ela muda NO PEDIDO, antes de aprovado; a lista de compra e a regra
        # do alerta (`compras.ajustar_compra`) continuam da gerência, porque ali o que
        # se muda vale para todo mundo e não passa por aprovação nenhuma.
        "pedidos.registrar_pedido",
    ],
    ADMINISTRATIVO: list(_ADMINISTRATIVO),
    # Só a tela de consulta: produto e fornecedor, sem custo e sem dinheiro.
    VENDEDOR: ["importacao.consultar_produtos"],
    # "Gerenciar usuários e perfis. Acesso financeiro concedido separadamente." Cuida de
    # contas e senhas sem ver número da loja; e, pela regra de autoridade, só dá a outra
    # pessoa o que não tem marca de dinheiro nem de administração, ou o que ele mesmo tem.
    ADMIN_ACESSOS: ["contas.gerenciar_usuarios"],
    # "Fornecedores, cotações, sugestões e pedidos dentro da alçada." O pedido nasce
    # esperando a gerência, como o da Líder de loja, até a alçada da etapa 2.
    COMPRAS: [
        "compras.ver_compras",
        "compras.sugerir_compra",
        "compras.responder_sugestao",
        "fornecedores.view_fornecedor",
        "fornecedores.change_fornecedor",
        "pedidos.view_pedido",
        "pedidos.registrar_pedido",
        "pedidos.anexar_documento",
        "importacao.consultar_produtos",
    ],
    # "Consultas, contagens, recebimentos e solicitações de ajuste." O ajuste é a lista
    # que a contagem fechada tira para lançar no SET; quem lança é a gerência.
    ESTOQUE: [
        "importacao.consultar_produtos",
        "inventario.contar_estoque",
        "inventario.fechar_contagem",
        "pedidos.view_pedido",
        "pedidos.anexar_documento",
        "compras.sugerir_compra",
    ],
    # "Leitura dos dados expressamente liberados." Olha, não mexe em nada.
    CONSULTA: [
        "importacao.ver_painel",
        "importacao.ver_vendas",
        "importacao.ver_importacoes",
        "fornecedores.view_fornecedor",
        "pedidos.view_pedido",
        "processos.view_processo",
        "processos.ver_anexo",
        "auditoria.ver_auditoria",
    ],
}

# Compatibilidade: até a 1.43.0 o resto do código lia `PERFIS`.
PERFIS = PADRAO

ORDEM = {nome: posicao for posicao, nome in enumerate(PADRAO, start=1)}

DESCRICOES = {
    ADMINISTRACAO: "Acesso total, inclusive a usuários, perfis, auditoria, importação e os "
                   "relatórios por e-mail.",
    LIDER: "Tudo do administrativo, mais montar o pedido ao fornecedor, que só vale "
           "depois que a gerência aprova, e responder as sugestões da equipe. Não mexe em "
           "usuários, na lista de compra nem nas configurações.",
    ADMINISTRATIVO: "Lançamentos, contas a pagar e a receber, fornecedores, painéis, a "
                    "contagem do estoque e sugestões de compra. Não mexe em usuários nem "
                    "vê a auditoria.",
    VENDEDOR: "Só a consulta de balcão: produto e fornecedor, sem custo e sem valores.",
    ADMIN_ACESSOS: "Cria contas, define senha, dá e tira perfil, bloqueia e encerra "
                   "sessões. Não vê número da loja: acesso a dinheiro se dá à parte.",
    COMPRAS: "Lista de compra, fornecedores, sugestões e pedidos. O pedido nasce "
             "esperando a aprovação da gerência.",
    ESTOQUE: "Consulta de balcão, contagem do estoque, recebimento de mercadoria e "
             "sugestões de compra.",
    CONSULTA: "Só olha: indicadores, vendas, pedidos, fornecedores, processos e a "
              "auditoria. Não muda nada.",
}
