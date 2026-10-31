"""O pedido que se manda ao fornecedor, em PDF.

Pedido do Edson em 14/10/2026: "após análise da sugestão de compra automático e/ou
editável disponibilizar um botão para gerar o pedido para o fornecedor(es) com layout
da Cabana do Jacarandá e razão social da Essenza, endereço Largo do Jesuítas 64".

O papel sai da MESMA lista de compra da tela, já com as quantidades que a gerência
ajustou: é o fim do caminho que começa em "o que está faltando" e passa por "quanto
eu quero mesmo comprar". Não existe conta nova aqui — se o número do papel não for o
número da tela, o papel está errado.

Um fornecedor por folha, porque é uma folha por ligação: o maço sai da impressora e
se separa sem ninguém precisar ler para saber onde um pedido acaba e o outro começa.

O que este módulo NÃO faz, de propósito: não manda e-mail, não fala com o SET, não
guarda pedido enviado e não numera pedido. É uma folha para levar ao fornecedor ou
anexar numa mensagem, como o arquivo CSV já era. Pedido de verdade, com número e
acompanhamento, é outro assunto e ninguém pediu.

O cabeçalho vem de `DadosDaEmpresa`, que é tela: o fornecedor conhece a loja por
"Cabana do Jacarandá" e fatura para a razão social, e nenhum dos dois é valor escrito
no código, porque CNPJ e telefone mudam sem avisar.
"""

from decimal import Decimal

from apps.core import pdf
# O mesmo escritor de número das telas: o papel e a tela não podem escrever 12,5 de
# duas maneiras diferentes, senão quem confere um contra o outro desconfia dos dois.
from apps.core.templatetags.cabana import quantidade as escrever, reais

ZERO = Decimal("0")


def itens_do_pedido(bloco):
    """As linhas que vão no papel: tudo o que tem quantidade maior que zero.

    Quantidade ajustada para zero é a gerência dizendo "este não, agora". A linha
    continua na tela, explicando por que o sistema pediu, mas pedir zero unidade a um
    fornecedor não é pedido — é ruído no papel que ele vai ler.
    """
    return [item for item in bloco.itens if (item.quantidade or ZERO) > ZERO]


def _total(itens):
    return sum((item.valor_do_pedido for item in itens), ZERO)


def _timbre(relatorio, empresa):
    """Quem está comprando: razão social, endereço e contato, como num papel de carta.

    Desde a 1.35.0 o endereço da ENTREGA sai numa linha própria, quando é diferente do
    da nota. Na Cabana ele é: o CNPJ está na Rua Claudionor Assis Dias e a loja fica no
    Largo dos Jesuítas. O papel que o fornecedor lê trazia só o endereço da nota, e com
    isso a carga ia parar no endereço fiscal — erro que só aparece no dia da entrega.
    """
    if empresa.linha_do_endereco:
        relatorio.paragrafo(empresa.linha_do_endereco, tamanho=8.5, cor=pdf.CINZA, espaco=2)
    if empresa.linha_da_entrega:
        relatorio.paragrafo(f"Entregar em: {empresa.linha_da_entrega}",
                            tamanho=8.5, fonte=pdf.NEGRITO, cor=pdf.MARROM, espaco=2)
    linhas = []
    if empresa.inscricao_estadual:
        linhas.append(f"Inscrição estadual {empresa.inscricao_estadual}")
    if empresa.linha_do_contato:
        linhas.append(empresa.linha_do_contato)
    if linhas:
        relatorio.paragrafo(" · ".join(linhas), tamanho=8.5, cor=pdf.CINZA, espaco=2)


