# Porta segura e leitura pela câmera do celular

## O problema

A contagem de inventário pelo celular depende da câmera. Todo navegador atual só
libera a câmera em **contexto seguro**: página servida por `https://`, ou aberta em
`localhost`. Num endereço de rede como `http://192.168.3.254:8095/sistema/` o
navegador nem chega a pedir permissão: ele simplesmente não oferece a câmera.

Então, sem HTTPS, a tela da câmera não funciona — por mais certo que esteja o código
dela. Não existe opção de configuração do sistema que contorne isso; é regra do
navegador.

## O que foi feito (1.15.0)

O sistema passou a responder em duas portas:

| Porta | Endereço | Para quê |
|---|---|---|
| 8095 | `http://192.168.3.254:8095/sistema/` | o de sempre, computador do balcão |
| 8443 | `https://192.168.3.254:8443/sistema/` | celular e tablet, com câmera |

O Waitress, que é o servidor do sistema, não fala TLS, e trocá-lo por outro mexeria no
que já funciona. Então o HTTPS entra por um túnel (`apps/core/tunel_tls.py`): ele
escuta na 8443, faz o TLS com o navegador e repassa os bytes para o Waitress na 8095,
dentro do próprio servidor. Ele não lê, não reescreve e não guarda nada do que passa.

Se o túnel não subir (porta ocupada, certificado ilegível), o sistema continua
respondendo em HTTP e grava o motivo em `logs\sistema.log`. A loja não para por causa
do HTTPS.

### A página que chegava cortada (corrigido na 1.43.0)

Até a 1.42.0 o túnel usava duas linhas por conexão, uma para cada sentido, e as duas
mexiam ao mesmo tempo no mesmo objeto TLS do OpenSSL: uma parada lendo o pedido seguinte
do navegador enquanto a outra escrevia a resposta. O OpenSSL não aguenta isso, e de vez em
quando a leitura voltava "acabou" no meio da resposta; a linha dela fechava a conexão e a
página (ou o CSS, ou uma imagem) chegava sem o fim. Quem entra por HTTP, no balcão, nunca
passou por aqui.

Apareceu como um teste que falhou uma vez com a máquina ocupada. Medido com 400 páginas
seguidas pelo túnel: **2 cortadas com a máquina parada e 9 a 11 com ela ocupada**. Agora é
uma linha só por conexão (`_encaminhar`, com `select`), que lê e escreve um lado de cada
vez: **nenhuma cortada em 1.200**, e conexão mantida com 45 MB descendo e 15 MB subindo
inteiros. O teste `test_o_tls_do_cliente_nunca_e_usado_por_duas_linhas_ao_mesmo_tempo`
trava a causa, que acontecia em toda página, e não só o sintoma, que é raro.

## O certificado

A loja não tem domínio nem certificado pago, e o endereço é um IP interno. O
certificado é feito pelo próprio servidor (`apps/core/certificado.py`), na primeira vez
que o sistema sobe, e guardado em `C:\studio-sistema\config\certificado`. Vale três
anos e é refeito sozinho quando falta menos de um mês para vencer.

Ele cobre o IP do servidor, o nome da máquina, `localhost` e `127.0.0.1`. Como não foi
emitido por uma autoridade conhecida, o navegador avisa na primeira visita de cada
aparelho: **Avançado → Continuar**. Depois disso não volta a avisar, desde que o
certificado não seja refeito — por isso ele não é regerado a cada inicialização.

## O que precisa estar configurado

No `studio.env` (o instalador cuida disso, inclusive numa atualização):

```
STUDIO_HTTPS=1
STUDIO_PORTA_HTTPS=8443
STUDIO_CERTIFICADO_PASTA=C:\studio-sistema\config\certificado
STUDIO_CERTIFICADO_NOMES=192.168.3.254,<nome-da-maquina>,localhost,127.0.0.1
STUDIO_CSRF_TRUSTED_ORIGINS=...,https://192.168.3.254:8443
```

