"""Os três perfis de acesso da loja e o que cada um pode fazer.

Definidos pelo Edson em 07/10/2026. A regra é simples: quem administra vê tudo e mexe
em tudo, inclusive em quem tem acesso; o administrativo cuida do dia a dia de contas e
fornecedores, sem mexer em usuário nem em auditoria; o vendedor só consulta produto e
fornecedor no balcão, e não vê custo, margem nem nada de dinheiro.

Permissão é conferida no servidor, em toda tela. Esconder o menu não protege nada: o
que protege é o permission_required de cada view.
"""

ADMINISTRACAO = "Administrador gerência"
ADMINISTRATIVO = "Operador administrativo"
VENDEDOR = "Operador vendedor"

_ADMINISTRATIVO = [
    "importacao.ver_painel",
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

PERFIS = {
    ADMINISTRACAO: _ADMINISTRATIVO + [
        "contas.gerenciar_usuarios",
        "importacao.executar_importacao",
        "auditoria.ver_auditoria",
        "processos.validar_processo",
        "processos.aprovar_regra",
        "compras.responder_sugestao",
        # Mudar a quantidade a comprar é decidir quanto dinheiro sai: fica com quem
        # responde pela compra, ao lado de responder à sugestão da equipe. O
        # administrativo continua vendo a lista e levando o arquivo ao fornecedor.
        "compras.ajustar_compra",
        # O timbre do pedido (razão social, CNPJ, endereço) é documento da empresa.
        "compras.change_dadosdaempresa",
        # Registrar o pedido é comprometer dinheiro com um fornecedor: fica com quem
        # ajusta a quantidade, que é a mesma decisão.
        "pedidos.registrar_pedido",
        # Só a gerência: esta tela guarda a senha do e-mail da loja e decide o que sai
        # do servidor para fora. Não é configuração de dia a dia.
        "alertas.configurar_email",
        # Só a gerência: esta tela guarda um token que dá escrita num repositório fora
        # da loja, e decide o que sai do servidor.
        "backup.configurar_backup",
        "tempo.configurar_tempo",
    ],
    ADMINISTRATIVO: _ADMINISTRATIVO,
    # Só a tela de consulta: produto e fornecedor, sem custo e sem dinheiro.
    VENDEDOR: ["importacao.consultar_produtos"],
}

DESCRICOES = {
    ADMINISTRACAO: "Acesso total, inclusive a usuários, auditoria, importação e os relatórios por e-mail.",
    ADMINISTRATIVO: "Lançamentos, contas a pagar e a receber, fornecedores, painéis, a "
                    "contagem do estoque e sugestões de compra. Não mexe em usuários nem "
                    "vê a auditoria.",
    VENDEDOR: "Só a consulta de balcão: produto e fornecedor, sem custo e sem valores.",
}