def _um_pedido(relatorio, bloco, empresa, data_corte=None, observacao="", aviso=""):
    """Uma folha: o timbre da loja, para quem é o pedido e o que se está pedindo."""
    _timbre(relatorio, empresa)
    relatorio.espaco(6)
    relatorio.paragrafo(f"Para: {bloco.nome}", tamanho=14, fonte=pdf.NEGRITO,
                        cor=pdf.MARROM, espaco=4)
    if aviso:
        # No alto e em vermelho, antes da tabela: é a primeira coisa que o fornecedor
        # leria, se a folha chegasse até ele. Rodapé ninguém lê. Uma linha por linha do
        # aviso, porque `paragrafo` corta o que não cabe na largura da folha.
        linhas = [linha.strip() for linha in aviso.splitlines() if linha.strip()]
        for posicao, linha in enumerate(linhas):
            relatorio.paragrafo(linha, tamanho=12 if posicao == 0 else 10, fonte=pdf.NEGRITO,
                                cor=pdf.VERMELHO, espaco=6 if posicao == len(linhas) - 1 else 2)

    itens = itens_do_pedido(bloco)
    total = _total(itens)
    destaques = [
        ("Itens", str(len(itens))),
        ("Total do pedido", reais(total)),
    ]
    if bloco.prazo_dias is not None:
        prazo = f"{bloco.prazo_dias} dias" + (" (estimado)" if bloco.prazo_assumido else "")
        destaques.append(("Prazo de entrega", prazo))
    if bloco.ajustados:
        destaques.append(("Quantidades definidas pela loja", str(bloco.ajustados)))
    relatorio.destaques(destaques)

    if not itens:
        relatorio.paragrafo(
            "Nenhum item neste pedido: todas as quantidades deste fornecedor foram "
            "ajustadas para zero na lista de compra.", tamanho=9.5)
        return

    colunas = [
        pdf.Coluna("Código", 58),
        pdf.Coluna("Produto", 300),
        pdf.Coluna("Grupo", 110),
        pdf.Coluna("Quantidade", 66, direita=True),
        pdf.Coluna("Custo unit.", 72, direita=True),
        pdf.Coluna("Total", 80, direita=True),
    ]
    linhas = []
    for item in itens:
        # Quantidade mudada à mão sai em marrom: quem confere o pedido contra a tela
        # precisa ver qual linha é decisão de gente e qual é conta do sistema.
        quantidade = escrever(item.quantidade, vazio="0")
        linhas.append([
            item.codigo, item.descricao, item.grupo,
            (quantidade, pdf.MARROM) if item.foi_ajustada else quantidade,
            reais(item.custo) if item.custo is not None else "—",
            reais(item.valor_do_pedido),
        ])
    relatorio.tabela(colunas, linhas)
    relatorio.total("Total do pedido", reais(total))

    fora = len(bloco.itens) - len(itens)
    if fora:
        relatorio.espaco(4)
        relatorio.paragrafo(
            f"{fora} produto(s) da lista ficaram fora deste pedido porque a loja "
            "ajustou a quantidade para zero.", tamanho=8, cor=pdf.CINZA, espaco=3)
    if any(item.foi_ajustada for item in itens):
        relatorio.paragrafo(
            "As quantidades em marrom foram definidas pela loja; as demais são a "
            "reposição calculada pelo sistema.", tamanho=8, cor=pdf.CINZA, espaco=3)
    if any(item.custo is not None for item in itens):
        relatorio.paragrafo(
            "Os custos são os da última compra registrada e servem de referência: "
            "vale o preço que o fornecedor confirmar.", tamanho=8, cor=pdf.CINZA, espaco=3)
    if data_corte:
        relatorio.paragrafo(
            f"Estoque e venda conferidos nos dados de {data_corte:%d/%m/%Y}.",
            tamanho=8, cor=pdf.CINZA, espaco=3)
    recado = observacao or empresa.observacao
    if recado:
        relatorio.espaco(6)
        for linha in recado.splitlines():
            if linha.strip():
                relatorio.paragrafo(linha.strip(), tamanho=9)


def montar(blocos, empresa, data_corte=None, emitido_por="", observacao="", aviso=""):
    """O PDF dos pedidos, uma folha por fornecedor.

    Deitado (paisagem) porque a linha tem descrição longa, quantidade, custo e total,
    e em pé o nome do produto fica cortado — é justamente o que o fornecedor lê.
    """
    blocos = list(blocos)
    titulo = "Pedido de compra" if len(blocos) == 1 else f"Pedidos de compra · {len(blocos)} fornecedores"
    subtitulo = empresa.razao_social
    if empresa.nome_fantasia and empresa.nome_fantasia != empresa.razao_social:
        subtitulo = f"{empresa.razao_social} ({empresa.nome_fantasia})"
    if empresa.documento:
        subtitulo += f" · CNPJ {empresa.documento}"

    relatorio = pdf.Relatorio(titulo, subtitulo, paisagem=True, emitido_por=emitido_por)
    for posicao, bloco in enumerate(blocos):
        if posicao:
            relatorio.pagina_nova()
        _um_pedido(relatorio, bloco, empresa, data_corte=data_corte, observacao=observacao,
                   aviso=aviso)
    return relatorio


def nome_do_arquivo(blocos, data_corte=None):
    """Nome de arquivo que diz de quem é o pedido, para não virar "documento (3).pdf"."""
    import re

    data = f"-{data_corte:%Y-%m-%d}" if data_corte else ""
    blocos = list(blocos)
    if len(blocos) == 1:
        limpo = re.sub(r"[^a-zA-Z0-9]+", "-", blocos[0].nome).strip("-").lower()[:40]
        return f"pedido-{limpo or 'fornecedor'}{data}.pdf"
    return f"pedidos-{len(blocos)}-fornecedores{data}.pdf"