A origem `https://...:8443` precisa estar nas origens confiáveis, senão o Django recusa
todo formulário enviado pelo celular. O firewall libera a 8443 só para a rede da loja,
na mesma regra de grupo da 8095.

`STUDIO_HTTPS=0` desliga a porta segura; o sistema segue em HTTP e a tela da câmera
passa a mostrar o recado explicando por que ela não liga.

## Quando o celular ainda assim não lê

A tela avisa, em vez de só não funcionar:

- **endereço sem https** — mostra o endereço seguro e o passo a passo do aviso;
- **leitor não carregou** — desde a 1.16.0 o leitor vem dentro do sistema (ZXing em
  `static/js/leitor/`), então iPhone e Android leem igual; sobra o caso raro de o arquivo
  não ter carregado;
- **câmera não autorizada** — a pessoa negou a permissão.

Nos três casos a digitação do código à mão continua na mesma tela e dá no mesmo
resultado. O leitor de mão no computador da loja também segue valendo.


## Atalho na tela inicial (1.16.0)

O mesmo https que liberou a câmera é o que permite o atalho: um aplicativo instalado a
partir do navegador (PWA) só se instala em contexto seguro.

Como instalar, uma vez por aparelho:

- **Android (Chrome)** — abrir `https://192.168.3.254:8443/sistema/`, passar pelo aviso do
  certificado, menu de três pontos, "Instalar aplicativo" ou "Adicionar à tela inicial".
- **iPhone/iPad (Safari)** — abrir o mesmo endereço, botão de compartilhar, "Adicionar à
  Tela de Início". No iPhone só o Safari instala; o Chrome do iPhone não.

O que isso é, por dentro (`apps/core/aplicativo.py`):

- `/sistema/manifesto.webmanifest` — nome, ícones, cores e `display: standalone`, que é o
  que tira a barra de endereço. Serve sem login porque o navegador o busca sem o cookie da
  sessão.
- `/sistema/operario.js` — o service worker. Responde em `/sistema/` e não em
  `/sistema/static/` porque o navegador só deixa o operário cuidar da pasta dele e do que
  está abaixo dela.

Duas decisões que não se mexem sem pensar:

- **Só o visual é guardado no aparelho** (CSS, o leitor de código, ícones). Nenhuma tela
  com número da loja entra no depósito: saldo velho na tela seria pior do que tela nenhuma.
- **O nome do depósito leva o número da versão** (`cabana-1.16.0`). Atualizar o sistema
  muda o nome, o depósito antigo é apagado na ativação e ninguém fica preso no visual da
  versão passada. O próprio `operario.js` sai com `no-store`, senão a atualização não
  chegaria nunca.

Desinstalar é apagar o ícone, como qualquer aplicativo. Nada disso passa pela Play Store
nem pela App Store, e não há um segundo programa para manter.


## Por que a etiqueta não era lida, e o que mudou (1.38.0)

Em 21/10/2026 ele testou o inventário num **Samsung S24 FE**: *"a câmera foi habilitada e
nao leu nenhuma etiqueta de código de barras, precisa ajustar melhor para fazer a leitura
rápida para fazer sentido o modulo"*. Ou seja: o HTTPS estava certo, a permissão estava
dada, a imagem aparecia na tela — e nenhum código entrava.

### O que estava errado, medido e não suposto

A causa principal não era o leitor, era o **tamanho da imagem pedida à câmera**. O código
pedia `width: { ideal: 1280 }`. Um celular novo entrega 1280 sem reclamar, e a conta não
fecha: a etiqueta da loja tem 95 barras e espaços em pouco mais de 2 cm. Em 1280 pixels de
largura, com a etiqueta ocupando um quarto da tela, cada barra fica com menos de um pixel e
meio — depois da compressão do vídeo, barra fina e espaço fino viram a mesma mancha cinza.
Não existe leitor que acerte isso; o nosso devolvia vazio quadro após quadro, calado.

