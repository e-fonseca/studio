"""O relatório de contas a pagar, montado uma vez e entregue em papel ou em planilha.

Pedido do Edson em 19/10/2026: *"FINANCEIRO, permitir exportar além do pdf para planilha
de excel ajustado no mesmo layout"*.

"No mesmo layout" é a parte difícil, e é por isso que este módulo existe. Se o PDF
fosse montado numa função e a planilha noutra, as duas começariam iguais e divergiriam
na primeira correção: alguém acrescenta uma fatia ao resumo no papel e esquece da
planilha, e aí os dois relatórios da mesma tela passam a dizer números diferentes —
que é exatamente o defeito que a 1.34.0 consertou entre o Painel e a Visão geral.

Aqui o relatório é montado UMA vez, chamando blocos (`destaques`, `tabela`, `total`)
que tanto o `pdf.Relatorio` quanto a `planilha.Planilha` sabem receber. O que muda
entre os dois é só o desenho de cada bloco, nunca o conteúdo nem a ordem.

Os valores andam embrulhados em `apps.core.celula`: no papel cada um vira o texto que
já saía, e na planilha vira número de verdade — dinheiro que soma, data que ordena,
contagem que filtra.
"""

from apps.core import celula, pdf
from apps.financeiro import servicos


def montar(relatorio, *, estado, hoje, escolhido, busca, contas, resumo, filtros):
    """Escreve o relatório inteiro no objeto recebido, seja ele papel ou planilha."""
    destaques = [
        ("Vencidas e em aberto", celula.Dinheiro(resumo.vencidas.valor)),
        ("A vencer", celula.Dinheiro(resumo.a_pagar.valor)),
    ]
    # Sem data no SET entra na folha só quando existe, mas aí entra: sem ela o
    # compromisso total não fecha com as parcelas de cima.
    if resumo.sem_data.quantidade:
        destaques.append(("Sem data de vencimento no SET",
                          celula.Dinheiro(resumo.sem_data.valor)))
    destaques += [
        ("Previstos registrados aqui", celula.Dinheiro(resumo.previstos.valor)),
        ("Compromisso total", celula.Dinheiro(resumo.compromisso_total)),
    ]
    relatorio.destaques(destaques)
    if busca:
        relatorio.paragrafo(f"Procurado por: {busca}", fonte=pdf.NEGRITO)

    # Quais são as seis listas da tela e onde a impressa se encaixa. Quem recebe a folha
    # não está olhando a tela, e sem isto "44 contas" não diz se é muito ou pouco.
    relatorio.paragrafo("As listas da tela, e esta entre elas", fonte=pdf.NEGRITO, espaco=3)
    relatorio.tabela(
        [pdf.Coluna("Lista", 230), pdf.Coluna("Contas", 60, direita=True),
         pdf.Coluna("Valor", 120, direita=True)],
        [
            [(f"{f['rotulo']} (esta)", pdf.MARROM) if f["chave"] == escolhido else f["rotulo"],
             celula.Inteiro(f["quantidade"]), celula.Dinheiro(f["valor"])]
            for f in filtros
        ],
        altura_da_linha=13, tamanho=8,
    )
    relatorio.espaco(10)

    if contas:
        # A classificação do plano de contas fica de fora do papel de propósito: é quase
        # sempre a mesma linha ("1.07.01 - Compra p/ Revenda") e comia a largura do nome
        # do fornecedor, que é o que se procura numa lista de contas. Para onde o dinheiro
        # vai por classificação é a tela de Despesas.
        colunas = [
            pdf.Coluna("Vencimento", 52), pdf.Coluna("Atraso", 38, direita=True),
            pdf.Coluna("Conta", 145), pdf.Coluna("Parcela", 40),
            pdf.Coluna("Fornecedor", 167), pdf.Coluna("Valor", 73, direita=True),
        ]
        linhas = [
            [
                celula.Data(conta.vencimento),
                (celula.Inteiro(conta.atraso, sufixo="d"), pdf.VERMELHO)
                if conta.atraso else "",
                conta.descricao or "—", conta.parcela or "", conta.contraparte or "—",
                celula.Dinheiro(conta.valor),
            ]
            for conta in contas
        ]
        # `principal` é a tabela que a pessoa veio ler: na planilha é ela que ganha o
        # cabeçalho congelado e o filtro. No papel não muda nada.
        relatorio.tabela(colunas, linhas, principal=True)
        relatorio.total("Total desta lista", celula.Dinheiro(servicos.somar(contas)))
        if any(c.atraso for c in contas):
            relatorio.espaco(4)
            relatorio.paragrafo(
                "Na coluna Atraso, os dias vencidos. Pode ser pagamento já feito e ainda não "
                "baixado no SET: confira antes de cobrar o setor.", tamanho=8, cor=pdf.CINZA)
    else:
        relatorio.paragrafo("Nenhuma conta nesta lista.")


def subtitulo_de(escolhido, contas, estado):
    """A linha embaixo do título: qual lista é, quantas contas e de quando é o dado."""
    rotulo = servicos.rotulo_do_filtro(escolhido)
    texto = f"{rotulo} · {len(contas)} conta{'s' if len(contas) != 1 else ''}"
    if estado.importacao and estado.importacao.data_corte:
        texto += f" · dados do SET de {estado.importacao.data_corte:%d/%m/%Y}"
    return texto
