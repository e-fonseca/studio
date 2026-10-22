# Pedidos ao fornecedor: o pedido guardado, os anexos e a conferência

Até a 1.30.0 o pedido ao fornecedor era só um PDF timbrado: saía da Lista de compra,
ia impresso ou por WhatsApp e acabava ali. Desde a **1.31.0** o pedido fica **guardado**,
aceita os documentos que o fornecedor manda de volta (pedido assinado, romaneio, nota
fiscal) e **confere item a item** o que chegou contra o que foi pedido.

Tela: **Compras > Pedidos** (`/sistema/pedidos/`).

## Por que o pedido precisou virar registro

A lista de compra é refeita a cada sincronização, três vezes ao dia. Ela responde
"o que comprar HOJE", e isso muda sozinho quando a venda entra. Para conferir uma nota
que chegou uma semana depois, é preciso saber o que foi pedido **naquele dia** — a
quantidade, o custo de referência, o código de barras de cada item. Então o pedido ganhou
tabela própria (`apps/pedidos/`), com as linhas congeladas no momento em que o PDF saiu.

Como tudo o que não vem do SET, o pedido **não** tem campo `importacao` e não aponta para
a foto da sincronização: cada linha guarda o `codigo` do produto, nunca uma chave
estrangeira para algo que a próxima importação vai refazer.

## Como nasce um pedido

Na Lista de compra, o botão "Gerar o pedido" virou **formulário POST**: ao clicar, o
sistema grava o pedido (um por fornecedor, numerado) e **anexa ao pedido a própria folha
em PDF** que foi para o fornecedor. O PDF abre em outra aba como antes; o aviso na tela
traz o link do pedido guardado.

Reabrir o mesmo PDF pelo link (GET) **não** cria outro pedido: só reimprime. E gerar o
mesmo pedido duas vezes no mesmo dia, com as mesmas linhas e quantidades, reaproveita o
pedido que já existe em vez de duplicar — a comparação é por valor (`Decimal`), não por
texto, porque a coluna do banco tem três decimais e `"10"` e `"10.000"` são o mesmo
número.

Entram no pedido só as linhas com quantidade maior que zero, como no PDF. Quem registra
precisa da permissão `pedidos.registrar_pedido` (Administrador gerência); o Operador
administrativo vê os pedidos e anexa documentos, mas não cria.

O timbre da folha sai do cadastro (tela Dados da empresa), e desde a 1.35.0 ele carrega
os **dois endereços**: o fiscal, que é o da nota, e o físico, impresso como
`Entregar em: …` quando é diferente. A loja fica no Largo dos Jesuítas e a nota é
emitida no endereço da R Claudionor Assis Dias — sem essa linha a mercadoria sai para o
endereço errado e ninguém descobre antes do romaneio.

## Gerar os pedidos pela tela de Pedidos (1.37.0)

Pedido dele em 20/10/2026: *"na tela pedidos, gerar automaticamente pedidos de compra
mercadorias por fornecedor, com a quantidade sugerida pelo formula informada
anteriormente aqui"*.

Até a 1.36.0 o caminho era um só: abrir a Lista de compra, filtrar um fornecedor e
clicar lá. Quem chegava pela tela de Pedidos via o que já tinha sido pedido e não tinha
como fazer o do dia. Agora a tela abre com o quadro **"Gerar os pedidos de hoje"**: um
fornecedor por linha, com itens, unidades, valor e prazo, um botão por fornecedor e um
botão para os que cabem no teto do mês.

- **Nenhum pedido nasce sozinho.** "Automaticamente" aqui quer dizer que o sistema monta
  tudo — fornecedor, linhas, quantidade e a folha — e não que ele pede. O prompt dele é
  explícito: *"Não aprovar nem emitir pedidos automaticamente"*. O clique é de uma pessoa.
- **O teto do mês é informação, não trava.** O botão que gera de uma vez pega só os que
  cabem no que sobrou do teto (*"Não ultrapassar o orçamento sem autorização"*). Quem
  passa do teto continua podendo ser pedido, um a um, porque quem decide é quem compra.
- **Na tela entram os que cabem no mês** e os que já foram pedidos hoje. A loja tem mais
  de cem fornecedores com o que comprar, e uma tabela com todos esconderia justamente os
  cinco que importam hoje. Uma linha diz quantos ficaram de fora e manda para a lista de
  compra.
- **A gravação é a mesma das duas telas** (`apps/pedidos/geracao.py`): registra o pedido,
  monta a folha **daquele** fornecedor e anexa. Pedido guardado com a folha de outro
  fornecedor é erro que só aparece quando a carga chega.