A prova está em `docs/ferramentas/`, duas ferramentas novas que servem para conferir isso
de novo quando mexerem no leitor:

- `montar-etiqueta-falsa.py` desenha a etiqueta EAN-13 **de um produto real da loja**
  (`0000000047463`, VASO GARRAFA M JUNCO) com o mesmo código que imprime as barras do
  sistema, em três cenas: `perto` (as barras ocupam 900 dos 1920 pixels do quadro),
  `medio` (480) e `longe` (260);
- `conferir-leitura-de-barras.js` abre a tela de verdade num navegador com câmera de
  mentira alimentada por essas cenas, e mede quantos segundos o sistema leva para ler.

O resultado, antes e depois:

| Cena | Antes (1.37.0) | Depois (1.38.0) |
|---|---|---|
| perto (900 px de barras) | lido em 0,0 s | lido em 0,1 s |
| medio (480 px de barras) | **não leu em 15 s** | lido em 0,1 s |
| longe (260 px de barras) | não leu em 15 s | não leu em 15 s |

E a prova de que a causa era a resolução: mudando **só** `1280` para `1920` no código
antigo, sem mais nada, a cena `medio` passou a ser lida em 0,0 s.

A cena `longe` continua não sendo lida, e isso não é defeito — é o limite físico. Abaixo de
mais ou menos um sexto da largura do quadro não há pixel suficiente para as barras finas.
Por isso a tela agora **manda encostar**, em vez de deixar a pessoa descobrir sozinha.

### O que mudou na tela

- **Pede 1920×1080 à câmera** e aceita o que o aparelho der (`ideal`, não `exact`, senão
  aparelho antigo não abriria a câmera nenhuma).
- **Usa o leitor do próprio aparelho quando ele existe** (`BarcodeDetector`, no Chrome do
  Android — e é o caso do S24 FE), que lê em código nativo; o nosso leitor (ZXing) fica
  como segundo, para o iPhone e para quem não tem. A tela escreve qual dos dois está
  valendo, em uma linha, para o diagnóstico não depender de adivinhação.
- **A faixa branca da tela é exatamente o pedaço analisado.** Antes a faixa desenhada e o
  recorte analisado eram dois retângulos diferentes, e o recorte era reduzido antes de ser
  lido. Agora o recorte sai no tamanho real, sem encolher, e a conta compensa o
  `object-fit: cover` — o vídeo é cortado pela tela, e ignorar isso analisa o lugar errado.
  A faixa também cresceu (de 32% para 48% da altura), porque etiqueta de vaso não fica reta.
- **Foco contínuo** pedido à câmera depois que o vídeo começa (`focusMode: continuous`), que
  é o que resolve o borrão de quem aproxima o celular.
- **Lanterna e Aproximar**, dois botões que só aparecem quando o aparelho os oferece
  (`getCapabilities()`). O Aproximar vai a 2x, não ao máximo: o máximo de alguns celulares é
  digital e piora a imagem.
- **O texto de ajuda mudou de recado**: "Encoste a câmera quase na etiqueta, até as barras
  preencherem a faixa branca de ponta a ponta."

Digitar o código à mão continua na mesma tela, e o leitor de mão do balcão segue valendo.

### Conferir de novo

Da pasta do projeto, com o sistema de desenvolvimento no ar:

```
python3 docs/ferramentas/montar-etiqueta-falsa.py /tmp/camfalsa
node docs/ferramentas/conferir-leitura-de-barras.js medio /tmp/camfalsa
```

Sai `0` quando leu e `1` quando não leu, então serve em script. Os testes de `apps/inventario`
guardam o resto: que a câmera é pedida em 1920, que o leitor do aparelho vem antes do nosso,
e que a faixa do CSS e a faixa do JavaScript continuam sendo a mesma faixa — essa última é a
que quebra calado quando alguém mexe só num dos dois arquivos.
