# Sincronizar substitui, não soma (1.18.0)

O Edson desconfiou, em 07/10/2026, que os números cresciam a cada sincronização. Não
crescem. Este documento é a prova e o que foi posto no sistema para ele conferir sozinho.

## Por que não soma

Toda tabela de dado vindo do SET tem um campo `importacao`, e cada importação cria linhas
novas em vez de alterar as antigas. É o padrão de **foto por importação**:
`ProdutoImportado`, `VendaImportada`, `Lancamento`, `ClienteImportado`,
`FornecedorImportado`, `CompraImportada`, `ItemCompraImportada`, `CaixaImportado`. Toda
consulta de tela filtra por `importacao=`, e as telas sempre usam a última concluída. Nada
é acumulado: a importação de hoje não lê nem altera a de ontem.

`limpar_antigas(manter=10)` apaga as fotos mais velhas que as dez últimas concluídas, para
o banco não crescer sem parar. Isso não muda nenhum número: as fotos antigas não entram em
conta nenhuma. Quais modelos entram nessa limpeza é uma lista só, `fotos_fora_do_limite`,
que a limpeza automática e o `manage.py higienizar` usam juntas — ela ficou duplicada até
a 1.26.0 e o caixa havia ficado de fora ([higienizacao.md](higienizacao.md)).

## A conferência feita (07/10/2026)

A mesma cópia do backup foi importada três vezes seguidas, mudando só a data do arquivo
para passar pela trava de "backup não mudou". Em todas as três:

| Número | Importação 22 | 23 | 24 |
| --- | --- | --- | --- |
| Faturamento 12m | 1.576.325,86 | 1.576.325,86 | 1.576.325,86 |
| Compras | 519.248,39 | 519.248,39 | 519.248,39 |
| Estoque | 615.032,91 | 615.032,91 | 615.032,91 |
| Ticket médio | 94,02 (16.361 vendas) | igual | igual |
| Contas vencidas | 49 / 64.486,82 | igual | igual |
| Lista de compra | 2.238 / 184.405,84 | igual | igual |

E as linhas guardadas dividem exatamente pelo número de importações, sem sobra:
78.918 produtos em 7 importações = 11.274 por importação; 65.444 vendas em 4 = 16.361;
241.842 lançamentos em 6 = 40.307.

## O que entrou no sistema

`apps/importacao/comparacao.py` e um bloco novo na tela de Importações: as duas últimas
importações concluídas lado a lado, nove números, com a diferença calculada. Três recados
possíveis:

- verde, quando as duas leram o **mesmo arquivo** de backup e todos os números deram
  iguais — é a confirmação de que substitui;
- neutro, quando mudaram, dizendo que a diferença é o movimento da loja no período;
- vermelho, quando algum número **dobrou** de uma para a outra. Isso não deveria
  acontecer nunca, e é justamente o sintoma que o Edson descreveu.

Os testes em `apps/importacao/tests/test_comparacao.py` importam o mesmo dado duas e três
vezes e exigem que nada mude, inclusive no ticket médio. Se algum dia alguém escrever uma
consulta sem o filtro `importacao=`, eles quebram.

## Forçar a leitura do mesmo backup (1.23.0)

O botão **Forçar atualização com o último backup**, na tela de Importações, relê o backup
mais recente mesmo quando ele é o mesmo da importação anterior. Ele não muda nada do que
está acima: é a mesma importação, com a mesma foto por importação, então reler o mesmo
arquivo tem que dar exatamente os mesmos números — e a comparação da própria tela é onde
isso se vê. `test_forcar_a_leitura_do_mesmo_backup_tambem_nao_soma` trava esse caso.
Detalhe do botão e da conferência que roda antes dele em
[conferencia-do-backup.md](conferencia-do-backup.md).