- Gerar de novo no mesmo dia, com as mesmas linhas, **reaproveita** o pedido que já
  existe — a mesma regra de sempre. A tela mostra o número em vez do botão.
- Fornecedor que saiu da lista entre abrir a tela e clicar volta com recado, não com um
  pedido vazio.

## Gerar de novo o pedido de compra (1.36.0)

Na tela do pedido, o botão **"Gerar o pedido de compra em PDF"** monta a folha outra vez,
a partir do que está **guardado** — não da lista de compra de hoje, que já é outra. Sai
com o timbre da loja e o endereço da entrega, pronto para mandar ao fornecedor, e dá para
gerar quantas vezes quiser: gerar não grava nada nem cria pedido novo.

É a MESMA folha da lista de compra (`apps/compras/pedido.py`), e isso é de propósito: o
papel que o fornecedor lê não pode depender de por qual tela foi impresso. Aquele módulo
nunca soube o que é um `Pedido` — ele conta com um "bloco" que tem `.nome`, `.itens`,
`.prazo_dias`, `.prazo_assumido` e `.ajustados`. `apps/pedidos/folha.py` veste o pedido
guardado com essa roupa, e é todo o custo de reaproveitar a folha em vez de escrever uma
segunda versão dela.

Dois detalhes:

- O prazo de um pedido guardado **nunca sai como "(estimado)"**. Esse aviso significa "o
  sistema não sabia o prazo deste fornecedor", e aqui ele sabe: está gravado no pedido.
- A folha de um pedido **cancelado** sai avisando, em cima da observação: `PEDIDO
  CANCELADO. Motivo: ...`. Ela existe para o arquivo e para avisar o fornecedor; sair
  igual à do pedido válido faria a loja imprimir um cancelamento e o fornecedor entender
  um pedido.

## Editar o pedido (1.36.0)

Pedido dele em 20/10/2026: *"permitir editar pedido"*. O fornecedor liga dizendo que só
tem seis das dez, ou a loja muda de ideia antes de mandar o papel. Até aqui a saída era
cancelar e fazer outro pedido — e aí o número que a loja já tinha falado ao telefone
deixava de existir.

**Só pedido em aberto se edita.** Depois de recebido, mexer na quantidade apagaria
justamente a prova contra a qual a nota fiscal é conferida; cancelado já é o fim da linha.

O que dá para mudar: a quantidade de cada linha, o prazo combinado e a observação que sai
na folha. **Escrever 0 tira o item do pedido** — é a mesma regra da folha, onde pedir zero
unidade nunca foi pedido. O que **não** dá para mudar é o custo: ele é o da última compra
registrada no dia do pedido, é referência de conferência, e é contra ele que a diferença
de preço da nota aparece.

Ao salvar:

- o valor de cada linha é recalculado pelo custo guardado;
- a linha mexida fica marcada como **escolhida pela loja**, que é o que sai em marrom na
  folha — quem confere precisa ver qual número é decisão de gente e qual é conta do sistema;
- a **folha nova é gerada e anexada ao pedido**. A anterior continua lá, com data: quem já
  recebeu a primeira precisa poder ver o que ela dizia;
- a tela passa a avisar, no topo, que o pedido foi alterado, quando e por quem;
- a trilha de auditoria guarda `pedido.editado` com o de-para de cada linha.

Um pedido **não pode ficar sem nenhum item**. Esvaziar não é editar, é desistir — e
desistir tem caminho próprio, com motivo.

## Cancelar o pedido, com motivo (1.36.0)

Pedido dele no mesmo dia: *"descartar/cancelar (informar motivo)"*. A situação
`cancelado` existia desde a 1.31.0 e nunca teve tela nem motivo: dava para um pedido
estar cancelado no banco sem ninguém saber por quê.

O cancelamento fica atrás de um `<details>` fechado, no fim da tela, e **o motivo é
obrigatório**: pedido cancelado sem motivo é a pergunta "por que este não chegou?" sem
resposta, três meses depois.

**Nada é apagado.** O pedido e as linhas ficam guardados, marcados como cancelados, com o
motivo, quem cancelou e quando — é a regra dele de não eliminar histórico, e é o que
permite ver depois o que se deixou de comprar daquele fornecedor. O número do pedido não
é reaproveitado.

Depois de cancelado, o pedido não se edita, não se marca como recebido e não se cancela de
novo (senão o segundo motivo apagaria o primeiro). E a lista de compra **não** reaproveita
um pedido cancelado: a regra que evita pedido repetido no mesmo dia só olha pedidos em
aberto, então cancelar e gerar de novo cria um pedido novo, como tem de ser.

