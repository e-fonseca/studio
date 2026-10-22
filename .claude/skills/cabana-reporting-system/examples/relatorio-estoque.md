# Exemplo: o relatório semanal de estoque

Mostra como um relatório se monta **sem conta nenhuma própria**, só juntando o que já
está em duas telas.

```python
# apps/alertas/relatorios.py
def estoque(importacao=None):
    importacao = importacao or importacao_servicos.ultima_concluida()
    relatorio = Relatorio(rotina="estoque", assunto="Estoque da loja",
                          aviso=_aviso_dos_dados(), caminho="/sistema/painel/")
    if importacao is None:
        relatorio.manchete = "Ainda não há dados importados do SET."
        relatorio.resumo = "Sem importação concluída."
        return relatorio

    visao = visao_geral.montar(importacao)          # a tela Visão geral
    todas = sugestoes.montar(importacao)            # a tela Sugestões
```

## O que copiar daqui

**1. Antes da primeira importação, explica.** Toda função de relatório começa checando
`importacao is None` e devolve manchete sem notícia. E-mail que inventa número é pior do
que e-mail que não chega.

**2. Dado velho vai escrito no topo.** `_aviso_dos_dados()` devolve frase quando a última
importação está vencida; sem isso o número do e-mail parece de hoje.

**3. O recorte é explícito.** `_recorte(linhas)` corta em `LINHAS_NO_EMAIL = 12` e devolve
quantas ficaram de fora, e o bloco diz "e mais N no sistema". E-mail que precisa de
rolagem no celular não é lido.

**4. Só os blocos que são do assunto.** O estoque leva `parar`, `destravar` e `empurrar`;
`repor` fica de fora porque é assunto do relatório de compra, que sai no mesmo dia. Dois
e-mails dizendo a mesma coisa viram um e-mail não lido.

**5. A manchete carrega o contraste**, não o total:

```python
relatorio.manchete = (f"{_reais(prateleira.valor)} parados na prateleira, "
                      f"dos quais {_reais(parado.total)} em produtos que não venderam no ano.")
```

"R$ 742 mil na prateleira" não move ninguém. "R$ 227 mil deles não venderam uma unidade
no ano" move.

**6. `tem_noticia` é sobre hoje:**

```python
relatorio.tem_noticia = any(not b.vazio for b in todas.blocos if b.chave in blocos_de_estoque)
```
