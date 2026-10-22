---
name: cabana-reporting-system
description: Como mexer em relatório, tela de número e importação do sistema da Cabana do Jacarandá sem quebrar as regras da loja. Use ao criar ou alterar relatório, painel, exportação, alerta por e-mail ou Telegram, ou ao mexer na leitura do backup do SET.
---

# Relatórios do sistema da Cabana

Sistema auxiliar da Cabana do Jacarandá: Django 5.2 + PostgreSQL, servido em
`/sistema` no servidor da loja (Windows, 192.168.3.254). O sistema **lê** uma cópia do
backup do SET Sistemas e não escreve nada nele. Tudo em português do Brasil, inclusive
nomes de função, variável e teste.

## As cinco regras que não se negociam

1. **Nada afeta o SET.** A leitura é sempre de uma CÓPIA do backup do dia, num Firebird
   4 x64 separado, em `C:\cabana-sistema`. Nunca abrir o `DADOS-SET.FDB` em uso, nunca
   falar com o serviço Firebird do SET, nunca escrever em `C:\Set Sistemas`.
2. **Sincronizar não soma.** Cada importação é uma FOTO: todo modelo vindo do SET tem
   `importacao` e toda consulta filtra por ela. Consulta sem esse filtro é o defeito mais
   caro possível aqui, porque dobra número na cara do comprador.
3. **O vendedor vê UMA tela.** `Operador vendedor` só abre
   `/sistema/importacao/consulta/`, sem custo, sem margem, sem valor. Tela nova nasce com
   `permission_required`, e tela de dinheiro nunca ganha permissão de vendedor.
   Quem confere isto é `apps/contas/tests/test_rotas_por_perfil.py`, que lê as rotas do
   próprio Django e roda com os outros testes: tela nova entra sozinha na conferência.
   **Dinheiro não é só o número na tabela**: em 11/10/2026 o furo estava na tela de
   versões, que mostrava o histórico de mudanças — e o histórico cita o faturamento e o
   lucro que cada versão consertou. Texto que explica um número é o número.
4. **LGPD.** Nome, CPF e comprador do cliente não são importados. Há teste que falha se
   alguém acrescentar campo de cliente em venda.
5. **O número do relatório é o número da tela.** Relatório chama a mesma função que a
   tela chama. Regra copiada é regra que diverge, e já divergiu.

## O que fazer antes de escrever código

1. Ler `docs/` do próprio repositório: `arquitetura.md`, `modelo-de-dados.md`,
   `sincronizacao-nao-soma.md`, `mapeamento-set.md` e o doc do assunto.
2. Procurar o padrão que já existe na tela antes de inventar desenho novo
   (`references/padrao-interface.md`).
3. Conferir `references/regras-negocio.md`: teto de compra, custo do dia, item sem custo,
   grupos que não são mercadoria.

## O caminho de um número, do SET à tela

```
cópia do backup (Firebird)
  → apps/importacao/fontes/firebird.py      lê e devolve dicionários
  → apps/importacao/servicos.py             grava a foto (bulk_create por lote)
  → apps/<app>/<calculo>.py                 a conta, em função pura sobre a foto
  → apps/<app>/views.py                     permissão + contexto
  → templates/<app>/<tela>.html             a tela
  → apps/alertas/relatorios.py              o mesmo cálculo, por e-mail e Telegram
```

Detalhe de cada etapa em `references/banco-dados.md` e `references/relatorios.md`.

## Receita: tela de número nova

1. Cálculo em módulo próprio, com `@dataclass` de resultado e propriedades para o que a
   tela mostra. Nada de conta dentro de template.
2. `calcular(importacao, ...)` devolve resultado vazio quando `importacao is None`: antes
   da primeira importação a tela abre e explica, não quebra.
3. Total do dia/período sai de `aggregate` sobre a consulta inteira, nunca da soma das
   linhas mostradas: cortar a lista não pode mudar o total.
4. Apelido de anotação não pode ter o nome do campo (`Sum("quantidade")` como
   `quantidade=` faz a soma seguinte apontar para a própria soma). Prefixar com `soma_`.
5. View com `@login_required` e `@permission_required(..., raise_exception=True)`.
   Vale para a tela E para a exportação dela: CSV sem permissão é a tela inteira aberta.
6. Entrada no menu em `apps/core/menu.py` (é a única lista) e, se houver exportação,
   `irmas=(...)` para o menu acender.
7. Teste: a conta, o caso sem dado, a permissão do vendedor (403) e o CSV.
8. Print no computador (1600 px) E no celular (390 px) antes de entregar, medindo
   `document.documentElement.scrollWidth > window.innerWidth`.

## Receita: relatório novo por e-mail e Telegram

1. Função em `apps/alertas/relatorios.py` que CHAMA o cálculo da tela e devolve
   `Relatorio` com `manchete`, `resumo`, `blocos`, `tem_noticia` e `caminho`.
2. Registrar em `MONTADORES` e em `Rotina` (`DIARIAS` ou `SEMANAIS`).
3. `tem_noticia=False` quando nada mudaria o que a pessoa faz hoje: sem notícia não manda.
4. Bloco de tabela tem DUAS colunas (o que é, quanto custa); quatro não cabem em 390 px.
5. O e-mail leva a tabela; o Telegram leva manchete e três linhas por bloco.
6. Teste que o número do relatório é igual ao da função da tela.

## Armadilhas que já custaram uma versão

- `{# ... #}` em várias linhas quebra teste de template: usar `{% comment %}`.
- `--noreload` no runserver serve TEMPLATE e CÓDIGO velhos: reiniciar antes de print.
- Texto que vaza do elemento (e-mail, código longo) não muda a largura dele: só
  `scrollWidth > clientWidth` acha.
- `manage.py shell` escreve no banco de verdade mesmo com settings de teste.
- Migração já aplicada no servidor nunca ganha campo novo: campo novo, migração nova.
- Permissão nova só entra no perfil porque o instalador roda `configurar_perfis` depois
  de migrar; no banco local, rodar à mão.
- Fechar uma tela com `permission_required` não basta: quem não pode abri-la não pode ter
  o link na mão. Conferir `apps/core/menu.py` (o `Item` leva a permissão) e os links soltos
  nos templates, senão a pessoa clica e leva um 403 — foi o que quase aconteceu com o
  número da versão no alto da tela, que é link para o histórico.
- Conferência feita à mão envelhece no dia seguinte. Quando descobrir uma regra que vale
  para o sistema inteiro, o lugar dela é um teste que LÊ a lista (rotas, modelos, telas) em
  vez de repeti-la; lista digitada à mão é a que fica para trás.

## Scripts de conferência (não gravam nada)

```
python3 .claude/skills/cabana-reporting-system/scripts/validar-importacao.py
python3 .claude/skills/cabana-reporting-system/scripts/validar-relatorios.py
python3 .claude/skills/cabana-reporting-system/scripts/checar-consistencia.py
```

Pedem as variáveis `CABANA_*` do ambiente (ver `.env.exemplo`) e são só de leitura.

## Referências

- `references/regras-negocio.md` — as contas da loja e o que cada número significa.
- `references/banco-dados.md` — a foto por importação, os modelos e o que o SET mente.
- `references/relatorios.md` — relatórios, rotinas, canais e agendamento.
- `references/permissoes.md` — os três perfis e o que cada um abre.
- `references/padrao-interface.md` — o desenho que o dono da loja já lê sem reclamar.
- `examples/` — um relatório de venda, um de estoque e uma tela de números, inteiros.
