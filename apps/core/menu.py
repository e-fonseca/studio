"""O menu do topo: o Dashboard, a Visão geral e cinco assuntos, e dentro de cada um as suas telas.

Por que mudou (pedido do Edson, 19/10/2026)
-------------------------------------------
*"o sistema está ficando com muitos menus, acaba dificultando o acesso e a tomada de
decisões rápidas (...) imagine os gestores em viagem, precisando tomar uma decisão
rápida para comprar, como se fosse uma bolsa de valores, tem momento exato para
comprar (...) os menus precisam se conectarem com o mesmo assunto."*

Eram vinte e sete telas em duas fileiras, todas à vista ao mesmo tempo. Quem abria o
sistema no celular, na estrada, lia vinte e sete rótulos antes de chegar na tela que
decide a compra. Ficaram **seis entradas** naquele dia, e cada uma é um assunto:

    Visão geral · Compras · Vendas · Estoque · Dinheiro · Sistema

Nenhuma tela foi apagada: as vinte e sete continuam lá, cada uma dentro do assunto a
que pertence. A segunda fileira do topo mostra **só as telas do assunto aberto** — é
por isso que a pessoa vê seis rótulos mais os cinco ou seis do assunto em que está, e
não vinte e sete de uma vez.

A ordem é a da decisão, não a do organograma: Compras vem logo depois da Visão geral
porque comprar é o que ele precisa decidir rápido, e a primeira tela de Compras é a
Lista de compra, que é onde a quantidade é escolhida e o pedido sai.

O Dashboard na frente (pedido do Edson, 31/10/2026)
---------------------------------------------------
*"logo quando fazer login quero que abra o Dashboard, causa bom impacto com as
informações visíveis. no mesmo menu (principal) colocar ao lado como segunda opção a
visão geral."* O Dashboard saiu de dentro de Vendas e virou a primeira entrada do topo,
com a Visão geral logo ao lado; são **sete entradas** desde a 1.43.0:

    Dashboard · Visão geral · Compras · Vendas · Estoque · Dinheiro · Sistema

Como `primeira_tela` devolve a primeira tela do menu que o perfil abre, quem tem o
painel passa a entrar pelo Dashboard sem regra nova nenhuma, e o vendedor continua
entrando pela Consulta, que é a tela dele. Clicar em Vendas cai agora em Vendas do dia.

Como isto é lido no resto do sistema
------------------------------------
* `para(request)` devolve as duas fileiras já filtradas por permissão e com a tela
  aberta marcada. O operador vendedor enxerga um assunto com uma tela, então não
  recebe segunda fileira nenhuma.
* `apps/core/navegacao.py` lê a ordem daqui para as setas de "anterior" e "próxima",
  andando pelas telas na mesma sequência em que o menu as apresenta.
* Cada item diz as rotas irmãs que o deixam aceso: sem isso, abrir "Despesas" não
  acenderia nada e a pessoa perderia de vista onde está.
"""

from dataclasses import dataclass, field, replace

from django.urls import reverse


@dataclass(frozen=True)
class Item:
    rota: str
    rotulo: str
    permissao: str | None = None
    # Rotas que também acendem este item (view_name completo, como "painel:completo").
    irmas: tuple = ()
    # Uma linha dizendo para que serve, usada no título do link (balão do navegador).
    ajuda: str = ""
    # A rota da tela de onde esta se abre, quando ela é recurso de outra e não parada
    # própria. Quem está nela recebe a seta "anterior" apontando para a tela de origem,
    # em vez de ficar sem caminho de volta por não estar mais no menu.
    dentro_de: str = ""
    atual: bool = field(default=False, compare=False)

    @property
    def endereco(self):
        return reverse(self.rota)

    def acende_em(self, view_name):
        return view_name == self.rota or view_name in self.irmas


@dataclass(frozen=True)
class Grupo:
    """Um assunto do topo, com as telas que pertencem a ele.

    O endereço do assunto é o da **primeira tela que esta pessoa pode abrir**, e não
    uma página de índice: clicar em "Compras" tem que cair na Lista de compra, não
    numa tela que só oferece mais links. Um clique a menos, que é o pedido inteiro.
    """

    chave: str
    rotulo: str
    telas: tuple
    ajuda: str = ""
    atual: bool = field(default=False, compare=False)

    @property
    def endereco(self):
        return self.telas[0].endereco

    @property
    def tem_fileira(self):
        """Assunto de uma tela só não precisa da segunda fileira: ela repetiria o topo."""
        return len(self.telas) > 1

    def acende_em(self, view_name):
        return any(tela.acende_em(view_name) for tela in self.telas)


