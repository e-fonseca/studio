"""Os relatórios do inventário, montados uma vez e entregues em papel ou em planilha.

Pedido do Edson em 22/10/2026: o relatório comparando o SET com a nossa leitura, o
relatório de descartes e o relatório de conserto.

Cada um é montado UMA vez, chamando blocos que tanto o `pdf.Relatorio` quanto a
`planilha.Planilha` sabem receber — o mesmo arranjo de `apps/financeiro/relatorio.py`,
pelo mesmo motivo: montados em funções separadas, os dois começariam iguais e
divergiriam na primeira correção, e aí os dois relatórios da mesma tela passariam a
dizer números diferentes.

Os valores andam embrulhados em `apps.core.celula`: no papel viram o texto que a tela
mostra, na planilha viram número de verdade — dinheiro que soma, data que ordena,
contagem que filtra.
"""

from decimal import Decimal

from apps.core import celula, pdf

from . import conferencia as conferencia_do_set
from . import organizar

ZERO = Decimal("0")


def _quem(usuario):
    if usuario is None or not getattr(usuario, "is_authenticated", False):
        return ""
    return usuario.get_full_name() or usuario.get_username()


# -- o SET contra a nossa contagem ---------------------------------------------


def subtitulo_da_divergencia(contagem, resumo):
    """A linha abaixo do título: o que foi contado, quando e contra qual foto do SET."""
    partes = [contagem.nome]
    if contagem.fechada_em:
        partes.append(f"fechada em {contagem.fechada_em:%d/%m/%Y}")
    else:
        partes.append("ainda em contagem")
    corte = getattr(contagem.importacao, "data_corte", None)
    if corte:
        partes.append(f"saldo do SET de {corte:%d/%m/%Y}")
    partes.append(f"{resumo.divergentes} de {resumo.contados} produtos diferentes")
    return " · ".join(partes)


def montar_divergencia(relatorio, *, contagem, resumo, conferencia=None):
    """O comparativo entre o que o SET diz e o que foi contado na prateleira."""
    relatorio.destaques([
        ("Produtos contados", celula.Inteiro(resumo.contados)),
        ("Conferem com o SET", celula.Inteiro(resumo.conferem)),
        ("Diferentes", celula.Inteiro(resumo.divergentes)),
        ("Falta na prateleira", celula.Dinheiro(resumo.valor_da_falta)),
        ("Sobra na prateleira", celula.Dinheiro(resumo.valor_da_sobra)),
    ])

    relatorio.paragrafo(
        "O acerto do saldo é digitado no SET, uma linha por vez: este sistema lê o "
        "backup do SET e nunca escreve nele.", cor=pdf.CINZA,
    )
    if conferencia is not None and conferencia.disponivel:
        corte = getattr(conferencia.importacao, "data_corte", None)
        quando = f" de {corte:%d/%m/%Y}" if corte else ""
        relatorio.paragrafo(
            f"Conferido com o backup{quando}: {conferencia.entraram} ajustes já entraram "
            f"no SET, {conferencia.falta_ajustar} ainda não.", fonte=pdf.NEGRITO,
        )
    elif conferencia is not None:
        relatorio.paragrafo(
            "A conferência de quais ajustes entraram no SET aparece aqui depois da "
            "próxima importação, que lê o backup novo.", cor=pdf.CINZA,
        )
    relatorio.espaco(8)

    if not resumo.itens_divergentes:
        relatorio.paragrafo("Nenhuma diferença: a prateleira bate com o SET em tudo o "
                            "que foi contado.", fonte=pdf.NEGRITO)
        return

    # A conferência indexada pelo item, para a coluna de "entrou" saber o que dizer sem
    # uma segunda varredura por linha.
    por_item = {}
    if conferencia is not None and conferencia.disponivel:
        por_item = {linha.item.pk: linha for linha in conferencia.linhas}

    colunas = [
        pdf.Coluna("Código", 70),
        pdf.Coluna("Produto", 190),
        pdf.Coluna("No SET", 52, direita=True),
        pdf.Coluna("Contado", 52, direita=True),
        pdf.Coluna("Diferença", 58, direita=True),
        pdf.Coluna("Valor", 68, direita=True),
    ]
    if por_item:
        colunas.append(pdf.Coluna("No SET hoje", 92))
    linhas = []
    for item in resumo.itens_divergentes:
        # Falta sai em vermelho porque é a que vira prejuízo: a loja vendeu o que o SET
        # achava que tinha e ninguém deu baixa.
        cor = pdf.VERMELHO if item.diferenca < 0 else pdf.PRETO
        linha = [
            item.codigo,
            item.descricao,
            celula.Inteiro(int(item.saldo_set)) if item.saldo_set == int(item.saldo_set)
            else f"{item.saldo_set:f}",
            celula.Inteiro(int(item.quantidade)) if item.quantidade == int(item.quantidade)
            else f"{item.quantidade:f}",
            (f"{item.diferenca:+f}".rstrip("0").rstrip("."), cor),
            (celula.Dinheiro(item.valor_da_diferenca), cor),
        ]
        if por_item:
            conferida = por_item.get(item.pk)
            linha.append(conferida.recado if conferida else "produto saiu do SET")
        linhas.append(linha)
    relatorio.tabela(colunas, linhas, principal=True)
    relatorio.total("Diferença em dinheiro",
                    celula.Dinheiro(resumo.diferenca_em_dinheiro))

    if resumo.nao_contados:
        relatorio.espaco(6)
        relatorio.paragrafo(
            f"{resumo.nao_contados} produtos do SET não passaram pelo leitor nesta "
            "contagem, e por isso não aparecem acima.", cor=pdf.CINZA,
        )


