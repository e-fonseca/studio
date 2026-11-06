# Manual: descontos e metas

**Para que serve**: ver, venda a venda, o desconto que a equipe deu contra as regras da loja,
e a meta de cada sábado, domingo e feriado. Mostra também o desconto que o SET não mostra: o
preço do produto mudado no caixa antes de fechar a venda. Desde a versão 1.46.0.

**Onde fica**: no menu de cima, **Contas a pagar > Descontos e metas**. As regras ficam no botão
**Regras e metas**, no alto da tela.

**Quem pode usar**: quem tem a permissão **Controlar descontos e metas**. Na instalação, só o
perfil Administrador gerência. Para dar a outro perfil: **Sistema > Usuários**, botão **Perfis e
permissões**.

**O sistema não muda nada no SET** e não trava venda nenhuma. Ele lê a cópia do backup, como
o resto, e mostra a conta.

## Antes de começar

Olhe o aviso de cima: **"Dados de dd/mm/aaaa"**. A tela é tão nova quanto a última
importação. Na primeira vez depois da atualização aparece **"A próxima importação completa
esta tela"**: até ela rodar, a conta usa só o desconto do fechamento. Para não esperar,
**Sistema > Importações > Importar agora**.

## Passo a passo

1. **Escolha o período e, se quiser, a pessoa.** 7 dias, 30 dias, este mês ou o mês passado.
   "Quem recebeu no caixa" mostra só as vendas de uma pessoa. Clique em **Filtrar**.
2. **Leia os quatro cartões.**
   - **Fora da regra, sem aprovação**: quantas vendas passaram do que a regra deixa e quanto
     de desconto foi além.
   - **Vendas com desconto**: quantas tiveram algum desconto, quanto no total e quanto disso
     foi preço mudado no caixa.
   - **Metas batidas**: dos sábados, domingos e feriados do período, e o prêmio por pessoa
     somando os dias.
   - **Meta que dependeu de venda fora da regra**: dias em que, sem essas vendas, a meta não
     teria sido batida ou o prêmio seria menor. É o número que responde à pergunta "a equipe
     deu desconto só para bater a meta?".
3. **Abra as vendas fora da regra.** Vêm da que mais passou para a que menos passou. Cada
   cartão diz o dia, a hora, quem recebeu no caixa, a forma de pagamento, o desconto e **por
   que** saiu da regra. Em **Os produtos desta venda** aparece cada produto com o preço de
   tabela, o cobrado e o desconto.
4. **Se o grupo aprovou, anote.** Em **Foi aprovada no grupo? Anotar**, escolha quem aprovou,
   escreva uma observação se quiser e clique em **Anotar a aprovação**. A venda sai da lista e
   vai para **Aprovadas pelo grupo**, no fim da tela. Anotou errado? **Desfazer** devolve a
   venda para a lista; o registro de quem anotou e de quem desfez fica guardado.
5. **Confira as metas.** A tabela **Metas do período** mostra cada sábado, domingo e feriado
   com a meta, o vendido, o prêmio por pessoa e as vendas fora da regra do dia. Quando a meta
   dependeu delas, a linha diz como o dia ficaria sem elas.
6. **Veja quem e o quê.** **Por quem recebeu no caixa** soma por pessoa; **Produtos que mais
   saíram com desconto** mostra onde o desconto se repete.

## Mudar as regras

**Regras e metas** tem três partes: o desconto sem aprovação (Pix e dinheiro, débito,
crédito, parcelas, folga e quem autoriza), as metas e o prêmio, e os feriados. Escreva os
valores como se escreve no papel: `12.000`, `12.000,00` ou `7,5`. Clique em **Salvar as
regras**. Se algum campo estiver errado, nada é salvo e o campo aparece marcado.

- **Débito** começa sem desconto, porque a regra da loja não fala dele. Se a loja aceitar o
  desconto do à vista no débito, é escrever a porcentagem aqui.
- **Folga** é para o arredondamento: com R$ 1,00, quem fecha R$ 107,50 em R$ 100,00 no Pix
  (6,98%) não aparece como fora da regra.
- **Parcelas** entram no texto da regra, mas o sistema não as confere: o SET não grava em
  quantas vezes o cartão foi passado.
- **Feriados**: o sistema já sabe os nacionais, o de São Paulo e os de Embu das Artes (a
  lista do ano está em "Os feriados que o sistema já conhece"). Carnaval não é feriado em
  Embu. Para acrescentar um dia, escreva uma data por linha: `20/01 São Sebastião` vale todo
  ano; `16/02/2027 Carnaval` vale só aquele dia.

Toda mudança fica na auditoria, com o antes e o depois. A tela de descontos passa a conferir
todas as vendas com a regra nova, inclusive as que já estavam na tela.

## O que o número quer dizer

- **"Preço mudado no caixa"**: o produto saiu por menos do que o preço de tabela, e a venda
  no SET aparece **sem desconto**. É o desconto que não se vê no SET.
- **"Comparado ao cadastro"**: desde julho de 2026 o SET não grava o preço de tabela na
  venda, e a comparação é com o preço do cadastro. Se o preço do produto mudou entre a venda
  e a importação, a diferença pode ser o aumento, e não desconto.
- **"Recebeu"**: é quem registrou o recebimento no caixa do SET, que nem sempre é quem
  negociou com o cliente. O SET deixou de gravar o vendedor em abril de 2026.
- **Prêmio por pessoa**: o SET não sabe quem trabalhou no dia (freela não tem usuário). Os
  nomes da linha da meta são de quem abriu caixa ou passou venda.

## Todo dia, no e-mail

O e-mail **Vendas do dia** traz a meta do dia (no sábado, no domingo e no feriado) e as
vendas fora da regra, com o link desta tela. Dia sem nada fora da regra não ganha o bloco.

## No grupo das metas, no Telegram

Desde a versão 1.47.0, quando o sábado, o domingo ou um feriado bate a meta, o robô do
Telegram avisa no grupo das metas: o dia, quanto vendeu, a meta e o prêmio por pessoa. As
metas são as desta tela: sábado e feriado **R$ 12.000**, domingo **R$ 15.000**.

**Ligar, uma vez só** (em **Sistema > Alertas**, parte **Grupo das metas**):

1. Se o robô ainda não existe, crie no **@BotFather** e grave o token em **Aviso no
   Telegram**, como a tela explica.
2. No Telegram, abra o grupo METAS, toque no nome do grupo, **Adicionar membro**, e procure o
   robô pelo nome de usuário dele (o que termina em *bot*). O link de convite não serve para
   robô.
3. Na tela, clique em **Descobrir o grupo** e, na linha do grupo, em **Usar para as metas**.
4. Clique em **Enviar teste ao grupo das metas**. O teste já explica as metas e o prêmio a
   quem lê o grupo.
5. Marque **avisar no grupo das metas quando a meta bater** e clique em **Salvar o grupo das
   metas**.

**Quando chega**: depois da importação que traz as vendas do dia. Se o SET faz o backup só à
noite, o aviso do sábado chega no domingo de manhã. A mensagem diz até que hora há venda na
conta. Se o prêmio subir de degrau numa importação seguinte, vem outro aviso; o mesmo número
não se repete.

**Quando a meta dependeu de desconto fora da regra**, o aviso diz numa linha quantas vendas
foram, quanto e como o dia ficaria sem elas. Não diz o nome de ninguém: isso fica nesta tela.
Anotar a aprovação aqui tira a linha dos avisos seguintes.