GRUPOS = [
    # Primeiro de propósito: é a tela que abre ao entrar (pedido de 31/10/2026, acima).
    Grupo("dashboard", "Dashboard",
          ajuda="A loja em quadros: venda, margem, estoque e o que pede atenção.", telas=(
        Item("painel:dashboard", "Dashboard", "importacao.ver_painel",
             ajuda="Gráficos e estatísticas da loja: venda, margem, estoque e curva ABC."),
    )),
    Grupo("visao", "Visão geral", ajuda="Como a loja está hoje, e o que fazer agora.", telas=(
        Item("painel:geral", "Visão geral", "importacao.ver_painel",
             ajuda="Como a loja está, em quatro números grandes."),
    )),
    Grupo("compras", "Compras", ajuda="Decidir o que comprar e fechar com o fornecedor.",
          telas=(
        # Primeira de propósito: é a tela em que a quantidade é escolhida e o pedido
        # sai. Clicar em "Compras" cai aqui.
        Item("compras:lista", "Lista de compra", "compras.ver_compras",
             irmas=("compras:lista_em_arquivo", "compras:ajustar_quantidade",
                    "compras:pedido_ao_fornecedor"),
             ajuda="O que comprar antes de faltar, quanto comprar e de qual fornecedor."),
        # Pedido do Edson em 02/11/2026: "no menu compras criar um sub menu compra guiada".
        # A mesma conta da Lista de compra, feita em perguntas, um fornecedor por vez, para
        # quem nunca comprou pela loja (apps/compras/guiada.py).
        Item("compras:guiada", "Compra guiada", "compras.ver_compras",
             irmas=("compras:guiada_comecar", "compras:guiada_continuar", "compras:guiada_passo",
                    "compras:guiada_folha", "compras:guiada_pronto", "compras:guiada_deixar"),
             ajuda="Perguntas, uma de cada vez, que montam o pedido de um fornecedor."),
        Item("pedidos:lista", "Pedidos", "pedidos.view_pedido",
             # "baixar" fica de fora: ela devolve o arquivo anexado, não uma tela com menu.
             irmas=("pedidos:detalhe", "pedidos:anexar", "pedidos:receber",
                    "pedidos:aprovar"),
             ajuda="Os pedidos feitos a fornecedores, com o romaneio e a nota de cada um."),
        Item("fornecedores:lista", "Fornecedores", "fornecedores.view_fornecedor",
             irmas=("fornecedores:ficha", "fornecedores:produtos",
                    "fornecedores:produtos_em_arquivo"),
             ajuda="Prazo, reputação e cadastro de cada fornecedor."),
        Item("painel:painel", "Indicadores de compra", "importacao.ver_painel",
             irmas=("painel:completo",),
             ajuda="Os indicadores de compra e estoque, do resumo ao completo."),
    )),
    Grupo("vendas", "Vendas", ajuda="O que a loja vendeu, com que lucro e para quem.",
          telas=(
        Item("painel:vendas_dia", "Vendas do dia", "importacao.ver_vendas",
             irmas=("painel:vendas_dia_arquivo",),
             ajuda="O que a loja vendeu no dia, com custo, lucro e margem de cada produto."),
        Item("margem:lista", "Margem", "importacao.ver_margem",
             irmas=("margem:em_arquivo",),
             ajuda="Markup e margem de lucro de cada produto, e da loja inteira."),
        Item("painel:ticket_medio", "Ticket médio", "importacao.ver_vendas",
             ajuda="Quanto o cliente gasta por compra, por período, pagamento e vendedor."),
        Item("clientes:lista", "Clientes", "clientes.ver_clientes",
             ajuda="Quem compra na loja, pelo que o SET registra."),
    )),
    Grupo("estoque", "Estoque", ajuda="O que está na prateleira, e se é isto mesmo.",
          telas=(
        Item("importacao:consulta", "Consulta", "importacao.consultar_produtos",
             ajuda="Procurar um produto pelo nome, pelo código ou pelo leitor."),
        Item("inventario:lista", "Inventário", "inventario.contar_estoque",
             irmas=("inventario:contagem", "inventario:camera"),
             ajuda="Contagem física da loja, com a diferença contra o SET."),
        Item("inventario:organizar", "Organizar", "inventario.fechar_contagem",
             irmas=("inventario:etiquetas",),
             ajuda="Peças sem etiqueta, danificadas e paradas, e o que fazer com cada uma."),
    )),
    Grupo("dinheiro", "Contas a pagar", ajuda="O que a loja deve, o que entrou e o que o banco diz.",
          telas=(
        Item("financeiro:contas_a_pagar", "Financeiro", "financeiro.ver_financeiro",
             irmas=("financeiro:despesas", "financeiro:contas_a_receber",
                    "financeiro:pagamentos"),
             ajuda="Contas a pagar e a receber, despesas e pagamentos a fornecedores."),
        Item("caixa:lista", "Caixa", "caixa.ver_caixa",
             irmas=("caixa:turno",),
             ajuda="Os turnos de caixa: abertura, fechamento, operador e valores."),
        Item("caixa:descontos", "Descontos e metas", "caixa.controlar_descontos",
             irmas=("caixa:regras_de_desconto",),
             ajuda="O desconto de cada venda contra as regras da loja, e a meta de cada fim de semana."),
        Item("conciliacao:lista", "Conciliação", "conciliacao.conciliar_banco",
             irmas=("conciliacao:extrato",),
             ajuda="Conferir o extrato do banco contra as contas pagas no SET."),
    )),
    Grupo("sistema", "Sistema",
          ajuda="Quem entra, de onde vêm os dados e o que o sistema avisa.", telas=(
        Item("importacao:historico", "Importações", "importacao.ver_importacoes",
             ajuda="Quando os dados do SET entraram e o que cada importação trouxe."),
        Item("compras:dados_da_empresa", "Dados da empresa", "compras.change_dadosdaempresa",
             ajuda="O nome, o CNPJ e os endereços que saem no pedido ao fornecedor."),
        Item("processos:quadro", "Base de processos", "processos.view_processo",
             irmas=("processos:detalhe", "processos:ficha_tecnica"),
             ajuda="Transferência de conhecimento: o passo a passo do trabalho."),
        Item("contas:usuarios", "Usuários", "contas.gerenciar_usuarios",
             irmas=("contas:ficha", "contas:alterar_usuario", "contas:criar_usuario",
                    "contas:confirmar_senha"),
             ajuda="Quem entra no sistema, com quais perfis, e a ficha de cada pessoa."),
        Item("alertas:painel", "Alertas", "alertas.configurar_email",
             ajuda="Os relatórios que o sistema manda por e-mail sozinho."),
        Item("backup:painel", "Cópia do programa", "backup.configurar_backup",
             irmas=("backup:enviar_agora",),
             ajuda="A cópia do código do sistema no GitHub, fora do servidor da loja."),
        # No menu só para quem administra, senão ela entraria na fileira do vendedor, que
        # tem uma tela só. A tela em si pede apenas login, para o link poder ser passado a
        # qualquer pessoa que precise instalar o certificado no celular dela.
        Item("core:certificado", "Certificado", "importacao.ver_painel",
             irmas=("core:certificado_autoridade",),
             ajuda="Como fazer o celular confiar no sistema e liberar a câmera."),
        Item("auditoria:lista", "Auditoria", "auditoria.ver_auditoria",
             ajuda="Tudo o que foi feito no sistema, por quem e de onde."),
    )),
]

