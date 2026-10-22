# Exemplo: a relação de vendas do dia (1.24.0)

Pedido do Edson em 11/10/2026: "uma relação de todos os produtos vendidos do dia, preço de
custo e valor de venda com porcentual de lucro e valor". Serve de modelo para qualquer
relatório que precise de um dado que a importação ainda não traz.

## 1. O dado não existia: trazer da origem

O produto importado guarda a soma de 12 meses, não o dia. Quem responde é `IVENDAS`:

```python
# apps/importacao/fontes/firebird.py
def _ler_itens_de_venda(linhas, inicio, produtos):
    por_venda = {}
    for id_venda, codigo, quantidade, valor, custo in linhas("""
        select v.idvenda, i.nprod, i.qtde, i.valortotal, i.precocusto
        from ivendas i
        join vendas v on v.nvenda = i.nvenda and v.empresa = i.empresa
        where v.empresa = ? and v.status <> 'Estornado' and v.datavenda > ?
    """, (EMPRESA, inicio)):
        custo_unitario = _decimal(custo)
        if not custo_unitario or custo_unitario <= 0:
            custo_unitario = None          # vazio é vazio, não zero
        ...
```

Decisões que valem para qualquer leitura nova: só o que a tela vai usar (cinco colunas),
`status <> 'Estornado'`, e nada de cliente.

## 2. Gravar como foto

```python
# apps/importacao/servicos.py
def _gravar_vendas(importacao, vendas):
    cabecalhos = [VendaImportada(importacao=importacao, **sem_linhas(dados)) for dados in vendas]
    VendaImportada.objects.bulk_create(cabecalhos, batch_size=1000)
    itens = [ItemVendaImportada(venda=venda, **linha)
             for venda, dados in zip(cabecalhos, vendas)
             for linha in dados.get("linhas", ())]
    ItemVendaImportada.objects.bulk_create(itens, batch_size=1000)
```

Casado pela ORDEM, não pelo id do SET. E o `detalhe` da importação ganhou duas contagens,
`itens_de_venda_importados` e `itens_de_venda_sem_custo`, com rótulo em português em
`ROTULOS_DETALHE` — é assim que a tela de importações explica o que entrou.

## 3. A conta, numa função pura

```python
# apps/painel/vendas_do_dia.py
com_custo = Q(custo_total__isnull=False)
agrupado = (
    do_dia.values("codigo", "descricao", "grupo")
    .annotate(
        soma_quantidade=Sum("quantidade"),
        soma_valor=Sum("valor_total"),
        soma_custo=Sum("custo_total", filter=com_custo),
        soma_valor_com_custo=Sum("valor_total", filter=com_custo),
        soma_quantidade_com_custo=Sum("quantidade", filter=com_custo),
        quantas_vendas=Count("venda", distinct=True),
    )
    .order_by("-soma_valor")
)
```

Três coisas para copiar:

- **`filter=` em vez de `Case/When`**, e apelido com prefixo `soma_`: apelido igual ao
  nome do campo faz a soma seguinte apontar para a própria soma.
- **lucro e margem só sobre `valor_com_custo`**, nunca sobre o faturamento inteiro.
- **os totais do dia saem de `aggregate` sobre a consulta inteira**, não da soma das
  linhas mostradas, senão cortar a lista mudaria o faturamento.

## 4. O relatório chama a tela

```python
# apps/alertas/relatorios.py
def vendas_do_dia(importacao=None, dia=None):
    dados = vendas_da_tela.calcular(importacao, dia=dia)   # a MESMA função da tela
    relatorio.manchete = (f"Em {quando} a loja vendeu {_reais(dados.faturamento)} e sobrou "
                          f"{_reais(dados.lucro)} depois do custo do produto ({margem}).")
```

Bloco com os números do dia, bloco com os campeões, e um bloco a mais só quando há
produto vendido abaixo do custo — que é a única coisa ali que pede ação hoje.

## 5. O que os testes travam

`apps/painel/tests/test_vendas_do_dia.py`, em ordem de importância:

1. item sem custo não vira lucro cheio (margem de 40%, não de 70%);
2. cortar a lista não muda o total do dia;
3. a segunda importação não dobra o dia;
4. o vendedor leva 403 na tela e no arquivo.
