# Relatório em PDF

Pedido do Edson em 13/10/2026: "CONTAS A PAGAR = Campo pesquisa, gerar relatorios para
impressao pdf".

O PDF sai em `/sistema/financeiro/pdf/`, pelo botão que fica logo abaixo dos filtros na
tela de contas a pagar. Ele obedece ao **filtro e à busca que estiverem na tela**: a view
usa o mesmo `_lista_pedida` dos dois lados, então papel e tela nunca mostram contas
diferentes.

## O botão fica com a lista, e diz o nome dela (1.27.0)

Na 1.25.0 o botão nasceu dentro do cartão "Procurar uma conta", **acima** da fileira de
filtros, dizendo "Gerar PDF desta lista para imprimir". Tecnicamente ele já gerava o PDF
de qualquer uma das seis listas, porque o link sempre levou `?filtro=`; mas quem lê a tela
de cima para baixo vê busca, botão, e só depois as seis listas — e conclui que o botão é
da busca, ou de uma lista só. Foi exatamente o que aconteceu: em 14/10/2026 o Edson pediu
"disponibilizar relatório para impressão em todas as listas do contas a pagar".

O conserto é de lugar e de nome. O botão desceu para **entre os filtros e a tabela**, e
passou a se chamar pela lista escolhida: "Gerar PDF de Atrasados para imprimir", "Gerar
PDF de Programação futura para imprimir". Ao lado dele, uma linha diz que trocando a lista
acima o botão passa a gerar a outra. O nome vem de `servicos.rotulo_do_filtro`, o mesmo
que o PDF usa no subtítulo: a tela e o papel chamam a lista pelo mesmo nome.

O botão aparece **em todas as seis listas, inclusive nas vazias**. Sumir numa lista vazia
devolveria a dúvida de "por que esta aqui não imprime?"; o PDF de lista vazia sai com
"Nenhuma conta nesta lista".

### E o papel diz onde a lista se encaixa

Quem recebe a folha não está olhando a tela, e "2 contas" sozinho não diz se é muito ou
pouco. Por isso o PDF traz, antes da tabela, as **seis listas com a contagem e o valor de
cada uma**, com a impressa marcada em marrom: `Do dia (esta)`. São os mesmos números dos
botões da tela, da mesma `filtros_de_contas`.

Um PDF que juntasse as seis listas numa folha só foi considerado e descartado: elas se
sobrepõem (`Todas em aberto` = `Atrasados` + `A vencer`, e `A vencer` = `Do dia` +
`Prestes a vencer` + `Programação futura`), então o papel repetiria as mesmas contas três
vezes. O panorama em números dá a mesma visão sem a repetição.

## Por que o PDF é escrito aqui dentro

`apps/core/pdf.py` não usa biblioteca nenhuma.

A mais usada para isto (fpdf2) traz junto Pillow e fonttools: cerca de **12 MB de
extensões compiladas**, para desenhar uma tabela de texto. O pacote da loja é instalado
**sem internet**, a partir das rodas que vão dentro do zip, e uma roda errada já custou
uma versão inteira — a 1.22.0 parou no meio da instalação e deixou a loja sem sistema.

Um PDF de tabela é um formato simples de escrever: cabeçalho, objetos numerados, um
fluxo de texto e a tabela de posições no fim. Helvetica e Helvetica-Bold são duas das
catorze fontes que todo leitor de PDF já tem, então não é preciso embutir arquivo de
fonte: basta declarar a codificação **WinAnsi**, que é a cp1252 e cobre todo acento do
português.

## O que ele faz, e o que não faz

Faz: A4 em pé ou deitado, título, linhas de texto, números em destaque no topo, tabela
com cabeçalho repetido a cada página, coluna à esquerda ou à direita, zebra, linha de
total, e rodapé com "página 1 de 3", a data de emissão e quem emitiu.

Não faz: imagem, cor fora do marrom e dos cinzas da loja, e quebra de linha dentro da
célula — texto que não cabe é cortado com reticências. Nada disso faz falta num relatório
de contas, e cada coisa que não existe é uma coisa que não quebra.

### A medida das letras

A tabela de larguras oficiais da Helvetica está no módulo, em milésimos do tamanho da
letra. É ela que faz a coluna de dinheiro ficar **alinhada à direita de verdade** (sem
ela, cada linha erraria a posição por um tanto diferente e a borda direita ficaria
esfarrapada) e o texto ser cortado na hora certa. Letra com acento tem a largura da letra
sem acento, então `Á` mede o mesmo que `A` e não precisa entrar na tabela.

### Acento

O fluxo da página é gravado em **cp1252**, que é o que a fonte declara. Gravar em
latin-1, que é parecido, transformaria o travessão em `?` — foi o primeiro defeito achado
ao conferir o arquivo gerado.

## O relatório de contas a pagar

Colunas: Vencimento, Atraso (em vermelho), Conta, Parcela, Fornecedor e Valor. A
classificação do plano de contas fica **de fora do papel** de propósito: é quase sempre a
mesma linha ("1.07.01 - Compra p/ Revenda") e comia a largura do nome do fornecedor, que
é o que se procura numa lista de contas. Para onde o dinheiro vai por classificação é a
tela de Despesas.

No topo vão os quatro números do resumo (vencidas, a vencer, previstos e compromisso
total) e, quando há busca, a linha "Procurado por:".

Tirar o relatório fica na trilha de auditoria: é uma lista do que a loja deve, com nome
de fornecedor, que sai impressa do sistema.

## O campo de pesquisa

Procura em fornecedor, descrição, documento, parcela e classificação, e **aceita com
acento ou sem**: quem digita "quiteria" acha "QUITÉRIA FLOR MILHO".

Isso é feito sem extensão do Postgres e sem dependência: `apps.core.texto.regex_sem_acento`
monta uma expressão regular em que cada letra vale por ela e pelas suas acentuadas
(`qu[iíìîï]t[eéèêë]r[aáàâãä]`), e a consulta usa `iregex`. Caractere de expressão regular
digitado sem querer — `(`, `*`, `[` — entra como texto, não como regra.

Quando há busca, **os filtros passam a contar só o que foi encontrado**. Senão o número
do filtro e o número da lista discordariam na tela, e quem lê acreditaria no errado.

## Arquivos

- `apps/core/pdf.py` — o escritor de PDF
- `apps/core/texto.py` — `regex_sem_acento`
- `apps/financeiro/views.py` — `contas_a_pagar_em_pdf` e `_lista_pedida`
- `apps/financeiro/servicos.py` — `_aplicar_busca` e `somar`
- `apps/financeiro/tests/test_financeiro.py` — `BuscaNasContasAPagar` e `RelatorioEmPdf`