# Telas que existem mas não entram no menu: a de versões abre pelo número no topo,
# e o início é a porta que encaminha cada perfil para a sua tela.
#
# As duas últimas saíram do menu por pedido do Edson (14/10/2026): cada uma virou recurso
# dentro da tela em que a decisão é tomada. A tela continua existindo inteira, só não se
# chega mais a ela pelo menu: a comparação com o ano passado abre pela Lista de compra e o
# tempo abre pela Visão geral. Tirar a rota junto apagaria a tabela produto a produto, o
# arquivo em CSV e o campo de anotar o dia.
FORA_DO_MENU = [
    # O histórico cita os números que cada versão consertou (faturamento, lucro,
    # margem), então pede a mesma permissão das telas de dinheiro. O NÚMERO da
    # versão continua à vista de todo mundo no alto da tela; o que é guardado é o
    # histórico.
    Item("core:versoes", "Versões do sistema", "importacao.ver_painel"),
    # As quatro abaixo saíram do menu de Compras por escolha do Edson em 22/10/2026
    # ("Quatro no menu"): oito abas eram muita coisa para decidir rápido. Abrem pela
    # fileira de links logo abaixo do título da Lista de compra, e nenhuma tela ou
    # histórico foi apagado.
    Item("compras:antes_de_comprar", "Antes de comprar", "compras.ver_compras",
         dentro_de="compras:lista",
         ajuda="Quanto ainda cabe comprar no mês e se vale comprar este produto."),
    Item("compras:sugestoes", "Sugestões", "compras.ver_compras",
         dentro_de="compras:lista",
         ajuda="O que repor, o que parar de comprar e o que empurrar na venda."),
    Item("compras:sugestoes_da_equipe", "Sugestões da equipe", "compras.sugerir_compra",
         dentro_de="compras:lista",
         ajuda="O que a equipe viu na loja e acha que precisa ser comprado."),
    Item("compras:consulta", "Últimas compras", "compras.ver_compras",
         irmas=("compras:compra",), dentro_de="compras:lista",
         ajuda="A última compra de cada fornecedor, item a item."),
    # Abre pela Lista de compra, no quadro "Comparar com o ano passado".
    Item("compras:comparar", "Comparar com o ano passado", "compras.ver_compras",
         irmas=("compras:comparar_em_arquivo",), dentro_de="compras:lista",
         ajuda="O que o período vendeu contra o mesmo período do ano passado."),
    # Abre pela tela Usuários (1.44.0): é onde quem dá acesso já está. Menu novo não se
    # cria solto (pedido do Edson, 19/10/2026).
    Item("contas:perfis", "Perfis e permissões", "contas.gerenciar_usuarios",
         irmas=("contas:perfil", "contas:criar_perfil", "contas:retirar_perfil",
                "contas:devolver_perfil"), dentro_de="contas:usuarios",
         ajuda="O que cada perfil pode fazer, numa tabela, e quem está em cada um."),
    # Abre pela Visão geral, no quadro "O tempo e a venda".
    Item("tempo:painel", "Tempo e venda", "tempo.anotar_tempo",
         irmas=("tempo:em_arquivo",), dentro_de="painel:geral",
         ajuda="O tempo de cada dia ao lado do que a loja vendeu nele."),
]