# -- descarte e conserto -------------------------------------------------------


def _tabela_de_pecas(relatorio, itens, *, rotulo_do_total):
    """A tabela comum ao descarte e ao conserto: a peça, de onde veio e quanto vale."""
    colunas = [
        pdf.Coluna("Código", 70),
        pdf.Coluna("Produto", 180),
        pdf.Coluna("Unidades", 56, direita=True),
        pdf.Coluna("Valor ao custo", 76, direita=True),
        pdf.Coluna("Contagem", 110),
        pdf.Coluna("Marcado em", 70),
    ]
    linhas = []
    total = ZERO
    for item in itens:
        valor = item.valor_no_custo
        total += valor or ZERO
        linhas.append([
            item.codigo,
            item.descricao,
            celula.Inteiro(int(item.quantidade)) if item.quantidade == int(item.quantidade)
            else f"{item.quantidade:f}",
            celula.Dinheiro(valor),
            item.contagem.nome,
            celula.Data(item.estado_em.date() if item.estado_em else None, vazio="—"),
        ])
    relatorio.tabela(colunas, linhas, principal=True)
    relatorio.total(rotulo_do_total, celula.Dinheiro(total))
    return total


def montar_descarte(relatorio, *, itens):
    """As peças sem aproveitamento, que saem do estoque e do dinheiro da loja."""
    total = sum(((item.valor_no_custo or ZERO) for item in itens), ZERO)
    relatorio.destaques([
        ("Peças a descartar", celula.Inteiro(len(itens))),
        ("Unidades", celula.Inteiro(int(sum((item.quantidade for item in itens), ZERO)))),
        ("Perda ao custo", celula.Dinheiro(total)),
    ])
    relatorio.paragrafo(
        "Peça marcada na contagem como danificada e classificada para descarte: não "
        "tem conserto que se pague e não volta para a prateleira.",
    )
    relatorio.paragrafo(
        "A baixa é digitada no SET por uma pessoa, e só depois dela o estoque e o "
        "custo da loja ficam certos. Este sistema lê o backup do SET e nunca escreve "
        "nele.", cor=pdf.CINZA,
    )
    relatorio.espaco(8)
    if not itens:
        relatorio.paragrafo("Nenhuma peça esperando descarte.", fonte=pdf.NEGRITO)
        return
    _tabela_de_pecas(relatorio, itens, rotulo_do_total="Perda total ao custo")
    relatorio.espaco(6)
    relatorio.paragrafo(
        "Conferir com a contabilidade antes de dar baixa: perda de estoque tem "
        "tratamento fiscal próprio e a nota de entrada já foi lançada.", cor=pdf.CINZA,
    )


def montar_conserto(relatorio, *, itens):
    """As peças que valem um reparo e podem voltar a ser vendidas."""
    total = sum(((item.valor_no_custo or ZERO) for item in itens), ZERO)
    relatorio.destaques([
        ("Peças para conserto", celula.Inteiro(len(itens))),
        ("Unidades", celula.Inteiro(int(sum((item.quantidade for item in itens), ZERO)))),
        ("Valor que se recupera", celula.Dinheiro(total)),
    ])
    relatorio.paragrafo(
        "Peça marcada na contagem como danificada e classificada para conserto: vale o "
        "reparo e volta para a venda.",
    )
    relatorio.paragrafo(
        "O valor da coluna é o custo da peça, que é o que se recupera ao consertar — "
        "não é o preço do reparo, que o sistema não tem.", cor=pdf.CINZA,
    )
    relatorio.espaco(8)
    if not itens:
        relatorio.paragrafo("Nenhuma peça esperando conserto.", fonte=pdf.NEGRITO)
        return
    _tabela_de_pecas(relatorio, itens, rotulo_do_total="Valor ao custo das peças")
    relatorio.espaco(6)
    relatorio.paragrafo(
        "Ao voltar da oficina, marcar a peça como resolvida na tela Organizar: é o que "
        "a tira desta lista.", cor=pdf.CINZA,
    )


# -- parados -------------------------------------------------------------------


