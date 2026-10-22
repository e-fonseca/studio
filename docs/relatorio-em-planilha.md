# O relatório em planilha, ao lado do PDF (1.35.0)

Pedido do Edson em 19/10/2026: *"FINANCEIRO, permitir exportar além do pdf para planilha
de excel ajustado no mesmo layout"*.

## Onde fica

Na tela **Contas a pagar**, junto do botão do PDF, embaixo das seis listas. Os dois
botões levam a lista escolhida e a busca digitada; trocando a lista acima, os dois
passam a gerar a outra.

O arquivo sai como `contas-a-pagar.xlsx` e abre no Excel, no LibreOffice, no Google
Planilhas e no aplicativo do celular.

## O que ele tem que o PDF não tem

**Número de verdade na célula.** Dinheiro soma, data ordena, atraso filtra. Uma planilha
em que o valor é o texto "R$ 1.234,56" é um PDF mais feio: não soma coluna, não ordena
por vencimento, não filtra as contas de um fornecedor.

| No papel | Na planilha |
|---|---|
| `R$ 1.234,56` alinhado à direita | `1234.56` com formato de real |
| `01/09/2026` | data de verdade, que ordena |
| `48d` em vermelho | `48` em vermelho, que ordena do mais vencido |

**Cabeçalho congelado e filtro ligado** na tabela das contas. Na linha 400 ainda se sabe
de que coluna é cada número.

## "No mesmo layout": como isso é garantido

O relatório é montado **uma vez só**, em `apps/financeiro/relatorio.py`, chamando blocos
(`destaques`, `tabela`, `total`, `paragrafo`) que tanto o `pdf.Relatorio` quanto a
`planilha.Planilha` sabem receber. O PDF e a planilha são dois desenhos do mesmo
conteúdo, na mesma ordem, com as mesmas colunas.

Se fossem duas funções, começariam iguais e divergiriam na primeira correção — alguém
acrescenta uma fatia ao resumo no papel e esquece da planilha, e os dois relatórios da
mesma tela passam a dizer números diferentes. Foi exatamente esse defeito que a 1.34.0
consertou entre o Painel e a Visão geral.

Os valores andam entre o montador e os dois formatos embrulhados em
`apps/core/celula.py`: `Dinheiro`, `Inteiro` e `Data`. Cada um sabe escrever a si mesmo
como texto (é o que o papel imprime) e dizer que número é (é o que a célula guarda).

## As duas diferenças, de propósito

**Não há zebra.** A faixa cinza alternada ajuda o olho a seguir a linha no papel; na
planilha atrapalha a leitura com filtro ligado, e o Excel faz isso sozinho quando a
pessoa quer.

**Não há "página 1 de 3".** A planilha não tem página. O que o papel diz no rodapé de
toda folha — quem emitiu e quando — vai para a primeira linha, antes do título.

## Por que escrito à mão, sem biblioteca

Pelo mesmo motivo do PDF (`docs/` e o cabeçalho de `apps/core/pdf.py`): o pacote da loja
é instalado **sem internet**, a partir das rodas que vão dentro do zip, e cada
dependência nova é uma roda a mais para dar errado numa máquina que não dá para
acompanhar daqui. Uma roda errada já custou uma versão inteira (a 1.22.0 parou no meio e
deixou a loja sem sistema).

Um `.xlsx` é um zip com seis arquivos XML dentro, e tudo o que ele precisa — `zipfile` e
texto — já vem no Python. São cerca de 300 linhas em `apps/core/planilha.py`.

## Como conferir que continua valendo

`apps/core/tests/test_planilha.py` lê o arquivo gerado com `zipfile` e `xml.etree`, da
biblioteca padrão — ler com uma biblioteca de planilha provaria só que ela concorda
consigo mesma. Trava que o arquivo tem as peças que o Excel exige, que dinheiro e data
saem como número, que **a cor e o formato convivem na mesma célula** (foi o defeito desta
versão: o vermelho do atraso ganhava do formato e o número virava texto), e que texto com
`&` e `<` não quebra o arquivo.

`apps/financeiro/tests/test_financeiro.py` trava o resto: que a planilha traz as mesmas
contas do papel, que o filtro e a busca da tela valem nela, que o vendedor não baixa, e
que a saída fica na trilha de auditoria — é uma lista do que a loja deve, com nome de
fornecedor, saindo do sistema.
