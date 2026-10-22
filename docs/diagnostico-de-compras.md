# Diagnóstico de compras: provar com números

**Objetivo:** mostrar, com dados do próprio SET, quanto dinheiro está parado em estoque
que não vende, quanto do que foi comprado ainda sobra e quais itens que vendem estão em falta.
Cada número tem o motivo e a conta ao lado, para qualquer pessoa conferir.

## O que o diagnóstico responde

| Pergunta | Como é calculado |
|---|---|
| Quanto dinheiro está parado sem venda? | Estoque × custo dos itens sem nenhuma venda no período |
| Quanto está em excesso? | Unidades acima de 180 dias de venda (ajustável) × custo |
| Quanto da compra do período ainda sobra? | Do que foi comprado no período, a parte que continua acima do necessário × custo |
| O que falta e vende? | Itens com venda no período e estoque zerado |
| O que comprar agora e quanto custa? | Fórmulas do briefing (seção 9): ponto de reposição, estoque alvo, lote e múltiplo |

As fórmulas estão em `apps/compras/calculos.py` e cobertas por testes. Os padrões (7 dias de
segurança, revisão semanal, excesso acima de 180 dias) são ponto de partida para a gestão aprovar.

## Relatórios do SET necessários

Exportar em Excel ou CSV, do jeito normal do SET, sem mexer em nada nele:

1. **Estoque atual por produto**, com código, descrição, quantidade e custo. Anotar a data e a hora da exportação.
2. **Vendas por produto** (quantidade) nos últimos 90 dias, e se possível 12 meses para ver sazonalidade.
3. **Compras ou entradas de nota por produto** (quantidade e valor) no mesmo período.
4. Se existirem: **devoluções por produto**, **pedidos de compra em aberto** e **lista de fornecedores com prazo de entrega**.

Com as amostras, monto o mapeamento direto dos relatórios. Até lá, dá para usar a
[planilha modelo](modelos/planilha-diagnostico-modelo.xlsx), juntando as colunas dos relatórios.

## Como rodar

```bash
python manage.py diagnostico_compras planilha.xlsx --dias 90 --data-corte 2026-10-04 --saida relatorio.csv
```

`--dias` é o número de dias em que a loja abriu no período das vendas. Linhas com problema
são listadas e recusadas; o relatório só sai parcial com `--aceitar-com-erros`, e o resumo avisa.

## Exemplo com dados FICTÍCIOS (só para mostrar o formato)

Entrada: [exemplo-ficticio.csv](modelos/exemplo-ficticio.csv). Saída: [exemplo-ficticio-relatorio.csv](modelos/exemplo-ficticio-relatorio.csv).

```
Diagnóstico de compras. Dados até 04/10/2026, vendas de 90 dias.
Itens analisados: 8 (0 sem custo informado, fora dos valores)
Valor em estoque: R$ 8.738,00
Parado sem venda no período: R$ 3.000,00
Acima de 180 dias de cobertura: R$ 2.650,00
Comprado no período e ainda sobrando: R$ 2.354,00
Itens em falta que vendem: 1
Itens para comprar agora: 2 (custo estimado R$ 1.093,50)
```

Exemplo de linha: “Vaso de barro pequeno (fictício): vende 1 a cada 8 dias; o estoque cobre
1050 dias, 116 unidades acima do necessário.” Foram compradas 100 no período.

## Limites (ditos com franqueza)

- Relatórios semanais são fotografias: não mostram o estoque de cada dia. Se o item ficou zerado,
  a venda do período subestima a procura; o relatório avisa e reduz a confiança.
- Sem custo, o item entra nas contagens mas não nos valores em reais.
- O diagnóstico mostra excesso e falta; **não** calcula lucro nem fluxo de caixa, que dependem de dados financeiros.
- Peças únicas e artesanais sem reposição regular precisam de regra própria, a definir com a gestão.
