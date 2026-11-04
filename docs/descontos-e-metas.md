# Descontos e metas (1.46.0)

Pedido dele (02/11/2026), junto com as regras de pagamento e as metas que a gerência passa à
equipe: *"no financeiro do caixa, tentar buscar os descontos de cada produto seguindo as
regras. ideia é controlar os desconto para que os funcionarios dê desconto sem parâmetros só
objetivando a premiação. A empresa nao pode se prejudicar financeiro."*

O passo a passo de quem usa a tela está em `manual/descontos-e-metas.md`. Aqui fica como a
conta é feita e de onde cada número sai.

## Onde fica e quem vê

- **Dinheiro > Descontos e metas** (`/sistema/caixa/descontos/`), logo depois do Caixa. O
  botão **Regras e metas** abre a tela das regras (`/sistema/caixa/descontos/regras/`).
- Permissão nova: **Controlar descontos e metas** (`caixa.controlar_descontos`), no grupo
  Dinheiro do catálogo. Entra sozinha no perfil Administrador gerência quando o instalador roda
  `configurar_perfis`; nenhum outro perfil a recebe. Quem quiser dar a outro perfil marca em
  Usuários > Perfis e permissões.
- A mesma permissão vê as vendas, anota a aprovação do grupo e muda as regras: são as três
  coisas que a gerência faz com este assunto, e separar daria três caixinhas para a mesma
  pessoa.

## As regras

Ficam numa linha só (`RegraDeDesconto`, sempre a de número 1) e mudam pela tela. A migração
nasce com o que ele mandou:

| Regra | Começa com | Observação |
|---|---|---|
| Desconto no Pix e no dinheiro | 7% | "À vista, no Pix ou dinheiro: 7% de desconto" |
| Desconto no cartão de crédito | 0% | "Cartão de crédito: em até 3x, sem desconto" |
| Parcelas no crédito | 3 | Vai no texto da regra, mas **não é conferido**: o SET não grava em quantas vezes o cartão foi passado |
| Desconto no cartão de débito | 0% | As regras dele não falam do débito. Com zero, débito com desconto precisa de aprovação. Se a loja aceitar, é mudar aqui |
| Folga | R$ 1,00 | Para o arredondamento: R$ 107,50 fechado em R$ 100,00 no Pix é 6,98% e não é passar da regra |
| Quem autoriza | os três nomes da mensagem dele | Separados por vírgula ou "ou"; viram as opções do campo "Quem aprovou" |
| Meta do sábado e do feriado | R$ 12.000 | |
| Meta do domingo | R$ 15.000 | Era R$ 18.000 até 04/11/2026, quando ele baixou (1.47.0). Feriado que cai no domingo fica com a do domingo |
| Prêmio na meta | R$ 30 por pessoa | |
| A mais | R$ 10 por pessoa a cada R$ 1.000 acima da meta | Vendeu R$ 13.500 no sábado: R$ 30 + R$ 10 = R$ 40 cada |
| Outros feriados | vazio | Um por linha: `20/01` vale todo ano, `16/02/2027` só aquele dia |

Mudar uma regra fica na auditoria (`caixa.regras_de_desconto_mudadas`), só com os campos que
mudaram, o antes e o depois. A tela passa a conferir **todas** as vendas, inclusive as que já
estavam lá, com a regra nova.

## Onde o desconto está no SET

Em dois lugares, e só um deles aparece como desconto:

1. **No fechamento** (`VENDAS.TOTALDESC`): o caixa tira um valor da venda inteira. É o
   desconto que o SET mostra: 1.344 das 16.361 vendas de 12 meses na cópia de 20/09/2026.
2. **No preço do produto**: o caixa troca o preço do item antes de fechar
   (`IVENDAS.VALORPROD` abaixo do preço de tabela). A venda sai com desconto zero e o produto
   mais barato. Em agosto de 2026, **71 das 134 vendas fora da regra** tinham desconto só
   assim: no SET elas aparecem sem desconto nenhum.

O desconto da venda é a soma dos dois, e a porcentagem é sobre o que a venda daria pelo
preço de tabela (`VENDAS.TOTALPROD` mais o corte nos itens). O desconto do fechamento é
dividido entre os produtos na proporção do valor de cada um, e é assim que cada produto tem
o seu na lista "Produtos que mais saíram com desconto".

O corte no preço não conta:

- no produto vendido a peso ("KG" ou "KL" na descrição): o caixa digita o preço do pedaço,
  que não se compara com o preço do quilo;
- no DIVERSOS, que no SET tem preço de R$ 1,00 de mentira;
- no produto sem preço de tabela.

## O preço de tabela

O SET grava no item o preço de tabela do dia da venda (`IVENDAS.PRECOVENDA`) e **parou de
gravar em julho de 2026**: faltava em 3.563 dos 4.068 itens de julho, 3.093 dos 3.368 de
agosto e 1.099 dos 1.104 de setembro. Antes de julho faltava em menos de 10 itens por mês.
O preço cobrado (`VALORPROD`) continua em todos.

