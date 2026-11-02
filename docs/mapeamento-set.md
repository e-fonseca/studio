# Mapeamento do banco do SET (Firebird)

Descoberto em 05/10/2026 numa cópia do banco (ODS 13.0, Firebird 4), aberta só para leitura
fora do servidor. A estrutura não é documentada pelo fornecedor e pode mudar em atualizações:
cada carga deve conferir as tabelas e colunas abaixo antes de importar.

## Empresas (`EMPRESA`)

| IDEMPRESA | Nome | Uso |
|---|---|---|
| 1 | CABANA DO JACARANDÁ | Loja física; quase todas as vendas desde 2015 |
| 2 | STUDIO CABANA SUL | 13 vendas (11/2025 a 08/2026) |
| 3 | SITE CABANA | 48 vendas (09/2025 a 07/2026) |

## Tabelas usadas

| Dado | Tabela e colunas | Ligação | Observações |
|---|---|---|---|
| Produto | `PRODUTOS`: `IDPRODUTO`, `NPROD` (código), `DESCRICAO`, `GRUPO`, `PRECOCUSTO`, `PRECOCOMPRA`, `PRECOVENDA`, `PLUCRO`, `QTDEMIN`, `QTDEMAX`, `SITUACAO`, `DATACAD` | `NPROD` liga vendas e compras | 11.274 produtos; 2.747 ativos têm mínimo cadastrado. `PLUCRO` é o "% de lucro": apesar do nome é **markup** sobre o custo (docs/margem-e-markup.md) |
| Estoque atual | `PRODUTOS_ESTOQUE`: `EMPRESA`, `IDPRODUTO`, `QTDE`, `QTDE_RESERVADO` | `IDPRODUTO` | **Fonte do saldo.** Bate com o histórico de movimentação em 82% dos itens. `PRODUTOS.QTDEDISP` bate só em 44% e não deve ser usado |
| Venda | `VENDAS`: `IDVENDA`, `NVENDA`, `EMPRESA`, `DATAVENDA`, `HORAVENDA`, `TOTALVENDA`, `TOTALDESC`, `TOTALPROD`, `FORMAPAGTO`, `VENDEDOR`, `STATUS` (`Faturado`, `a Faturar`, `Estornado`) | `NVENDA` + `EMPRESA` | Excluir `Estornado`. Importada venda a venda desde a 1.16.0 (ticket médio). `TOTALPROD` (os produtos antes do desconto do fechamento) desde a 1.46.0, preenchido em todas. **`NOMECLI`, `COMPRADOR` e `COMPRADOR_CPF` existem e não são lidos** |
| Item de venda | `IVENDAS`: `NVENDA`, `EMPRESA`, `NPROD`, `QTDE`, `VALORTOTAL`, `PRECOCUSTO` (às vezes vazio), `TROCA_DEV` | `NVENDA` + `EMPRESA` | 417 mil itens no total, 32.034 nos últimos 12 meses; nenhum marcado como troca/devolução. Importado item a item desde a 1.24.0 (vendas do dia). **`PRECOCUSTO` é o custo NO DIA DA VENDA** e o SET parou de gravá-lo: até 24/08/2026 faltava em 0,5% dos itens, de 25/08/2026 em diante falta em 70% a 100% deles (docs/vendas-do-dia.md). `VALORPROD` (o preço cobrado) e `PRECOVENDA` (o de tabela no dia) desde a 1.46.0: o cobrado vem em todos; **o de tabela parou em julho de 2026** (falta em 3.563 dos 4.068 itens de julho e em 1.099 dos 1.104 de setembro) e é trocado pelo do cadastro, marcado (docs/descontos-e-metas.md) |
| Recebimento da venda | `ICAIXA` com `TIPO = 'R'`: `IDVENDA`, `USUARIO` | `IDVENDA` | Quem registrou o recebimento no caixa: existe em 16.334 das 16.361 vendas de 12 meses, ao contrário do `VENDEDOR`. Lido desde a 1.46.0 (descontos). **`CLIFORNE` pode ter nome de cliente e não é lido** |
| Partes do pagamento | `FATVENDAS`: `IDVENDA`, `FORMAPAGTO`, `VALOR` | `IDVENDA` | Uma linha por forma usada, já sem o troco: a soma dá o total da venda em 16.309 das 16.336 vendas de 12 meses. 117 vendas em mais de uma parte, 88 em formas diferentes. Lido desde a 1.46.0. **`OBSERVACAO` pode ter nome de cliente e não é lida** |
| Compra | `COMPRAS`: `NCOMPRA`, `EMPRESA`, `DATAPEDIDO`, `NFDATA`, `DATAENTREGA`, `FORNECEDOR`, `VLTOTAL`, `SITUACAO` (`Entregue / Faturado`, `Pendente`) | `NCOMPRA` + `EMPRESA` | `DATACOMPRA` parou em 2024; usar `NFDATA` ou `DATAPEDIDO`. **`Pendente` é pedido ainda não recebido**: não conta como compra feita, entra como mercadoria a caminho |
| Item de compra | `ICOMPRA`: `NCOMPRA`, `NPROD`, `DESCRICAO`, `QTDE`, `FATCONVERSAO`, `CUSTOUN`, `CUSTOTOTAL` | `NCOMPRA` + `EMPRESA` | 338 compras e 7.398 itens na cópia de 20/09/2026; entram inteiros na importação desde a 1.14.0. `COMPRAS.COMPRADOR` diz quem comprou |
| Movimentação | `PRODMOV` (cabeçalho) e `IPRODMOV` (itens: `NPROD`, `TIPO`, `QTDEENT`, `QTDEANT`) | `CODIGO` = `CODIGOMOVIMENTO` | Histórico de entradas e saídas com saldo anterior; dados desde 2024 |
| Código de barras | `PRODUTOS.CODBARRAS` | `NPROD` | EAN-13 gerado pelo próprio SET; 11.268 dos 11.274 produtos têm, todos diferentes. É o que vai na etiqueta da prateleira e é o que o leitor devolve. `PRODUTOS_CODBARRAS` (vários códigos por produto) existe e está vazia |
| Contagem de estoque | `CONFERENCIA_ESTOQUE`, `ICONFERENCIA_ESTOQUE` | | **Vazias.** O SET tem a tela de conferência e a loja nunca a usou. Por isso a contagem física acontece no sistema novo (módulo de inventário), que compara e não escreve nada aqui |
| Fornecedor | `FORNECEDORES`, `PRODUTOSFORNE` | `IDFORNECEDOR`, `IDPRODUTO` | Tem dados bancários e CPF: extrair só nome e contato |

