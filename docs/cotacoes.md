# Faixa do topo: relógio, dólar e ações (1.50.0)

Pedido do Edson em 06/11/2026: *"na area logada / na parte de cima do menu colocar a data e
hora em real time / na parte de cima do menu colocar um linha formato carrossel informando
valor do dólar comercial no momento em destaque e os principais ações em alta e queda de em
real time"*.

## O que aparece

Logo acima do menu, em todas as telas depois de entrar (`templates/core/_faixa_cotacoes.html`,
incluída no `base.html`):

- **Relógio**: dia, data e hora de São Paulo, andando a cada segundo (`static/js/cotacoes.js`).
- **Dólar comercial** em destaque: preço de VENDA, que é o do jornal, a variação do dia e a
  hora do preço.
- **Ações rolando**, em grupos: Em alta (maior primeiro), Em queda (a pior primeiro) e Sem
  mudança, com a hora dos preços. O rolo para com o mouse em cima e fica parado para quem
  pediu ao computador menos movimento (`prefers-reduced-motion`).
- **O vendedor fica só com o relógio**: a tela dele não mostra R$ nenhum (condição do Edson;
  `test_trocar_senha` cobra). Quem decide é a permissão `importacao.ver_painel`, a mesma do
  link da versão.

## De onde vem (apps/core/cotacoes.py)

| O quê | Fonte | Quanto custa | De quanto em quanto tempo |
|---|---|---|---|
| Dólar comercial | AwesomeAPI, `economia.awesomeapi.com.br/json/last/USD-BRL` (`ask`, `pctChange`, `timestamp`) | grátis, sem cadastro | no máximo 1 vez por minuto |
| Ações | brapi.dev, `brapi.dev/api/quote/<código>` (`regularMarketPrice`, `regularMarketChangePercent`, `regularMarketTime`) | grátis, sem cadastro só para PETR4, VALE3, ITUB4 e MGLU3 | no máximo a cada 15 minutos |

- **Atraso**: no plano grátis da brapi o preço das ações chega com uns 30 minutos de atraso;
  o preço ao vivo da B3 é pago. Por isso a faixa diz a hora de cada preço.
- **Mais ações**: a brapi pede a chave grátis (conta no site; 15 mil consultas por mês, uma
  ação por consulta). Dez ações a cada 15 minutos, no horário da bolsa, cabem nela.

## Nenhuma tela espera a internet

A mesma decisão do tempo (`apps/tempo/fonte.py`). A tela lê só o cache (`cotacoes:faixa`, sem
prazo, para o último valor sobreviver sem internet). Quando o guardado envelheceu, `faixa()`
solta uma busca em segundo plano (`threading`), uma de cada vez: `cache.add("cotacoes:buscando")`
é a trava entre os processos, e solta sozinha em 60 s se a busca morrer no meio. Resposta
estranha (limite de pedidos, erro, formato novo) nunca vira cotação: fica o valor anterior.
Busca que falhou conta como feita, para ninguém ficar batendo na porta sem internet.
Ninguém com o sistema aberto, ninguém busca. Nos testes, `COTACOES_NA_INTERNET = False`.

## A sessão parada continua acabando

A tela pede o miolo da faixa (`core:cotacoes`, JSON com o HTML de `_cotacoes.html`) a cada
minuto, e para quando a aba está escondida. Esse pedido **não conta como uso**
(`apps/contas/sessao.py`, `_pedido_de_fundo`): senão a tela esquecida no balcão nunca chegaria
aos 30 minutos parada. Quando a sessão acaba, ele recebe 401 e a tela vai sozinha para a
entrada, com o aviso de sempre.