Sem o do dia, vale o do cadastro (`PRODUTOS.PRECOVENDA`) na importação, marcado no item
(`preco_tabela_do_cadastro`) e na tela ("comparado ao cadastro"). O risco é o preço do
produto subir depois da venda e o aumento parecer desconto. Para isso, a importação **passa
adiante o primeiro preço visto**: o item que já estava na importação anterior com o preço do
cadastro fica com aquele preço, e não com o de hoje. Com a importação três vezes ao dia, o
preço que vale é o do dia da venda, ou muito perto dele. Medido na cópia: nos itens de junho
(quando o SET ainda gravava o preço do dia), o cadastro de 20/09 dava 235 cortes de preço
onde, pelo preço gravado, houve 73.

## O que a regra deixa, venda a venda

Depende de como o cliente pagou, parte por parte (`FATVENDAS`, já sem o troco: a soma das
partes dá o total em 16.309 das 16.336 vendas de 12 meses).

- **Pix e dinheiro**: a porcentagem do à vista sobre a parte paga assim.
- **Débito e crédito**: a do débito e a do crédito (zero, no começo).
- **Qualquer outra forma** (a prazo, por exemplo): é "condição diferente", que pela regra
  precisa de aprovação **mesmo sem desconto**.

A venda paga metade no Pix e metade no cartão pode ter desconto só na metade do Pix. Ela sai
da regra quando o desconto passa do que a regra deixava por mais do que a folga. Cada cartão
diz por quê, em português: *"Passou R$ 30,00 da regra: no cartão de crédito ela é sem
desconto."* e, quando houve preço mudado, *"R$ 30,00 foi preço mudado no caixa (1 produto),
comparado ao preço do cadastro."* Venda que saiu por menos do que custou ganha uma linha a mais.

117 vendas em 12 meses foram pagas em mais de uma parte, 88 delas em formas diferentes.

## Quem

O `VENDAS.VENDEDOR` está vazio em 11.481 das 16.361 vendas de 12 meses; de abril a setembro
de 2026, veio em 2 das 8.028. Quem aparece é quem registrou o recebimento no caixa (`ICAIXA.USUARIO` da
linha de tipo `R`), que existe em 16.334 delas. É quem fecha a venda e dá o desconto do
fechamento, mas **nem sempre quem negociou com o cliente**, e a tela diz isso. Venda sem
recebimento aparece como "sem nome no caixa".

## As metas

Sábado e feriado, R$ 12.000; domingo, R$ 15.000 (R$ 18.000 até 04/11/2026: ele baixou, e a
atualização da 1.47.0 muda a regra da loja sozinha, só se ela ainda estiver nos R$ 18.000, com o
antes e o depois na auditoria). Batida, cada pessoa que trabalhou no dia ganha R$ 30, e mais R$ 10 a cada R$ 1.000 inteiros acima da meta. O SET não sabe quem
trabalhou (freela não tem usuário), então o prêmio sai **por pessoa**, e a tela mostra os
nomes de quem abriu caixa ou passou venda naquele dia.

Feriados que o sistema já conhece (`apps/caixa/feriados.py`): os nacionais (com o 20 de
novembro desde 2024), o de São Paulo (9 de julho) e os de Embu das Artes: o aniversário da
cidade (18 de fevereiro), a Sexta-feira da Paixão e Corpus Christi, que mudam de data com a
Páscoa. Carnaval não é feriado em Embu; se a loja quiser meta nele, escreve a data em "Outros
feriados". A tela de regras mostra a lista do ano.

**O que liga as duas coisas, e é a razão do pedido**: o dia que só bateu a meta, ou só chegou
naquele prêmio, por causa de venda fora da regra. A conta tira do dia as vendas fora da
regra que ninguém aprovou e diz como ele ficaria. Em agosto de 2026, com a meta do domingo de
então (R$ 18.000), as **três** metas batidas dependeram disso: num sábado a meta não teria sido batida (R$ 12.758,50, e R$
11.784,00 sem elas) e nos outros dois o prêmio teria sido R$ 30 em vez de R$ 60 e de R$ 40.

## A aprovação do grupo

A aprovação acontece no grupo, antes da venda; o sistema anota **depois**, para a venda sair
da lista de fora da regra. Cada venda tem "Foi aprovada no grupo? Anotar": quem aprovou (um
dos nomes da regra) e uma observação, se quiser. Fica em `DescontoAprovado` com quem anotou e
quando, e na auditoria (`caixa.desconto_aprovado`).

**Desfazer** devolve a venda para a lista e não apaga nada: a linha ganha a data e quem
desfez (`caixa.aprovacao_desfeita`). Só uma aprovação vale por venda (restrição
`uma_aprovacao_valendo_por_venda`), e duas pessoas anotando ao mesmo tempo dão uma só.

## No e-mail Vendas do dia

O e-mail diário ganhou dois blocos, quando houver o que dizer:

