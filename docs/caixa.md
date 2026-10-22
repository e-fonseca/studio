# Caixa

Tela pedida pelo Edson em 08/10/2026: "menu caixa = caixas aberto e fechados, valores,
hora abertura, hora fechamento, dia, operador".

O sistema **só lê**. Abrir, movimentar e fechar caixa continua sendo no SET; aqui ele
aparece somado, conferido e filtrável, que é o que o SET não dá numa tela só.

## De onde vem

Duas tabelas do backup do SET, lidas na importação (`apps/importacao/fontes/firebird.py`,
função `_ler_caixas`):

- **CAIXA** — o turno: `IDCAIXA`, `USUARIO` (quem abriu), `DATAABERTURA`,
  `DATAFECHAMENTO`, `SALDOINICIAL`, `SALDOFINAL`, `STATUS`, `TIPO`, `OBSERVACAO`,
  `USUARIOFECHAMENTO`. São 969 linhas no backup de 20/09/2026, 950 da Cabana
  (`EMPRESA = 1`).
- **ICAIXA** — cada movimento do turno: 49.597 linhas, das quais 3.971 são da Cabana e
  **não** são venda.

O campo `TIPO` de ICAIXA é a chave da leitura:

| TIPO | O que é | O que o sistema faz |
|---|---|---|
| `I` | saldo inicial | ignora: já vem em `CAIXA.SALDOINICIAL`, somar duplicaria |
| `R` | recebimento de venda | soma em `recebido` e em `por_forma` |
| `E` | entrada de dinheiro | soma em `entradas` e grava a linha |
| `S` | sangria (retirada) | soma em `sangrias` e grava a linha |
| `P` | pagamento feito pelo caixa | soma em `pagamentos` e grava a linha |

Movimento marcado como **Estornado** sai da conta e vai para o campo `estornado`, só
para a tela poder dizer que ele existiu.

Os 43.945 recebimentos de venda entram **somados**, e não linha a linha: a venda em si
o sistema já guarda em `VendaImportada`, e repetir cinquenta mil linhas tornaria a
importação e a tela pesadas sem acrescentar nada. Linha a linha ficam só os 3.971
movimentos que não são venda — que são exatamente os que alguém abre para conferir.

A leitura inteira leva 1,8 s.

## A conta do turno

```
saldo calculado = saldo inicial + recebido + entradas - sangrias - pagamentos
```

É a mesma conta que o fechamento do caixa faz no SET. Conferido no turno 970:
379,40 + 8.067,50 − 266,25 = **8.180,65**, igual ao `SALDOFINAL` gravado.

Diferença de até **um centavo** é arredondamento e conta como "fecha". Nos 950 turnos
da loja, 7 não fecham:

| Caixa | Dia | Quem | Gravado | Pela conta | Diferença |
|---|---|---|---|---|---|
| 54 | 15/04/2024 | ADMIN | 0,00 | −20.933,62 | 20.933,62 |
| 555 | 22/08/2025 | BARBARA | −1.158,54 | −1.993,34 | 834,80 |
| 818 | 22/04/2026 | ANA BEATRIZ | −4.377,98 | −4.868,33 | 490,35 |
| 320 | 05/01/2025 | LETHICIA | 15.429,05 | 15.573,05 | −144,00 |
| 317 | 03/01/2025 | BARBARA | 3.978,40 | 4.024,40 | −46,00 |
| 89 | 20/05/2024 | ADMIN | 954,60 | 924,20 | 30,40 |
| 79 | 10/05/2024 | ADMIN | 1.242,90 | 1.238,10 | 4,80 |

Saldo final negativo não é erro de leitura: é o próprio SET gravando assim, e nos três
maiores casos o turno tem data de abertura e fechamento separadas por meses.

## Dinheiro na gaveta

Pedido do Edson em 13/10/2026: "contabilizar caixa em dinheiro, inicio, o que saiu,
sangrias e saldo". A conta do turno acima responde "quanto este turno movimentou". Esta
responde outra coisa: **quanto papel deveria estar na gaveta**. PIX e cartão entram no
caixa mas não entram na gaveta.

```
dinheiro na gaveta = saldo inicial
                   + recebido EM DINHEIRO
                   + entradas
                   - sangrias
                   - pagamentos pelo caixa
```