Quem pode editar e cancelar é quem pode registrar pedido (`pedidos.registrar_pedido`):
Administrador gerência. O Operador administrativo vê o pedido e gera a folha, que é
leitura, e não mexe no que foi pedido. O vendedor não chega a nenhuma dessas telas.

## Os anexos

Cada pedido aceita quantos documentos vierem, classificados em **pedido**, **romaneio**,
**nota fiscal** ou **outro**. Aceita `.xml`, `.pdf`, `.png`, `.jpg`, `.csv` e `.txt`.

Cuidados que valem a pena conhecer:

- A **assinatura** do arquivo é conferida, não a extensão: um `.pdf` que não começa com
  `%PDF-` é recusado. Extensão mentida é o jeito mais velho de fazer um sistema abrir o
  que não devia.
- O arquivo é gravado com **nome calculado** (hash), nunca com o nome que veio de fora,
  e fica em `dados\anexos`, fora da pasta do programa. O nome original fica num campo,
  só para a tela mostrar.
- O mesmo arquivo não entra duas vezes: o `sha256` é único por pedido.
- Para baixar, a resposta vai com `Content-Security-Policy: default-src 'none'` e
  `X-Content-Type-Options: nosniff`, e cada download fica na auditoria. Documento de
  fornecedor é arquivo de fora: ele é servido como anexo, nunca como página do sistema.
- `XML` com `<!DOCTYPE` é recusado antes de qualquer leitura — é por ali que entra a
  "bomba de bilhões de risadas", um punhado de entidades que se multiplicam e comem a
  memória do servidor. Nota fiscal de verdade nunca traz DOCTYPE.

## O que o sistema consegue ler de cada arquivo

Isso é do documento, não do sistema:

| Arquivo | O que sai |
| --- | --- |
| **XML da NF-e** | Tudo: emitente, CNPJ, número, data, total e **cada item** (código, descrição, código de barras, quantidade, unitário, total). Confere linha por linha. |
| **CSV / TXT** (romaneio) | Item a item, pelos nomes das colunas (código, descrição, quantidade, unitário, total, barras), em qualquer ordem e com acento ou sem. |
| **PDF (DANFE)** | Fica guardado e à vista, com a explicação de que o PDF é o *retrato* da nota: o conteúdo não está em campo nenhum, são posições de texto na página. O que se tira dali é adivinhação, e adivinhação em tela que confere dinheiro é pior que nada. |
| **Foto / imagem** | Fica guardada. Ler número de foto de papel exigiria mandar a imagem para fora, e nada aqui sai do servidor da loja. |

Por isso vale pedir ao fornecedor **o XML** da nota, não só o PDF. É o mesmo arquivo que
a contabilidade já recebe.

## A conferência

Com um XML ou um CSV anexado, a tela do pedido mostra a conferência item a item.

O casamento entre a linha da nota e a linha do pedido é o ponto delicado: **o código do
produto na nota é o do FORNECEDOR**, não o da loja. Então a ponte, em ordem:

1. **Código de barras** — é o mesmo nos dois lados do balcão. É por isso que a linha da
   lista de compra passou a levar o código de barras junto.
2. **Código do produto** — serve quando o fornecedor usa o mesmo código da loja.
3. **Descrição** — nome reduzido ao que distingue (sem acento, sem pontuação, sem
   "unidade", "cx", "pct"). A linha sai marcada **"pela descrição (confira)"**, porque é
   palpite fundamentado, não certeza. Descrição repetida dentro do pedido fica fora do
   casamento por nome: entre dois candidatos iguais, errar em silêncio é pior que não
   casar.

Cada linha termina numa frase, da pior para a melhor: *veio sem ter sido pedido*,
*pedido e não veio*, *veio mais do que o pedido*, *veio menos do que o pedido*,
*quantidade certa, preço acima da referência* e *confere*. O preço só reclama passando de
**2%** acima do custo de referência, que é o custo que o SET tinha no dia do pedido.

No fim, o valor: o total da nota contra o total do pedido, com um centavo de tolerância
para arredondamento.

Conferido, o pedido é marcado como **recebido** (quem marcou e quando ficam gravados), e
sai da lista de pendentes.

## Onde isso aparece

- **Compras > Pedidos**: os pedidos em aberto primeiro, com fornecedor, data, valor,
  quantas linhas e quantos documentos chegaram.
- **Pedido** (`/sistema/pedidos/<número>/`): as linhas pedidas, os anexos, a conferência
  e o botão de marcar recebido.
- O vendedor não vê nada disso: Pedidos exige `pedidos.view_pedido`, que o perfil
  Operador vendedor não tem.