def recursos_de(rota, usuario):
    """As telas que abrem de dentro de `rota`, já filtradas pelo perfil de quem olha."""
    return [item for item in permitidos(FORA_DO_MENU, usuario) if item.dentro_de == rota]


def telas():
    """Todas as telas do menu, na ordem em que o menu as apresenta."""
    return [tela for grupo in GRUPOS for tela in grupo.telas]


def de_rota(rota):
    """O item do menu de uma rota, para quem precisa do rótulo e do endereço dela."""
    for item in telas() + FORA_DO_MENU:
        if item.rota == rota:
            return item
    return None


def grupo_de(rota):
    """O assunto a que uma rota pertence, para a tela saber em que fileira acender."""
    for grupo in GRUPOS:
        if any(tela.rota == rota for tela in grupo.telas):
            return grupo
    return None


def permitidos(itens, usuario):
    return [item for item in itens
            if item.permissao is None or usuario.has_perm(item.permissao)]


def grupos_de(usuario):
    """Os assuntos que esta pessoa enxerga, já sem as telas que ela não pode abrir.

    Assunto que ficou sem nenhuma tela some do topo inteiro: mostrar "Contas a pagar" para
    quem não pode abrir nada de dinheiro é oferecer uma porta trancada.
    """
    visiveis = []
    for grupo in GRUPOS:
        abertas = permitidos(grupo.telas, usuario)
        if abertas:
            visiveis.append(replace(grupo, telas=tuple(abertas)))
    return visiveis


def _marcar(itens, view_name):
    return [replace(item, atual=item.acende_em(view_name)) for item in itens]


def _grupo_aberto(grupos, view_name, usuario):
    """Qual assunto está aceso, inclusive quando a tela aberta é recurso de outra.

    A comparação com o ano passado não está em grupo nenhum, mas abre de dentro da
    Lista de compra: quem está nela continua vendo "Compras" aceso, senão o topo
    apagaria justamente quando a pessoa foi mais fundo no assunto.
    """
    for grupo in grupos:
        if grupo.acende_em(view_name):
            return grupo
    recurso = next((item for item in permitidos(FORA_DO_MENU, usuario)
                    if item.acende_em(view_name) and item.dentro_de), None)
    if recurso is None:
        return None
    origem = grupo_de(recurso.dentro_de)
    if origem is None:
        return None
    return next((g for g in grupos if g.chave == origem.chave), None)


def para(request):
    """As duas fileiras do topo: os assuntos, e as telas do assunto aberto."""
    usuario = getattr(request, "user", None)
    if usuario is None or not usuario.is_authenticated:
        return [], []
    view_name = getattr(getattr(request, "resolver_match", None), "view_name", None)
    grupos = grupos_de(usuario)
    aberto = _grupo_aberto(grupos, view_name, usuario)
    grupos = [replace(grupo, atual=aberto is not None and grupo.chave == aberto.chave)
              for grupo in grupos]
    if aberto is None or not aberto.tem_fileira:
        return grupos, []
    return grupos, _marcar(aberto.telas, view_name)


def primeira_tela(usuario):
    """A tela em que esta pessoa entra ao abrir o sistema.

    É a primeira do menu que o perfil dela abre, que para a gerência é o Dashboard desde
    a 1.43.0 (era a Visão geral).
    Quem não tem o painel (o perfil de vendedor) cai na primeira tela que o perfil dele
    abre, em vez de numa página vazia dizendo que ele não tem acesso a nada.
    """
    abertas = permitidos(telas(), usuario)
    return abertas[0].rota if abertas else None
