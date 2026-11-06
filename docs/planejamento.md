# Planejamento financeiro do Studio

Veio do protótipo que rodava no Claude do perfil da Henriett ("Financeiro Studio Industrial"),
trazido pelo Edson em 06/11/2026. As regras são as dele; as contas estão todas em
`apps/planejamento/regras.py`, e nada ali grava no banco.

## De onde vem cada número

| O quê | Regra |
|---|---|
| **Oficina, padrão** | 1ª parcela = custo × % da 1ª (50%), no cartão em N vezes; 2ª = o resto, em Pix na entrega real ou, sem ela, no prazo. Prazo que já passou conta como hoje. Sem prazo, vai para "sem data". |
| **Oficina, parcelas mensais** | custo ÷ N (3) no dia fixo da oficina. Repasse até o dia de corte entra no mesmo mês; depois dele, no seguinte. Rogério: dia 30, corte 25. Breno: dia 15, corte 10. Mês curto paga no último dia. |
| **Oficina, tudo no cartão** | custo inteiro no cartão em N vezes. |
| **Fatura do cartão** | a compra cai na primeira fatura cujo fechamento (vencimento − dias) é no dia da compra ou depois. |
| **Saldo do cliente** | Pix: o saldo informado, ou venda − recebido. Cartão ou quitado: nada a esperar (entrou antecipado). |
| **Margem de lucro** | (venda − oficina − frete − embalagem − RT − projeto − outros − taxa) ÷ venda. Taxa = o que entrou no cartão × taxa de antecipação; sem esse valor, venda × % no cartão (margem "estimada"). |
| **Juros do mês** | saldo usado × taxa ao mês de cada dívida, no dia dela. |
| **Venda mínima** | (fixos + empréstimos + juros) ÷ margem média dos pedidos (sem pedidos: a do markup alvo, menos a taxa). |
| **Caixa em 30 dias** | saldo em conta + entradas − saídas, dia a dia. |
| **Fechamento** | competência: pedidos com data de venda no mês. Caixa: o que sai e entra no mês pelas regras, mais o pró-labore pago pelo Studio. |
| **Entre empresas** | não é receita nem despesa; positivo = a Cabana deve ao Studio. Cancelado sai das contas. |

Toda parcela é arredondada ao centavo e a última leva a diferença, para a soma fechar o total.
Por isso o total de um mês pode diferir do protótipo em poucos centavos; o total geral é igual.

## Duas diferenças de propósito

1. Pedido **entregue sem data de entrega** cobra a 2ª parcela da oficina hoje. No protótipo ela
   sumia das contas.
2. O **Fluxo de caixa** (Dinheiro) é só do SET. O pedido tem o dinheiro calculado aqui, e somar
   os dois contaria duas vezes o que também está lançado no SET.

## Importar o arquivo do protótipo

```
python manage.py importar_prototipo C:\caminho\dados_sistema_financeiro_studio_2026-11-05.json --simular
python manage.py importar_prototipo C:\caminho\dados_sistema_financeiro_studio_2026-11-05.json
```

O pedido é achado pelo número do card; oficina, cartão, custo fixo, dívida e avulso, pelo
nome. Rodar de novo atualiza, não duplica, e não apaga o que não está no arquivo. O arquivo
tem dado de cliente: não vai para o repositório.

**A exportação de 05/11/2026 veio com os 7 movimentos entre empresas só com a data** (sem
valor, tipo e quem deve). Eles não entram; é preciso uma exportação nova ou lançar na tela.

## Conferido contra o protótipo

Com os 60 pedidos e o dia 05/11/2026, rodando o código do painel original ao lado:

| | Protótipo | Sistema |
|---|---|---|
| Caixa em 30 dias | −121.269,23 | −121.269,23 |
| Pior ponto | 05/12/2026 | 05/12/2026 |
| Entradas / saídas em 30 dias | 55.101,00 / 171.006,87 | 55.101,00 / 171.006,87 |
| Rogério em nov/26 | 42.211,78 | 42.211,78 |
| Breno em nov/26 | 14.938,33 | 14.938,33 |
| A receber: vencido / previsto / sem data | 10.994 / 109.936 / 146.709,30 | iguais |
| Alertas: margem baixa / incompletos | 7 / 35 | 7 / 35 |
| Venda mínima no mês | 91.103,93 | 91.103,92 |
