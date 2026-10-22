"""Processos a levantar com quem conhece a operação hoje (briefing, seção 5).

Lista de partida para o quadro. A gestão ajusta criticidade, prazos e
responsáveis nas telas; nada aqui é regra aprovada.
"""

from .models import Area, Processo

ALTA = Processo.Criticidade.ALTA
MEDIA = Processo.Criticidade.MEDIA

PROCESSOS_INICIAIS = [
    ("Abertura e fechamento da loja", Area.ABERTURA_FECHAMENTO, ALTA),
    ("Cadastro de produtos e códigos", Area.CADASTRO_PRODUTOS, ALTA),
    ("Unidades de medida e conversões", Area.CADASTRO_PRODUTOS, MEDIA),
    ("Variações artesanais e peças únicas", Area.VARIACOES, MEDIA),
    ("Formação de preços", Area.PRECOS_DESCONTOS, ALTA),
    ("Concessão de descontos", Area.PRECOS_DESCONTOS, MEDIA),
    ("Registro de vendas", Area.VENDAS, ALTA),
    ("Trocas e devoluções", Area.TROCAS_DEVOLUCOES, MEDIA),
    ("Cancelamentos de venda", Area.TROCAS_DEVOLUCOES, MEDIA),
    ("Recebimento e conferência de mercadorias", Area.RECEBIMENTO, ALTA),
    ("Inventário de estoque", Area.INVENTARIO, ALTA),
    ("Registro de quebras e perdas", Area.QUEBRAS_PERDAS, MEDIA),
    ("Mercadorias em consignação", Area.CONSIGNACAO, MEDIA),
    ("Compras e pedidos a fornecedores", Area.COMPRAS, ALTA),
    ("Contatos e condições de fornecedores e artesãos", Area.COMPRAS, ALTA),
    ("Prazos de entrega e reposição", Area.COMPRAS, ALTA),
    ("Sazonalidade e datas fortes", Area.SAZONALIDADE, MEDIA),
    ("Contas a pagar, a receber e conciliações", Area.CONTAS, ALTA),
    ("Relatórios do SET usados no dia a dia", Area.RELATORIOS, ALTA),
    ("Estoque e pedidos do site", Area.SITE, ALTA),
    ("Exceções e problemas recorrentes", Area.EXCECOES, MEDIA),
]
