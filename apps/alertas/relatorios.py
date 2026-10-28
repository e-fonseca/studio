"""Os três relatórios que saem por e-mail, cada um montado a partir das telas.

Pedido do Edson em 08/10/2026:

- contas a pagar vencidas, do dia e prestes a vencer — todo dia;
- relatório de estoque — toda semana;
- sugestão de compra dos produtos importantes — toda semana.

**Nenhuma conta é refeita aqui.** Cada relatório chama a mesma função que a tela
chama: `financeiro.servicos` para as contas, `painel.visao_geral` e
`compras.sugestoes` para o estoque, `compras.lista_de_compra` para a compra. Se o
número do e-mail divergisse do número da tela, o sistema perderia a confiança
inteira, e um dia divergiria — regra copiada é regra que diverge, já aconteceu com
o "parado" do Dashboard.

**Relatório sem notícia não é mandado.** `tem_noticia` diz se há algo que mude o
que a pessoa faz hoje; sem isso, o e-mail diário vira ruído que ninguém abre, e
quando houver uma conta vencida de verdade ela vai junto com o ruído. Um aviso
isolado no fim do mês, dizendo que está tudo em dia, mantém a confiança de que o
sistema está vivo sem encher a caixa de entrada.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from django.utils import timezone

from apps.compras import limite, lista_de_compra, sugestoes
from apps.financeiro import servicos as financeiro
from apps.financeiro.models import Lancamento
from apps.importacao import servicos as importacao_servicos
from apps.painel import visao_geral
from apps.painel import vendas_do_dia as vendas_da_tela

ZERO = Decimal("0")
# Quantas linhas de cada lista entram no corpo do e-mail. O resto fica na tela: um
# e-mail que precisa de rolagem para ser lido no celular não é lido.
LINHAS_NO_EMAIL = 12


@dataclass
class Bloco:
    """Um pedaço do e-mail: um título, uma frase e, às vezes, uma tabela.

    A tabela tem DUAS colunas, não quatro: o que a linha é, e quanto custa. Quatro
    colunas não cabem em 390px de celular, e e-mail que rola de lado no celular não é
    lido. O resto de cada linha (data, grupo, motivo) vai numa segunda linha menor
    dentro da própria coluna da esquerda.
    """

    titulo: str
    frase: str = ""
    colunas: list = field(default_factory=list)
    linhas: list = field(default_factory=list)
    escondidas: int = 0
    link: str = ""
    link_rotulo: str = ""


@dataclass
class Relatorio:
    rotina: str
    assunto: str
    manchete: str = ""
    # A frase que vai no registro de envios, para conferir sem abrir a caixa de entrada.
    resumo: str = ""
    data_corte: object = None
    blocos: list = field(default_factory=list)
    tem_noticia: bool = False
    aviso: str = ""
    # A tela que este relatório resume. O aviso do Telegram vira um endereço inteiro a
    # partir daqui, porque link relativo numa mensagem de celular não abre nada.
    caminho: str = "/sistema/"


def _reais(valor):
    texto = f"{(valor or ZERO):,.2f}"
    return "R$ " + texto.replace(",", "·").replace(".", ",").replace("·", ".")


def _numero(valor):
    return f"{int(valor or 0):,}".replace(",", ".")


def _recorte(linhas):
    """As primeiras linhas e quantas ficaram de fora."""
    return list(linhas[:LINHAS_NO_EMAIL]), max(len(linhas) - LINHAS_NO_EMAIL, 0)


def _aviso_dos_dados():
    """Dado velho muda o que o e-mail significa, então ele vai escrito no topo."""
    estado = importacao_servicos.estado_dos_dados()
    if estado.nivel in ("vencido", "sem_dados"):
        return f"{estado.titulo}. {estado.detalhe}"
    return ""


# ------------------------------------------------------------------ contas a pagar

def contas_a_pagar(importacao=None, hoje=None):
    """Diário: o que venceu, o que vence hoje e o que vence na semana.

    São os três filtros que a tela de contas já tem, nessa ordem, porque é a ordem da
    urgência: o que já venceu custa juros, o do dia ainda dá para pagar, e o da semana
    é o que permite remarcar uma compra antes de apertar o caixa.
    """
    importacao = importacao or importacao_servicos.ultima_concluida()
    hoje = hoje or timezone.localdate()
    relatorio = Relatorio(rotina="contas", assunto="Contas a pagar", aviso=_aviso_dos_dados(),
                          caminho="/sistema/financeiro/")
    if importacao is None:
        relatorio.manchete = "Ainda não há dados importados do SET."
        relatorio.resumo = "Sem importação concluída."
        return relatorio

    relatorio.data_corte = importacao.data_corte
    faixas = [
        ("atrasados", "Já venceram", "Contas em aberto com vencimento passado. Cada dia aqui costuma custar juros."),
        ("do_dia", "Vencem hoje", "Dá para pagar hoje sem custo nenhum."),
        ("prestes", f"Vencem em até {financeiro.DIAS_PRESTES_A_VENCER} dias",
         "O que ainda dá para planejar: é aqui que uma compra pode ser remarcada."),
    ]
    total_vencido = ZERO
    # Por id, e não somando os três: no serviço do financeiro o filtro "prestes" é
    # vencimento >= hoje, então ele já inclui o que vence hoje. Somar os tamanhos
    # contaria a conta de hoje duas vezes e a manchete prometeria mais conta do que há.
    ids_no_total = set()
    for chave, titulo, explicacao in faixas:
        contas = financeiro.contas_a_pagar(importacao, hoje=hoje, filtro=chave)
        valor = sum((c.valor or ZERO for c in contas), ZERO)
        ids_no_total.update(c.pk for c in contas)
        if chave == "atrasados":
            total_vencido = valor
        linhas, escondidas = _recorte([
            {
                "quando": c.vencimento.strftime("%d/%m") if c.vencimento else "sem data",
                "quem": c.contraparte or c.descricao or c.documento or "sem descrição",
                "o_que": c.grupo or "",
                "valor": _reais(c.valor),
                "detalhe": f"{c.atraso} dia(s) de atraso" if getattr(c, "atraso", 0) else "",
            }
            for c in contas
        ])
        relatorio.blocos.append(Bloco(
            titulo=f"{titulo}: {len(contas)} conta(s), {_reais(valor)}",
            frase=explicacao if contas else "Nada aqui, e isso é uma boa notícia.",
            colunas=["Conta", "Valor"],
            linhas=linhas,
            escondidas=escondidas,
            link="/sistema/financeiro/?filtro=" + chave,
            link_rotulo="Abrir no sistema",
        ))

    quantas_no_total = len(ids_no_total)
    relatorio.tem_noticia = quantas_no_total > 0
    if total_vencido:
        relatorio.manchete = (f"{_reais(total_vencido)} em contas já vencidas, "
                              f"e {quantas_no_total} conta(s) exigem atenção hoje.")
    elif quantas_no_total:
        relatorio.manchete = f"Nada vencido. {quantas_no_total} conta(s) vencem hoje ou nos próximos dias."
    else:
        relatorio.manchete = "Nenhuma conta vencida, do dia ou da semana. Caixa tranquilo."
    relatorio.resumo = relatorio.manchete
    return relatorio


# ------------------------------------------------------------------------ estoque

def estoque(importacao=None):
    """Semanal: quanto dinheiro está na prateleira e quanto dele não gira.

    Os números são os mesmos da Visão geral e das Sugestões; o e-mail só junta o que
    está espalhado em duas telas e manda uma vez por semana, que é o ritmo em que uma
    decisão de estoque muda alguma coisa.
    """
    importacao = importacao or importacao_servicos.ultima_concluida()
    relatorio = Relatorio(rotina="estoque", assunto="Estoque da loja", aviso=_aviso_dos_dados(),
                          caminho="/sistema/painel/")
    if importacao is None:
        relatorio.manchete = "Ainda não há dados importados do SET."
        relatorio.resumo = "Sem importação concluída."
        return relatorio

    relatorio.data_corte = importacao.data_corte
    visao = visao_geral.montar(importacao)
    cartoes = {c.chave: c for c in visao.cartoes}
    prateleira = cartoes.get("estoque")

    relatorio.blocos.append(Bloco(
        titulo="O que está na prateleira hoje",
        frase=(f"{_reais(prateleira.valor) if prateleira else '—'} ao custo, "
               f"em {_numero(visao.importacao.produtos)} produtos cadastrados. "
               f"{_numero(visao.sem_venda)} deles não venderam nenhuma unidade em 12 meses."),
        link="/sistema/painel/", link_rotulo="Abrir a Visão geral",
    ))

    # Os três blocos de estoque das Sugestões: o que não devia ter sido comprado, o que
    # está travado e o que precisa sair pela venda. O "repor" fica de fora porque é
    # assunto do relatório de compra, que vai no mesmo dia.
    blocos_de_estoque = {"parar", "destravar", "empurrar"}
    todas = sugestoes.montar(importacao)
    for bloco in todas.blocos:
        if bloco.chave not in blocos_de_estoque or bloco.vazio:
            continue
        linhas, escondidas = _recorte([
            {
                "quando": "",
                "quem": linha.descricao,
                "o_que": linha.grupo or linha.fornecedor or "",
                "valor": _reais(linha.valor),
                "detalhe": linha.detalhe,
            }
            for linha in bloco.linhas
        ])
        relatorio.blocos.append(Bloco(
            titulo=f"{bloco.titulo}: {bloco.quantos} produto(s), {_reais(bloco.total)}",
            frase=f"{bloco.pergunta} {bloco.acao}",
            colunas=["Produto", bloco.coluna],
            linhas=linhas,
            escondidas=escondidas,
            link="/sistema/compras/sugestoes/", link_rotulo="Abrir as sugestões",
        ))

    parado = next((b for b in todas.blocos if b.chave == "parar"), None)
    relatorio.tem_noticia = any(not b.vazio for b in todas.blocos if b.chave in blocos_de_estoque)
    if prateleira and parado and not parado.vazio:
        relatorio.manchete = (f"{_reais(prateleira.valor)} parados na prateleira, "
                              f"dos quais {_reais(parado.total)} em produtos que não venderam no ano.")
    elif prateleira:
        relatorio.manchete = f"{_reais(prateleira.valor)} na prateleira, sem produto parado para apontar."
    else:
        relatorio.manchete = "Sem número de estoque nesta importação."
    relatorio.resumo = relatorio.manchete
    return relatorio


# --------------------------------------------------------------- sugestão de compra

def sugestao_de_compra(importacao=None, hoje=None):
    """Semanal: o que comprar antes de faltar, dentro do teto do mês.

    "Produtos importantes" aqui é o começo da lista de compra — o que cabe no teto
    mensal, já ordenado por urgência e cortado POR FORNECEDOR, com o contrapeso de
    quanto daquele fornecedor está parado. É a mesma lista da tela, e é de propósito:
    o e-mail não decide nada que a tela não decida.
    """
    importacao = importacao or importacao_servicos.ultima_concluida()
    hoje = hoje or timezone.localdate()
    relatorio = Relatorio(rotina="compra", assunto="Sugestão de compra", aviso=_aviso_dos_dados(),
                          caminho="/sistema/compras/lista/")
    if importacao is None:
        relatorio.manchete = "Ainda não há dados importados do SET."
        relatorio.resumo = "Sem importação concluída."
        return relatorio

    relatorio.data_corte = importacao.data_corte
    # Os dois passos da tela, na mesma ordem: montar a lista e DEPOIS priorizar com o
    # teto do mês. Sem o segundo, `lista.primeiro` fica vazia e o e-mail sairia sem
    # nenhum fornecedor — a lista existe, mas ninguém escolheu por onde começar.
    resumo_caixa = financeiro.resumir(importacao, hoje=hoje)
    teto = limite.teto_de(importacao, hoje=hoje, resumo_caixa=resumo_caixa)
    lista = lista_de_compra.priorizar(lista_de_compra.montar(importacao, hoje=hoje), teto)
    if not lista.tem_itens:
        relatorio.manchete = "Nenhum produto abaixo do mínimo ou prestes a faltar."
        relatorio.resumo = relatorio.manchete
        return relatorio

    relatorio.tem_noticia = True
    relatorio.manchete = (
        f"{_numero(lista.faltando)} produto(s) já faltando e {_numero(lista.quantos)} na lista. "
        f"Comprando o começo da lista, {_reais(lista.valor_primeiro)} de "
        f"{_reais(lista.cabe_no_mes)} que cabem no mês."
    )
    relatorio.resumo = relatorio.manchete

    for fornecedor in lista.primeiro:
        linhas, escondidas = _recorte([
            {
                "quando": item.rotulo,
                "quem": item.descricao,
                "o_que": f"tem {item.estoque:.0f}, comprar {item.comprar:.0f}",
                "valor": _reais(item.valor),
                "detalhe": item.motivo,
            }
            for item in fornecedor.itens
        ])
        contrapeso = ""
        if fornecedor.parado_na_prateleira:
            contrapeso = (f" Contrapeso: {_reais(fornecedor.parado_na_prateleira)} deste fornecedor "
                          f"estão parados sem vender no ano, em {fornecedor.itens_parados} produto(s).")
        prazo = f"{fornecedor.prazo_dias} dias de prazo" if fornecedor.prazo_dias is not None else "prazo não informado"
        relatorio.blocos.append(Bloco(
            titulo=f"{fornecedor.nome or 'Sem fornecedor'}: {_reais(fornecedor.valor)}",
            frase=f"{fornecedor.quantos} produto(s), {fornecedor.faltando} já faltando, {prazo}.{contrapeso}",
            colunas=["Produto", "Valor"],
            linhas=linhas,
            escondidas=escondidas,
            link="/sistema/compras/lista/", link_rotulo="Abrir a lista de compra",
        ))

    if lista.resto:
        relatorio.blocos.append(Bloco(
            titulo=f"Fora do teto do mês: mais {_numero(lista.resto)} produto(s), {_reais(lista.valor_resto)}",
            frase="Não cabem no teto deste mês. Estão na tela, com o arquivo para o Excel.",
            link="/sistema/compras/lista/", link_rotulo="Abrir a lista de compra",
        ))
    return relatorio


# ------------------------------------------------------------------- vendas do dia

def vendas_do_dia(importacao=None, dia=None):
    """Diário: tudo o que saiu no dia, com custo, lucro em reais e margem.

    Pedido do Edson em 11/10/2026, junto com a tela: "uma relação de todos os produtos
    vendidos do dia, preço de custo e valor de venda com porcentual de lucro e valor".

    A conta é a da tela, chamada daqui: `painel.vendas_do_dia.calcular`. O e-mail leva a
    relação; o Telegram leva a manchete e os campeões.

    O dia é o último com venda na importação, e não "ontem" pelo calendário: se a
    importação não rodou hoje, dizer "ontem" seria mentir sobre a data do número. O dia
    vai escrito em toda parte do relatório.
    """
    importacao = importacao or importacao_servicos.ultima_concluida()
    relatorio = Relatorio(rotina="vendas", assunto="Vendas do dia", aviso=_aviso_dos_dados(),
                          caminho="/sistema/painel/vendas-do-dia/")
    if importacao is None:
        relatorio.manchete = "Ainda não há dados importados do SET."
        relatorio.resumo = "Sem importação concluída."
        return relatorio

    dados = vendas_da_tela.calcular(importacao, dia=dia)
    relatorio.data_corte = dados.dia
    if not dados.tem_dados:
        relatorio.manchete = "Nenhuma venda no último dia importado."
        relatorio.resumo = relatorio.manchete
        return relatorio

    relatorio.tem_noticia = True
    quando = dados.dia.strftime("%d/%m/%Y")
    margem = f"{dados.margem}%".replace(".", ",") if dados.margem is not None else "sem margem para calcular"
    relatorio.manchete = (
        f"Em {quando} a loja vendeu {_reais(dados.faturamento)} e sobrou "
        f"{_reais(dados.lucro)} depois do custo do produto ({margem})."
    )
    relatorio.resumo = relatorio.manchete

    sem_custo = ""
    if dados.tem_estimativa:
        sem_custo += (f" O SET não gravou o custo de {_numero(dados.produtos_estimados)} "
                      f"produto(s) deste dia, {_reais(dados.valor_estimado)} de venda: para "
                      "esses o custo é o do cadastro, uma estimativa.")
    if not dados.tudo_tem_custo:
        sem_custo += (f" Outros {_numero(dados.produtos_sem_custo)} produto(s) não têm custo "
                      f"nenhum, {_reais(dados.valor_sem_custo)} de venda que ficam fora da "
                      "conta do lucro.")
    relatorio.blocos.append(Bloco(
        titulo=f"O dia de {quando}",
        frase=(f"{_numero(dados.itens)} produto(s) em {_numero(dados.cupons)} venda(s). "
               f"Custo de {_reais(dados.custo)} sobre {_reais(dados.valor_com_custo)} "
               f"vendidos com custo conhecido.{sem_custo}"),
        link=relatorio.caminho, link_rotulo="Abrir a relação do dia",
    ))

    linhas, escondidas = _recorte([
        {
            "quando": "",
            "quem": linha.descricao,
            "o_que": f"{linha.quantidade:.0f} un., {linha.grupo}".strip().strip(","),
            "valor": _reais(linha.valor),
            "detalhe": ("sem custo nenhum, fora da conta do lucro" if linha.sem_custo else
                        f"sobrou {_reais(linha.lucro)} "
                        f"({str(linha.margem).replace('.', ',')}%)"
                        + (f", custo {linha.base_do_custo}" if linha.estimado else "")),
        }
        for linha in dados.linhas
    ])
    relatorio.blocos.append(Bloco(
        titulo="O que mais vendeu",
        frase="Do maior valor vendido para o menor, com o que sobrou em cada um.",
        colunas=["Produto", "Vendido"],
        linhas=linhas,
        escondidas=escondidas,
        link=relatorio.caminho, link_rotulo="Ver a relação inteira",
    ))

    # Vender abaixo do custo é a única coisa aqui que pede ação hoje: ou o preço está
    # errado no cadastro, ou o desconto passou do ponto. Só com o custo DA VENDA, nunca
    # com estimativa: produto vendido a peso tem custo de cadastro por quilo e apareceria
    # como prejuízo sem a loja ter perdido nada.
    prejuizo = [linha for linha in dados.linhas if linha.prejuizo_confirmado]
    if prejuizo:
        linhas, escondidas = _recorte([
            {
                "quando": "",
                "quem": linha.descricao,
                "o_que": f"vendido a {_reais(linha.preco_medio)}, custou {_reais(linha.custo_unitario_medio)}",
                "valor": _reais(linha.lucro),
                "detalhe": "",
            }
            for linha in prejuizo
        ])
        relatorio.blocos.append(Bloco(
            titulo=f"Vendidos abaixo do custo: {len(prejuizo)} produto(s)",
            frase="Saíram por menos do que custaram. Confira o preço no cadastro do SET ou "
                  "o desconto dado na venda.",
            colunas=["Produto", "Prejuízo"],
            linhas=linhas,
            escondidas=escondidas,
            link=relatorio.caminho, link_rotulo="Abrir a relação do dia",
        ))
    return relatorio


def backup_no_github(configuracao=None, agora=None):
    """Diário, e CALADO quando está tudo bem: o vigia da cópia fora do servidor.

    Pedido do Edson em 14/10/2026, dentro do foco de automatizar tudo. O envio já é
    automático; o que este relatório cobre é o jeito de ele parar sem ninguém notar —
    token vencido, atualização que falhou no meio, mês sem atualização nenhuma.

    `tem_noticia` só fica verdadeiro quando há algo a fazer, e por isso o relatório não
    chega todo dia dizendo que está tudo certo: aviso que chega sempre deixa de ser aviso.
    """
    from apps.backup import vigia  # noqa: PLC0415 - o app de backup não é dependência dos alertas

    estado = vigia.situacao(configuracao, agora)
    relatorio = Relatorio(rotina="backup", assunto="Cópia do programa no GitHub",
                          caminho=estado.caminho)
    relatorio.manchete = estado.titulo
    relatorio.resumo = estado.titulo
    relatorio.tem_noticia = estado.tem_noticia
    if not estado.tem_noticia:
        return relatorio
    relatorio.blocos.append(Bloco(
        titulo="O que está acontecendo",
        frase=estado.frase,
        link=estado.caminho, link_rotulo="Abrir a tela Cópia do programa",
    ))
    if estado.precisa_de_voce:
        relatorio.blocos.append(Bloco(
            titulo="Por que isto chegou até você",
            frase=("O envio para o GitHub é automático, mas a autorização não pode ser: o "
                   "GitHub exige que uma pessoa dê a permissão, e é isso que impede um "
                   "programa de escrever na conta de alguém sozinho. Este é o único passo "
                   "do backup que precisa de você."),
        ))
    return relatorio


MONTADORES = {
    "contas": contas_a_pagar,
    "vendas": vendas_do_dia,
    "estoque": estoque,
    "compra": sugestao_de_compra,
    "backup": backup_no_github,
}


def montar(rotina, **argumentos):
    """O relatório de uma rotina, pelo nome que o comando e a tela usam."""
    return MONTADORES[rotina](**argumentos)


def de_teste():
    """O e-mail do botão "enviar teste": prova o caminho sem prometer conteúdo."""
    relatorio = Relatorio(
        rotina="teste",
        assunto="Teste de envio",
        manchete="Se esta mensagem chegou, o sistema consegue mandar e-mail.",
        resumo="Teste de configuração.",
        tem_noticia=True,
        caminho="/sistema/alertas/",
    )
    agora = timezone.localtime()
    relatorio.blocos.append(Bloco(
        titulo="O que isto prova",
        frase=(f"O servidor da loja alcançou o servidor de e-mail e foi aceito, às "
               f"{agora:%H:%M de %d/%m/%Y}. Os relatórios de verdade vão sair nos horários "
               f"configurados, e só quando tiverem alguma notícia."),
        link="/sistema/alertas/", link_rotulo="Abrir a configuração",
    ))
    return relatorio


def contas_em_aberto(importacao):
    """Quantas contas a pagar existem em aberto. Usado pela tela de configuração."""
    if importacao is None:
        return 0
    return Lancamento.objects.filter(
        importacao=importacao, tipo=Lancamento.Tipo.PAGAR, pagamento__isnull=True
    ).count()