def montar_parados(relatorio, *, itens, meses=organizar.MESES_PARADO):
    """Os produtos com peça na prateleira e sem venda há muito tempo."""
    total = sum(((item.valor or ZERO) for item in itens), ZERO)
    encalhados = [item for item in itens if item.encalhado]
    relatorio.destaques([
        ("Produtos parados", celula.Inteiro(len(itens))),
        (f"Há mais de {organizar.MESES_ENCALHADO} meses", celula.Inteiro(len(encalhados))),
        ("Dinheiro parado ao custo", celula.Dinheiro(total)),
    ])
    relatorio.paragrafo(
        f"Produto com peça na prateleira e nenhuma unidade vendida há mais de {meses} "
        "meses. A peça está perfeita: o que está errado é que ela não sai.",
    )
    relatorio.espaco(8)
    if not itens:
        relatorio.paragrafo("Nenhum produto parado.", fonte=pdf.NEGRITO)
        return
    relatorio.tabela(
        [
            pdf.Coluna("Código", 66),
            pdf.Coluna("Produto", 170),
            pdf.Coluna("Grupo", 92),
            pdf.Coluna("Estoque", 50, direita=True),
            pdf.Coluna("Valor ao custo", 74, direita=True),
            pdf.Coluna("Última venda", 72),
            pdf.Coluna("Meses", 44, direita=True),
        ],
        [
            [
                item.codigo,
                item.descricao,
                item.grupo,
                celula.Inteiro(int(item.estoque)) if item.estoque == int(item.estoque)
                else f"{item.estoque:f}",
                celula.Dinheiro(item.valor),
                celula.Data(item.ultima_venda, vazio="nunca vendeu"),
                (celula.Inteiro(item.meses_sem_vender),
                 pdf.VERMELHO if item.encalhado else pdf.PRETO),
            ]
            for item in itens
        ],
        principal=True,
    )
    relatorio.total("Dinheiro parado ao custo", celula.Dinheiro(total))


# -- o plano de contagem -------------------------------------------------------


def montar_plano(relatorio, *, plano):
    """O plano de contagem cíclica: o prazo de cada classe e o que está vencido."""
    relatorio.destaques([
        ("Produtos com peça na prateleira", celula.Inteiro(plano.produtos)),
        ("Esperando contagem", celula.Inteiro(plano.a_contar)),
        ("Nunca contados", celula.Inteiro(plano.nunca_contados)),
        ("Valor ao custo do que falta contar", celula.Dinheiro(plano.valor_a_contar)),
    ])
    relatorio.paragrafo(
        "Contagem cíclica: conta-se um pedaço por vez, sempre, e o pedaço sai da curva "
        "ABC — o produto que sustenta a loja é contado todo mês, o que quase não vende, "
        "duas vezes por ano.",
    )
    relatorio.espaco(8)
    relatorio.tabela(
        [
            pdf.Coluna("Classe", 150),
            pdf.Coluna("Contar a cada", 76, direita=True),
            pdf.Coluna("Produtos", 60, direita=True),
            pdf.Coluna("Em dia", 56, direita=True),
            pdf.Coluna("Vencidos", 62, direita=True),
            pdf.Coluna("Nunca contados", 86, direita=True),
            pdf.Coluna("Valor vencido", 80, direita=True),
        ],
        [
            [
                classe.rotulo,
                celula.Inteiro(classe.cada_dias, sufixo=" dias"),
                celula.Inteiro(classe.produtos),
                celula.Inteiro(classe.em_dia),
                (celula.Inteiro(classe.vencidos),
                 pdf.VERMELHO if classe.vencidos else pdf.PRETO),
                (celula.Inteiro(classe.nunca_contados),
                 pdf.VERMELHO if classe.nunca_contados else pdf.PRETO),
                celula.Dinheiro(classe.valor_vencido),
            ]
            for classe in plano.classes
        ],
    )
    relatorio.espaco(10)
    if not plano.sugeridos:
        relatorio.paragrafo("Nada vencido: o plano está em dia.", fonte=pdf.NEGRITO)
        return
    relatorio.paragrafo(
        f"Para contar agora, os {len(plano.sugeridos)} primeiros — classe mais urgente "
        "na frente e, dentro dela, o maior dinheiro na prateleira",
        fonte=pdf.NEGRITO, espaco=3,
    )
    relatorio.tabela(
        [
            pdf.Coluna("Código", 66),
            pdf.Coluna("Produto", 180),
            pdf.Coluna("Classe", 44),
            pdf.Coluna("Estoque", 52, direita=True),
            pdf.Coluna("Valor ao custo", 76, direita=True),
            pdf.Coluna("Contado em", 72),
            pdf.Coluna("Atraso", 50, direita=True),
        ],
        [
            [
                item.codigo,
                item.descricao,
                item.classe or "sem venda",
                celula.Inteiro(int(item.estoque)) if item.estoque == int(item.estoque)
                else f"{item.estoque:f}",
                celula.Dinheiro(item.valor),
                celula.Data(item.contado_em.date() if item.contado_em else None,
                            vazio="nunca"),
                celula.Inteiro(item.atraso_dias, sufixo="d"),
            ]
            for item in plano.sugeridos
        ],
        principal=True,
    )


RECADOS_DA_CONFERENCIA = conferencia_do_set.RECADOS
