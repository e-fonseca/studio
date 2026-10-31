# Contraste das letras na tela escura (1.43.0)

Conferido em 31/10/2026 com `docs/ferramentas/conferir-contraste.js`, sobre o banco de
desenvolvimento (a foto de 20/09/2026), entrando como Administrador gerência, que abre
todas as telas.

## Resultado final

| | |
|---|---|
| Telas abertas | 48 (`docs/ferramentas/telas-para-conferir.txt`) |
| Tamanhos | computador (1600px) e celular (390px): 96 aberturas |
| Textos medidos | 38.055 |
| Abaixo do mínimo | **0** |
| Ilhas claras (quadro grande de fundo claro) | **0** |
| Tela que rola de lado | **0** |
| Erro de JavaScript | **0** |
| Resposta diferente de 200 | **0** |

O mínimo é o do WCAG: 4,5:1 para letra comum e 3:1 para letra grande (24px, ou 18,66px em
negrito). As estrelas da reputação contam como desenho (3:1): o número de estrelas também
está escrito, escondido, para o leitor de tela.

**Os 16 textos que a ferramenta não mede** estão no cartão de destaque do Painel e do Painel
completo ("Comprou mais do que vendeu em 12 meses"), cujo fundo é um degradê de `#2b2018` a
`#1c1916`. Medidos à mão contra a ponta mais clara do degradê, que é o pior caso: letra
creme 12,6:1, valor em brasa 5,4:1, link azul 7,9:1.

**As telas de entrada** têm o degradê e a foto por trás, que a ferramenta não mede; foram
medidas pela cor de verdade do fundo no print, no ponto mais claro atrás de cada texto: o
"Sistema auxiliar ao SET" debaixo da marca, no clarão de brasa (`#492d1b`), fica em 6,7:1;
versão, servidor e o pé da tela, sobre o escuro (`#1f1a16`), em cerca de 7:1. Dentro do
cartão vale a conta das outras telas.

**De propósito, claro**: a etiqueta de código de barras na folha de etiquetas é branca com
risco preto, porque é o desenho que vai para o papel e o leitor precisa de preto no
branco.

## O que a primeira passada achou, e o que foi feito

| Onde | O que era | Contraste | O que ficou |
|---|---|---|---|
| Fornecedores, Visão geral (estrelas da reputação) | estrela vazia na cor da borda forte | 1,7:1 | cor da borda de campo, 3,3:1: "duas de cinco" voltou a mostrar as cinco |
| Financeiro (valor do filtro ativo) | valor em marrom escuro sobre a brasa | 3,3:1 | letra branca, 4,9:1 |
| Tela de entrada (botão Entrar) | degradê começando num laranja mais claro | 4,3:1 no alto | degradê da brasa ao tom abaixo, 4,9:1 a 6,3:1 |

Também na conferência, fora da conta de contraste:

- **Páginas de erro** (sem permissão, não encontrada, erro interno) ainda claras: têm o CSS
  dentro delas e não liam os tokens. Ficaram escuras.
- **Tela de entrada comprida** (a do código, no computador): a foto, presa à janela,
  terminava numa faixa reta no meio da página. Passou a cobrir a página inteira.
- **"Mandar outro código"** saía com a mesma cor do botão principal; virou botão de
  contorno, para não haver dúvida sobre qual apertar.
- **A frase "mandamos um código para..." aparecia duas vezes** na tela do código (no texto e
  no quadro verde). Ficou uma.

## Impressão

Impressas em PDF pelo próprio navegador, a Visão geral e a folha de etiquetas saem no papel
claro. Duas correções: a faixa do título da Visão geral imprimia letra creme em folha
branca (já era assim antes da 1.43.0) e a folha de etiquetas imprimia o aviso da data dos
dados em cima da primeira fileira, contra o que a própria tela promete ("só as etiquetas
saem no papel").

## Como refazer

Com o servidor de desenvolvimento no ar em `127.0.0.1:8099`:

    CABANA_SENHA='senha do usuário de teste' \
      node docs/ferramentas/conferir-contraste.js edson docs/ferramentas/telas-para-conferir.txt /tmp/prints

Sai zero quando está tudo dentro do mínimo, e grava `relatorio-contraste.json` com cada
texto abaixo do mínimo (onde está, a cor da letra, a do fundo e a conta). As telas de
entrada não precisam de login e não estão na lista: foram conferidas à parte, no caminho
inteiro (pedir o código, errar, senha fraca, criar a senha e entrar), com o e-mail
capturado por um servidor de e-mail de mentira.
