# A tela escura em todo o sistema (1.43.0)

Pedido do Edson em 31/10/2026, com o print do Dashboard da 1.41.0 e uma foto da fachada:

> *"gostei do visual escuro / na tela de login manter o layout com as cores da empresa, mas
> com umas pegadas degrade para o escuro seguindo a ideia do sistema. usar técnicas de front
> end e ux design. / usar como teste o a foto da frente da loja no plano de fundo da tela de
> login como marca d'agua bem franquinho em preto e branco, senão ficar bom na proxima
> atualizacao peço para remover. (...) / melhor visualização e cansa menos os olhos /
> adaptar e aplicar em todo o sistema (...) / adotar o esquema Grafana em todo o sistema."*

## O que "esquema Grafana" quer dizer aqui

O jeito do Dashboard da 1.41.0 levado às outras telas, sem trocar o desenho de nenhuma:

- **Fundo quase preto puxado para a madeira** (`#13110f`) e os quadros um tom acima
  (`#1c1916`), com borda fina em vez de sombra. É o que o Grafana faz para o número saltar
  e o resto ficar quieto.
- **Letra creme, não branca pura** (`#ece4da`). Branco puro sobre preto ofusca e cansa: o
  "cansa menos os olhos" do pedido.
- **As cores de situação do Grafana em toda tela**: verde `#73bf69` é bom, laranja `#ff9830`
  pede atenção, vermelho `#ff7383` pede ação, azul `#8ab8ff` é link e número sem juízo.
  Selo pintado com uma delas leva letra escura (`--cor-sobre-status`), porque essas cores
  são claras e letra branca nelas não se lê.
- **A marca fica nas peças de ação**: o botão principal e o assunto aceso no menu na brasa
  da loja (`#bf4e16`, letra branca 4,9:1), o fio de latão (`#c9a36a`) dos títulos.

O desenho de cada tela, o menu e as contas não mudaram. O Dashboard continua com os quadros
dele (`.corpo-monitor`); as outras telas ganharam as cores dele.

## Onde mora

**Só os tokens do `:root`, no alto de `static/css/sistema.css`, carregam cor.** O resto do
arquivo usa as variáveis. Para mexer numa cor, muda-se o token, e ela muda em todas as
telas de uma vez. Cor escrita direto numa regra (`#fff`, `white`, `#f6f3ee`) é o que deixa
uma ilha clara numa tela escura: foi o que a 1.43.0 caçou em botões, campos, selos,
tarefas, cartões de fornecedor e nas páginas de erro (`templates/403.html`, `404.html` e
`500.html`, que têm o CSS dentro delas porque precisam abrir mesmo sem o arquivo de
estilo).

- **`color-scheme: dark`** faz o navegador desenhar escuros a barra de rolagem, o
  calendário do campo de data, a lista aberta do campo de escolha e a caixa de marcar.
- **Impressão volta ao claro**: o bloco `@media print` logo abaixo do `:root` devolve os
  tokens de antes da 1.43.0. Papel não tem fundo escuro, e letra creme em folha branca não
  se lê. Folha do pedido, etiquetas e folha de contagem saem como sempre saíram.
- **PDF e e-mail não mudaram.** Os PDFs são desenhados à mão (`apps/core/pdf.py`), sem CSS;
  os e-mails levam o estilo dentro de cada etiqueta, e caixa de e-mail clara é o normal.
- **A cor do aplicativo instalado** (barra do celular, tela de abertura) acompanha:
  `COR_DA_MARCA` e `COR_DO_FUNDO` em `apps/core/aplicativo.py`, e o `theme-color` do
  `base.html`.

## A tela de entrada

As quatro telas de quem ainda não entrou (entrar, esqueci a senha, o código do e-mail e o
acesso bloqueado) estendem `templates/contas/_entrada.html` e usam a seção "tela de
entrada" do CSS.

- **O fundo desce da madeira e da brasa da loja para o escuro do sistema**: um clarão de
  brasa no alto, onde fica a marca, e um degradê do marrom (`#4d250c`) ao fundo do sistema.
- **A fachada em marca d'água**: `static/img/fachada-marca-dagua.jpg`, já em preto e branco
  e levemente desfocada no próprio arquivo (604×754, 64 KB), com opacidade de 8%. Cobre a
  página inteira e rola com ela: presa à janela, a tela do código, mais comprida, cortava
  a foto numa faixa reta.
- **O cartão** é um quadro escuro meio transparente, com desfoque do que está atrás e o fio
  da brasa ao latão no alto. Sobe meio centímetro ao abrir; quem pediu ao sistema
  operacional menos movimento não vê nada se mexer (`prefers-reduced-motion`).
- **Mostrar a senha e aviso de Caps Lock** (`static/js/entrada.js`): as duas causas comuns
  de "a senha não entra" que a pessoa não enxerga. O botão só aparece com o JavaScript
  ligado, e a senha volta às bolinhas antes de enviar.

### Para tirar a foto

Ele pediu como teste e disse que, se não ficar bom, pede para remover. É uma linha:

1. Apagar, em `static/css/sistema.css`, a linha `--entrada-foto: url("../img/fachada-marca-dagua.jpg");`
   dentro de `.entrada`.
2. Apagar o arquivo `static/img/fachada-marca-dagua.jpg`.

O resto da tela não depende da foto. Para deixá-la mais forte ou mais fraca, muda-se o
`opacity: .08` de `.entrada::before` (0,05 quase some; 0,12 já se lê a placa).

## Como o contraste foi conferido

Contraste é a conta do WCAG entre a cor da letra e a do fundo onde ela está. O mínimo é
4,5:1 para letra comum e 3:1 para letra grande (24px, ou 18,66px em negrito).

Na 1.43.0 um programa abriu as telas do sistema no computador (1600px) e no celular
(390px), como Administrador gerência, e mediu **cada texto visível**: a cor da letra contra
o fundo de verdade, somando as camadas meio transparentes de baixo para cima até achar uma
opaca. Além disso, procurou **ilhas claras** (qualquer quadro grande com fundo claro, sobra
do tema de antes). O resultado está em `docs/evidencias/contraste-1.43.0.md`.

Para refazer depois de mexer em cor: subir o sistema local, entrar, e rodar o mesmo
procedimento (o roteiro está no fim daquele arquivo).

## Regras para tela nova

- Cor só por variável (`var(--cor-...)`). Nunca `#fff`, `white` ou cor clara escrita na
  regra.
- Letra sobre selo verde, laranja ou vermelho: `var(--cor-sobre-status)`.
- Fundo de botão da marca: `var(--cor-acao)`; letra e risco da marca sobre o escuro:
  `var(--cor-brasa)` ou `var(--cor-primaria)` (o `--cor-acao` como letra no escuro fica
  em 3,6:1, abaixo dos 4,5 da letra comum).
- Gráfico em SVG desenhado à mão: cor pela classe (`fill: var(--cor-fatia-N)`), nunca no
  atributo `fill="#..."`, senão a impressão sai com a cor da tela.
- Antes de entregar, print no computador e no celular, como sempre.