- **Meta do dia** (sábado, domingo ou feriado): bateu ou quanto faltou, e o aviso quando a
  meta dependeu de venda fora da regra.
- **Descontos fora da regra**: venda, quem recebeu, o motivo e quanto passou, com o link da
  tela. Dia sem venda fora da regra não ganha o bloco.

## O aviso no grupo das metas (desde a 1.47.0)

Pedido dele (04/11/2026): *"enviar notificação de telegram meta batida feriado 12mil, sábado 12
mil reais e domingo 15 mil reais"*, no grupo METAS do Telegram. O robô é o mesmo dos
relatórios (tela Alertas); o grupo é outro destino, com interruptor próprio, e se liga em
Alertas > Grupo das metas. A conta é a desta tela (`descontos.do_dia`), nunca outra.

- **Quando sai**: na volta da tarefa de hora em hora (`enviar_relatorios`) depois da
  importação que trouxe o dia. O sistema só sabe do sábado quando o backup do SET traz o
  sábado: com backup à noite, o aviso do sábado chega no domingo de manhã. A mensagem diz
  até que hora há venda na conta ("vendas até 17:56").
- **Quantas vezes**: uma por dia de meta e, se uma importação seguinte trouxer o prêmio um
  degrau acima, outra ("O prêmio subiu!"). O mesmo número não se repete. Só os dias de meta
  dos últimos três dias entram: ligar o aviso não despeja no grupo os fins de semana antigos.
- **O que diz**: o dia, o vendido, a meta, o prêmio por pessoa e o próximo degrau. Quando a
  meta só bateu (ou o prêmio só subiu) por venda fora da regra sem aprovação anotada, uma
  linha diz quantas vendas, quanto, e como o dia ficaria sem elas. **Nenhum nome**: o grupo
  é de muita gente, e quem passou cada venda está nesta tela.
- **Se falha**: três tentativas por dia de meta em cada dia, o erro em português na tela
  Alertas, e a tarefa segue com os relatórios. Nome de grupo com emoji não derruba mais o
  log da tarefa (o console do Windows não é UTF-8).
- **O robô no grupo**: o link de convite não serve para robô. Alguém do grupo o adiciona pelo
  nome de usuário dele; depois, em Alertas, "Descobrir o grupo" e "Usar para as metas". Grupo
  em que só administrador escreve pede o robô como administrador.

Fica em `EnvioDeRelatorio` com a rotina `metas`, o dia da meta e o prêmio avisado (migração
`alertas.0006`), que é como o sistema sabe o que já saiu. Rodar só o aviso, no servidor:
`manage.py enviar_relatorios --rotina metas`.

## O que o sistema não faz

- **Não mexe no SET** nem trava venda no caixa: ele lê a cópia do backup, como o resto.
- **Não confere parcelas**: o SET não grava em quantas vezes o cartão foi passado.
- **Não sabe quem trabalhou**: os nomes são de quem passou venda ou abriu caixa. Freela sem
  usuário não aparece.
- **Não paga prêmio nem pune ninguém**: mostra a conta. A decisão é da gerência.

## Ler do SET (desde a 1.46.0)

- `VENDAS.TOTALPROD`: o total dos produtos antes do desconto do fechamento.
- `ICAIXA.USUARIO` das linhas de tipo `R` (recebimento): o primeiro de cada venda.
- `FATVENDAS.FORMAPAGTO` e `VALOR`: as partes do pagamento, somadas por forma.
- `IVENDAS.VALORPROD` e `PRECOVENDA`: o preço cobrado e o de tabela de cada item.

`ICAIXA.CLIFORNE` e `FATVENDAS.OBSERVACAO` podem ter nome de cliente e **não são lidos**; um
teste (`apps/importacao/tests/test_importacao.py`) recusa o nome dessas colunas na leitura.
A importação anterior a esta versão não tem os campos novos: a tela avisa e usa só o
desconto do fechamento até a primeira importação depois da atualização.

## Arquivos

- `apps/caixa/descontos.py`: a conta inteira (venda, produto, pessoa, meta).
- `apps/caixa/feriados.py`: os feriados e a Páscoa.
- `apps/caixa/forms.py`: as regras (número com vírgula: `12.000`, `12.000,00` e `7,5`) e a
  aprovação.
- `apps/caixa/models.py`: `RegraDeDesconto` e `DescontoAprovado`; migração `caixa.0002`, e a
  `caixa.0003`, que baixa a meta do domingo para R$ 15.000.
- `apps/alertas/metas.py`: o aviso no grupo das metas (1.47.0), com os testes em
  `apps/alertas/tests/test_metas.py`.
- `apps/importacao/models.py`: os campos novos da venda e do item; migração `importacao.0014`.
- `templates/caixa/descontos.html` e `templates/caixa/regras_de_desconto.html`.
- Testes: `apps/caixa/tests/test_descontos.py`, e os novos de
  `apps/importacao/tests/test_itens_de_venda.py` e `apps/alertas/tests/test_relatorios.py`.