## Financeiro e clientes (descoberto em 07/10/2026)

O SET já tem o financeiro lançado e classificado. O sistema copia e não inventa categoria.

| Dado | Tabela e colunas | Observações |
|---|---|---|
| Conta a pagar | `CONTASPAG`: `IDCONTAPAG`, `NOMECONTA`, `NDOC`, `PARCELA`, `SITUACAO` (`Paga`, `a Pagar`), `DATAVENCTO`, `DATAPAG`, `VALOR`, `VALORPAG`, `FORNECEDOR`, `GRUPO`, `IDPLANOCONTA`, `IDCOMPRA`, `EMPRESA` | 7.478 no total, 7.242 da empresa 1. `GRUPO` já traz o texto da classificação ("1.01.05 - Aluguel") |
| Conta a receber | `CONTASREC`: mesmas colunas, com `CLIENTE`, `IDCLIENTE` e `IDVENDA` | 44.229; quase tudo já recebido, porque a loja vende à vista |
| Plano de contas | `PLANODECONTA`: `IDPLANOCONTA`, `DESCRICAO`, `TIPO` (`Despesas`/`Receitas`), `FLUXO`, `CODHIERARQUIA` | 77 contas, em hierarquia 1.01.05 |
| Conta fixa | `CONTASPAGFIXA` | 25; despesa que se repete todo mês |
| Cliente | `CLIENTES`: `IDCLIENTE`, `COD`, `RAZAO`, `FANTASIA`, `TIPO` (`F`/`J`), `CIDADE`, `UF`, `DATACAD`, `BLOQUEADO` | 241. **Tem CPF, RG, nome dos pais, renda do cônjuge e mais de cem colunas: só as da esquerda são importadas** |