Entrada, sangria e pagamento não têm forma de pagamento gravada no SET (conferido: o
campo vem vazio nos três tipos), e está certo — sangria é papel saindo da gaveta,
entrada é papel entrando, pagamento pelo caixa sai da gaveta. Forma de pagamento só
existe no recebimento de venda.

### Qual forma é dinheiro

No SET da Cabana o dinheiro é **AVISTA**, ao lado de PIX, CARTAO DEBITO e CARTAO
CREDITO. A lista é do SET e muda sem avisar, então `apps/caixa/dinheiro.py` não adivinha:
cada forma cai em uma de três caixas — é dinheiro, não é dinheiro, ou **não sei**. Forma
desconhecida **nunca** entra na conta calada; ela aparece na tela, somada à parte, para
alguém avisar a gerência. Chutar que uma forma nova é dinheiro faria a gaveta "faltar"
sem explicação, que é o pior que esta tela poderia fazer com quem confere caixa.

Conferência no backup de 20/09/2026, nos 950 turnos:

| | Valor |
|---|---|
| Recebido em dinheiro (AVISTA) | R$ 366.592,63 |
| Recebido por PIX e cartão | R$ 3.725.525,78 |
| Não classificado | R$ 0,00 |
| **Soma** | **R$ 4.092.118,41** |

A soma bate exatamente com o `recebido` que a tela já mostrava. Só **9,0%** do que a
loja recebe é papel.

### Por que o período não tem saldo

Num período a tela mostra o que entrou, o que saiu e a gaveta do **último turno** — não
um saldo somado. Somar o saldo de abertura de todos os turnos contaria o mesmo dinheiro
muitas vezes, porque a abertura de um turno é, em tese, o que ficou do anterior.

Encadear também não serve nesta loja: em **642 dos 949** turnos fechados a abertura
**não** é o fecho em dinheiro do turno anterior. A abertura é digitada no SET a cada
turno, e a gaveta é esvaziada por sangria quase todo dia.

Por isso "entrou menos o que saiu" pode dar negativo — dá −R$ 5.815,01 nos dois anos e
meio — e a tela explica o sinal em vez de mostrar um número negativo calado: a loja
retira por sangria dinheiro que já estava na gaveta antes do período começar.

## Caixa esquecido aberto

Turno que ficou aberto de um dia para o outro (`DIAS_PARA_ESQUECIDO`, contado sobre a
data da abertura no fuso da loja) aparece num cartão de atenção
no alto da tela, **fora** do filtro de período: enquanto ele não é fechado no SET, a
venda do dia seguinte entra no turno errado e nenhum fechamento confere.

Na Cabana há um só turno aberto, o 971, de 21/09/2026 — normal, é o do dia seguinte ao
backup. Os dois turnos abertos desde novembro de 2025 e abril de 2026 que aparecem no
banco do SET são das empresas 2 e 3, não da Cabana, e por isso o sistema não os lê.

## A janela de datas

O período termina no **último dia com caixa**, não na data de corte da importação. A
data de corte é o último dia com venda, e o turno aberto agora pode ter sido aberto
depois dela (é o caso do 971, aberto em 21/09 com corte em 20/09). Terminando a janela
no corte, justamente o caixa aberto ficaria de fora do período padrão.

## Acesso

Permissão `caixa.ver_caixa`, dada à gerência e ao operador administrativo. O operador
vendedor **não** vê: continua com uma tela só, sem valor nenhum.

## Arquivos

- `apps/caixa/models.py` — `CaixaImportado` e `MovimentoCaixa`
- `apps/caixa/servicos.py` — filtros, somas e as barras do turno
- `apps/caixa/views.py`, `templates/caixa/lista.html`, `templates/caixa/turno.html`
- `apps/importacao/fontes/firebird.py` — `_ler_caixas`
- `apps/importacao/servicos.py` — `_gravar_caixas`
- `apps/caixa/dinheiro.py` — o dinheiro vivo: classificação das formas, `do_turno` e `do_periodo`
- `apps/caixa/tests/test_caixa.py` — 24 testes
- `apps/caixa/tests/test_dinheiro.py` — 16 testes do dinheiro na gaveta
