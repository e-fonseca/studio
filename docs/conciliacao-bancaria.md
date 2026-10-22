# Conciliação bancária

Pedido do Edson em 13/10/2026: "CRIAR MODULO CONCILIAÇÃO BANCARIA, importar extratos dos
bancos e confrontar com a lista de pagamentos do contas a pagar".

A pergunta que o módulo responde é dupla: **saiu dinheiro da conta e está lançado no
SET?** E o contrário, **o SET diz que pagou e o banco confirma?** Quando os dois não
batem é sempre uma de três coisas — pagamento feito e não lançado, lançamento sem
pagamento, ou valor diferente do combinado — e nenhuma delas aparece sem conferir.

O sistema **só lê**. Não escreve no banco, não escreve no SET, não paga nada.

## Por onde se usa

`/sistema/conciliacao/` — lista de extratos importados e o formulário de trazer um novo.
`/sistema/conciliacao/<n>/` — um extrato aberto, linha a linha.

Permissão `conciliacao.conciliar_banco`, dada à gerência e ao operador administrativo
(quem lança pagamento é quem confere o banco). O operador vendedor não entra.

## O arquivo do banco

| Formato | Onde achar no banco | O que traz |
|---|---|---|
| **OFX** | "baixar extrato", opção OFX, "arquivo para o gerenciador financeiro", "Money", "extrato para conciliação" | data, valor, descrição, documento e um **identificador único** de cada movimento (FITID) |
| **CSV** | "baixar extrato", opção CSV ou Excel | data, valor e descrição; sem identificador |

OFX é o melhor: o identificador é o que distingue dois pagamentos iguais no mesmo dia de
um mesmo pagamento lido duas vezes.

`apps/conciliacao/leitores.py` lê os dois sem nenhuma biblioteca de fora:

- O OFX dos bancos é **SGML velho**, com etiqueta que abre e não fecha (`<TRNAMT>-100.00`
  seguido de outra etiqueta). Nenhum analisador de XML lê isso. As bibliotecas de OFX
  existem para contornar esse detalhe, que aqui cabe em vinte linhas — e o pacote da loja
  é instalado **sem internet**, onde cada dependência a mais é uma roda a mais para dar
  errado.
- O CSV muda de banco para banco: o separador é quase sempre `;`, às vezes há duas ou
  três linhas de apresentação antes do cabeçalho, e o nome da coluna varia ("Data",
  "Data Lançamento", "Histórico", "Descrição", "Valor (R$)"). O leitor procura o
  cabeçalho e reconhece os nomes mais comuns, ignorando acento e caixa.
- O número vem em qualquer feitio: `1.234,56`, `1,234.56`, `-50,00`, `50,00-`,
  `(1.234,56)`, `R$ 50`. O que **não** é número vira *nada* e a linha é descartada, nunca
  zero: uma linha de extrato com valor errado é pior do que uma linha a menos, e a tela
  diz quantas foram descartadas.
- A codificação é tentada em UTF-8, cp1252 e latin-1, nessa ordem.

O mesmo arquivo trazido duas vezes é recusado: a impressão digital é do **conteúdo**
(sha256), então renomear o arquivo não engana. O limite é de 5 MB, que é mais do que um
mês de extrato.

## Como o par é procurado

Para cada **saída** do extrato, entre as contas a pagar **já baixadas** do SET:

1. **Mesmo valor**, exato. Valor igual é condição, não pontuação: R$ 1.362,00 e
   R$ 1.362,01 são contas diferentes, e aproximar valores num confronto de dinheiro
   seria inventar.
2. Data de pagamento a até **5 dias** da data do banco (`DIAS_DE_FOLGA`), porque o SET
   costuma ser baixado no dia seguinte e feriado empurra mais.
3. Entre as que sobram, ganha a mais perto na data; o **nome do fornecedor desempata**.
   A comparação ignora acento e as palavras que aparecem em toda descrição de banco e
   não identificam ninguém: PIX, TED, PAGAMENTO, LTDA, COMERCIO, BANCO.

Conta já marcada em outra linha continua aparecendo, com o aviso "já marcada em outra
linha": às vezes são dois pagamentos iguais mesmo, e esconder a candidata deixaria a
pessoa sem saída.

**Entradas de dinheiro ficam fora do confronto.** Crédito é venda, cartão e
transferência recebida; conta a pagar não tem nada a ver com isso. Elas aparecem na tela,
contadas à parte, para o extrato continuar batendo com o que o banco mandou.

## O sistema não marca nada sozinho

Mesmo quando há uma única candidata, quem confirma é a pessoa — com um clique em "É
esta", ou com o botão que confirma de uma vez todas as linhas que têm uma candidata só.
Conciliação marcada automaticamente é conciliação que ninguém olhou, e o erro aparece
meses depois, quando já não dá para lembrar.

Toda conferência guarda **quem conferiu e quando**, e vai para a trilha de auditoria.
Desfazer está sempre à mão: errar a conferência é normal, ficar preso nela não.

**Uma conta do SET paga uma saída do banco** (corrigido na 1.34.0). As candidatas de todas
as linhas são lidas de uma vez, antes do laço, e uma conta já usada só perdia pontos na
ordenação em vez de sair da lista: duas saídas iguais no extrato com uma conta só no SET
apareciam as duas como "uma conta bate", o botão das óbvias marcava as duas, o resumo
somava o mesmo dinheiro duas vezes e a tela declarava o extrato inteiro conferido —
enquanto uma retirada de verdade não tinha lançamento nenhum no SET. Agora a segunda linha
fica para a pessoa decidir, e a tela diz que a única conta com aquele valor já está marcada
em outra saída, que normalmente quer dizer que falta lançar esta no SET. Marcar à mão a
mesma conta numa segunda linha é recusado com essa explicação; desfazer a primeira libera a
conta.

Saída que não é conta do SET — tarifa, imposto, retirada dos sócios — sai da lista pelo
botão "Não é conta do SET", com uma anotação do que foi.

## Por que a ligação é pelo código do SET

`LinhaExtrato.lancamento_id_set` guarda o **código do lançamento no SET**, não uma chave
estrangeira para `financeiro.Lancamento`.

O motivo está em [sincronizacao-nao-soma.md](sincronizacao-nao-soma.md): a conta a pagar
vive dentro da foto de uma importação, e a cada sincronização as linhas são apagadas e
gravadas de novo, com chaves novas. Uma chave estrangeira se perderia na primeira
sincronização, levando junto a conferência que alguém fez à mão. O `id_set` é do SET e
não muda. Junto com ele fica um rótulo do que foi conferido, para a tela continuar
legível mesmo se aquela conta sumir do SET.

Isto está num teste: `test_a_conferencia_sobrevive_a_uma_sincronizacao_nova` apaga os
lançamentos e a importação inteira e confere que a linha continua conferida.

## Arquivos

- `apps/conciliacao/models.py` — `ExtratoImportado` e `LinhaExtrato`
- `apps/conciliacao/leitores.py` — OFX e CSV
- `apps/conciliacao/conferencia.py` — a busca do par e o resumo da tela
- `apps/conciliacao/servicos.py` — importar, conferir, desfazer, apagar
- `apps/conciliacao/views.py`, `templates/conciliacao/lista.html`, `templates/conciliacao/extrato.html`
- `apps/conciliacao/tests/test_leitores.py` — 14 testes dos formatos
- `apps/conciliacao/tests/test_conciliacao.py` — 28 testes do confronto e das telas