- `VENDAS.IDCLIENTE` e `CONTASREC.IDCLIENTE` guardam o **COD** do cliente, em texto com zeros à
  esquerda (`'0083'`), e não o `IDCLIENTE` numérico. Comparar com número dá erro de conversão.
- `'0083'` é CONSUMIDOR FINAL, o cliente genérico do balcão: 43.397 das 43.578 vendas com cliente
  estão nele. Sem separar, ele parece o maior cliente da loja.
- 154.057 vendas (R$ 12,3 milhões) não têm cliente nenhum: é venda de balcão sem identificação.
- `VENDAS.FORMAPAGTO` vem preenchido em todas as vendas (ao contrário de `CONTASPAG.FORMAPAGTO`),
  mas `VENDAS.VENDEDOR` está vazio em 11.499 das 16.414 vendas da cópia de 20/09/2026, ou seja em
  7 de cada 10: comparar vendedores só passa a valer se a loja lançar a venda no nome de quem
  vendeu. `VENDAS.OPERADOR` é sempre nulo e não serve nem de filtro. De abril a setembro de 2026 o
  `VENDEDOR` veio em 2 das 8.028 vendas; a tela de descontos (1.46.0) usa quem recebeu no
  caixa (`ICAIXA.USUARIO`).
- As vendas se concentram no fim de semana: **76% do faturamento de 12 meses sai no sábado e no
  domingo**. Qualquer média semanal que não separe os dias esconde isso.
- Ticket médio de 12 meses na cópia de 20/09/2026: 16.361 vendas, R$ 1.538.337,77, R$ 94,02 por
  venda.
- `CONTASPAG.FORMAPAGTO` está vazio em 3.398 registros e `TIPODOC` em 6.998: não dá para usar
  essas colunas como classificação.

## Achados de qualidade dos dados

- 95 itens em `ICOMPRA` e 14 em `IVENDAS` não têm o cabeçalho correspondente em `COMPRAS`/`VENDAS`; ficam de fora das somas (o `join` os descarta) e são contados no log de cada importação.
- 2 códigos de `ICOMPRA` e 11 de `IVENDAS` não existem em `PRODUTOS` (produto apagado depois do movimento); também ficam de fora.
- Das 328 compras com data de pedido e de entrega, 195 têm as duas iguais: o SET grava a data da nota, não o prazo do fornecedor. Por isso a mediana geral dá 0 dia e a sugestão de quando repor sai curta (pergunta 11 em perguntas-pendentes.md).
- 1.456 produtos com estoque negativo: venda sem entrada registrada (compra não lançada ou contagem antiga).
- O prazo de entrega não é confiável: pedido e entrega costumam ter a mesma data.
- Itens vendidos por peso (KG/KL na descrição) e itens genéricos (`DIVERSOS`, `ETIQUETA ...`, `CONSUMO PROPRIO`, `PEDRAS UNIDADE`) precisam de tratamento próprio.
- `PRODUTOS.CODBARRAS` tem EAN-13 em 11.268 dos 11.274 produtos, todos gerados pelo próprio SET e
  **todos começando em zero**. O leitor pela câmera devolve um EAN-13 começado em zero como UPC-A de
  12 dígitos, sem o zero da frente (`0000000000024` volta como `000000000024`): a busca tem que
  aceitar as duas formas, e é o que `apps/core/barras.variantes` faz.
- Texto em WIN1252 com caracteres inválidos em alguns registros: ler com charset `NONE` e decodificar como cp1252.
