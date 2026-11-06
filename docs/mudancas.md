# Mudanças do sistema

Uma entrada por versão entregue, da mais nova para a mais antiga. O número que
aparece no pé das telas do sistema e no histórico de importações é o daqui.

A regra do número: o primeiro dígito só muda em reescrita; o segundo muda quando
entra função nova; o terceiro, em correção. O pacote enviado ao servidor leva
esse número, mais o commit e a data da geração, no arquivo `VERSAO`.

## 1.50.0 — 06/11/2026

Pedido dele (06/11/2026): *"na area logada / na parte de cima do menu colocar a data e hora
em real time / na parte de cima do menu colocar um linha formato carrossel informando valor
do dólar comercial no momento em destaque e os principais ações em alta e queda de em real
time"*. Ficha: `docs/cotacoes.md`.

- **Faixa do topo**, logo acima do menu, em todas as telas depois de entrar: o relógio (dia,
  data e hora, andando a cada segundo), o **dólar comercial** em destaque (preço de venda,
  variação do dia e hora do preço) e as ações rolando, em **Em alta**, **Em queda** e **Sem
  mudança**.
- **De onde vem**: o dólar da AwesomeAPI e as ações da brapi.dev, de graça e sem cadastro.
  Sem cadastro a brapi responde quatro ações (Petrobras, Vale, Itaú e Magalu), com uns 30
  minutos de atraso: o preço ao vivo da B3 é pago. A faixa diz a hora de cada preço.
- **Nenhuma tela espera a internet**: a tela lê o que o servidor guardou, e o servidor busca
  em segundo plano (o dólar no máximo uma vez por minuto, as ações a cada 15 minutos, e só
  enquanto alguém está com o sistema aberto). Sem internet, fica o último valor.
- **O pedido de cada minuto não conta como uso**: a sessão parada continua acabando em 30
  minutos, e a tela esquecida aberta agora vai sozinha para a entrada quando ela acaba.
- **O vendedor fica só com o relógio**: a tela dele não mostra R$ nenhum, nem o do dólar.

## 1.49.0 — 04/11/2026

Pedido dele (04/11/2026, com o print do Faturamento mês a mês e do menu): *"dashboard = nesse
gráfico de faturamento mês a mês informar os últimos 3 anos letivos / no menu Dinheiro =
alterar para Contas a pagar, eu acho que faz mais sentido e fica intuitivo"*.

- **Faturamento mês a mês do Dashboard com os três últimos anos**, de janeiro a dezembro, uma
  linha por ano (verde este ano, laranja o passado, azul o retrasado): o desenho das Contas
  pagas mês a mês da 1.48.0, com a cor da porcentagem ao contrário (vender mais é verde). A
  tabela "Ver o valor de cada mês" tem os três anos e a linha "Até 3/nov" de cada um. Os 13
  meses de antes saíram (`_monitor_linha.html`, `Mes`, `GraficoDeLinha`).
- **A importação lê a venda por mês desde o dia 1º de 36 meses antes** (eram 730 dias) e grava
  `vendas_mes_desde`; o pedaço do mês do corte (`mes_parcial`) ganhou o do ano retrasado. Até
  a primeira importação depois de atualizar, o começo de 2024 fica em branco, e não em zero.
  A compra por mês continua nos 730 dias.
- **Menu: "Dinheiro" virou "Contas a pagar"**, com as mesmas telas (Financeiro, Caixa,
  Descontos e metas, Conciliação). Endereços e permissões não mudaram.
- Por dentro: os três anos são um código só (`dashboard.tres_anos` e `TresAnos`), usado pelo
  Dashboard e por Contas a pagar.

## 1.48.0 — 04/11/2026

Pedido dele (04/11/2026, com o print do gráfico de Contas a pagar): *"gráfico ficou bom /
nesse mesmo gráfico do contas a pagar manter sempre os últimos 3 anos letivos"*.

- **Contas pagas mês a mês com os últimos três anos**: o mesmo quadro, agora de janeiro a
  dezembro, com uma linha para cada ano (este ano em verde, o ano passado em laranja e o
  retrasado em azul). A porcentagem embaixo do mês continua sendo este ano contra o ano
  passado, na cor do caixa, e o mês que corre continua tracejado e comparado com o mesmo
  pedaço do ano passado. Em "Ver o valor de cada mês" estão os três anos lado a lado e uma
  linha com cada ano de 1º de janeiro até o dia dos dados. O Dashboard não muda.
- **A importação lê três anos de contas pagas**, desde o dia 1º de 36 meses antes; as contas
  recebidas continuam em 24 meses. Até a primeira importação depois da atualização, o ano
  retrasado aparece só a partir de onde a foto anterior começava.
- **Mês que o SET não tem fica em branco, e não em zero**: a primeira conta paga do SET da
  loja é de 27/02/2024, então janeiro e fevereiro de 2024 ficam em branco, e a tabela diz
  por quê.
- No celular, a tabela dos três anos mostra os valores em reais redondos, para a variação
  caber na tela.

## 1.47.1 — 04/11/2026

Pedido dele (04/11/2026, com o print de `C:\instalacao\pacote`): *"padronizar envio do pacote
de atualização sempre no diretório /pacote / apartir desse caminho atualizar o script de
atualização e higienizacao"*. Traz junto tudo da 1.47.0, que não chegou a ser instalada.

- **Uma pasta só para atualizar**: o zip novo vai em `C:\instalacao\pacote`, e os dois
  comandos rodam dela, `C:\instalacao\pacote\atualizar.ps1` e
  `C:\instalacao\pacote\higienizar.ps1`. O atualizador acha o zip ali (e ainda em
  `C:\instalacao`, o lugar de antes), guarda o zip em `historico` antes de trocar a versão e
  esvazia a pasta em vez de apagá-la, porque o Windows não apaga pasta aberta num
  PowerShell. Se a troca falhar, o zip volta para a pasta e o sistema fica como estava.
- **O `higienizar.ps1` roda da pasta do pacote**: até aqui ele achava o sistema subindo uma
  pasta a partir de onde estava, e da pasta do pacote procurava o Python em `C:\instalacao`
  e saía calado. Agora, fora de `C:\cabana-sistema\scripts`, ele vai para
  `C:\cabana-sistema`, e mostra na tela o que limpou.
- A Ficha técnica, o `LEIA-ME.txt`, os avisos de erro da importação e a documentação mostram
  os comandos novos (`higienizacao.md`). Os de antes continuam valendo.
- **Só desta vez**: o atualizador que está no servidor, o da 1.46.0, ainda procura o zip em
  `C:\instalacao`. Para instalar a 1.47.1, o zip vai em `C:\instalacao` e o comando é o de
  antes; daí em diante, a pasta do pacote.

## 1.47.0 — 04/11/2026

Pedido dele (04/11/2026, com o print do Dashboard): *"usar esse formato de gráfico também em
contas a pagar / em compra guiada, exibir todos os produtos de cada fornecedor, priorizar os
produtos em falta E acabando e em seguida todos os demais. / enviar notificação de telegram
meta batida feriado 12mil, sábado 12 mil reais e domingo 15 mil reais"*, no grupo METAS.

- **Contas a pagar com os gráficos do Dashboard**, no alto da tela: **Contas pagas mês a mês**
  (13 meses, a linha laranja é o mesmo mês do ano passado, e aqui pagar mais é vermelho), **O
  que está em aberto** (atrasadas, vencem em até 7 dias, depois e sem data; o nome de cada
  fatia abre a lista dela) e **Para onde vai o dinheiro** (o pago em 12 meses pela
  classificação do SET). O mês que corre se compara com o mesmo pedaço do ano passado. São os
  mesmos desenhos, do mesmo arquivo do Dashboard (`dashboard.md`).
- **A importação lê o pago e o recebido em meses inteiros**: desde o dia 1º de 24 meses antes,
  e não mais "corte menos 730 dias", que começava no meio de um mês e faria o primeiro mês do
  gráfico comparar um mês cheio com dez dias. Até a primeira importação depois da
  atualização, o primeiro mês aparece sem comparação.
- **Compra guiada com todos os produtos do fornecedor**: a conferência mostra primeiro **Em
  falta e acabando** (o que a conta pede, como antes) e logo depois **Os outros produtos** do
  fornecedor, em zero: o que a conta pedia mas ficou fora da escolha, o que vendeu no ano (do
  que mais faturou para o que menos), o parado e o que não vendeu, cada um dizendo por que
  está ali. Escrever um número põe o produto no pedido; a busca acha pelo nome ou pelo código
  (`compra-guiada.md`).
- **Aviso de meta batida no grupo das metas, pelo Telegram**: quando o sábado, o domingo ou o
  feriado bate a meta, o robô manda no grupo o vendido, a meta, o prêmio por pessoa e o
  próximo degrau, e outro aviso se o prêmio subir. Sai depois da importação que traz o dia
  (com o backup do SET feito à noite, o sábado chega no domingo de manhã). Quando a meta só
  bateu por venda com desconto fora da regra sem aprovação, o aviso diz isso numa linha, sem o
  nome de ninguém. Liga-se em **Alertas > Grupo das metas**: o robô precisa ser adicionado ao
  grupo por alguém de lá, porque o link de convite não serve para robô
  (`descontos-e-metas.md`, `alertas-por-email.md`).
- **Meta do domingo de R$ 15.000** (era R$ 18.000). A atualização muda a regra da loja
  sozinha, só se ela ainda estiver nos R$ 18.000, e deixa o antes e o depois na auditoria.
  Sábado e feriado continuam R$ 12.000.
- **O log da tarefa dos relatórios não cai mais com emoji** no nome de um grupo do Telegram:
  o console do Windows não é UTF-8, e o erro vinha depois de a mensagem já ter saído.

## 1.46.0 — 02/11/2026

Pedido dele (02/11/2026): as regras de pagamento que a gerência passa à equipe (*"À vista, no
Pix ou dinheiro: 7% de desconto. Cartão de crédito: em até 3x, sem desconto. Qualquer condição
diferente precisa de aprovação no grupo antes de ser confirmada ao cliente."*), as metas do
sábado, do feriado e do domingo, e *"no financeiro do caixa, tentar buscar os descontos de cada
produto seguindo as regras. ideia é controlar os desconto para que os funcionarios dê desconto
sem parâmetros só objetivando a premiação. A empresa nao pode se prejudicar financeiro."* Como
a conta funciona está em `descontos-e-metas.md`; o passo a passo, em
`manual/descontos-e-metas.md`.

- **Descontos e metas**, a tela nova de Dinheiro, logo depois do Caixa: cada venda com
  desconto contra as regras da loja, da que mais passou para a que menos passou, com o motivo
  em português ("Passou R$ 30,00 da regra: no cartão de crédito ela é sem desconto."), os
  produtos da venda e quem recebeu no caixa.
- **O desconto que o SET não mostra**: além do desconto do fechamento, o preço do produto
  mudado no caixa antes de fechar a venda. Em agosto, 71 das 134 vendas fora da regra tinham
  desconto só assim, e no SET aparecem sem desconto nenhum.
- **A meta de cada sábado, domingo e feriado**, com o prêmio por pessoa e a conta do dia sem
  as vendas fora da regra. Em agosto, as três metas batidas dependeram delas: uma não teria
  sido batida e duas teriam pago menos.
- **A aprovação do grupo se anota na venda**: quem aprovou e uma observação. A venda sai da
  lista; Desfazer a devolve, nada é apagado e tudo vai para a auditoria.
- **Regras e metas** mudam na tela, com os feriados de Embu das Artes já dentro (aniversário
  da cidade, Sexta-feira da Paixão e Corpus Christi) e um campo para os outros. O débito começa
  sem desconto, porque a regra não fala dele.
- **O e-mail Vendas do dia** ganhou a meta do dia e as vendas fora da regra, com o link da
  tela.
- **A importação passa a ler do SET** o total dos produtos antes do desconto, quem recebeu no
  caixa, as partes do pagamento e, em cada item, o preço cobrado e o de tabela. Desde julho o
  SET não grava o preço de tabela na venda: vale o do cadastro, guardado o primeiro que o
  sistema viu, para um aumento de preço depois da venda não parecer desconto.
- **Permissão nova, Controlar descontos e metas**, que entra só no Administrador gerência.
- **Filtro e cartões não ficam mais colados** no Caixa, no Ticket médio, em Vendas do dia e em
  Comparar, e a última linha das tabelas com o nome na primeira coluna perdeu o risco que
  sobrava embaixo dele.

## 1.45.0 — 02/11/2026

Pedido dele (02/11/2026, com dois prints): *"remover linha branca em volta do logotipo / no
menu compras criar um sub menu compra guiada / fazer formato tipo apresentação, pop up, só que
com perguntas fechadas ou abertas para informar tipo ou quantidade para formatar a sugestão de
compra [...] Hoje o formato está longe de está intuitivo e fácil de operar, preciso que empenho
máximo nesse recurso, a funcionaria que trabalhava com essa parte saiu da empresa e não deixou
nenhuma informação registrada. / no gráfico principal do dashboard, inserir na vertical mais
faixas de valores 10.000 50.000 80.000 120.000 150.000 250.000"*. Como a compra guiada
funciona está em `compra-guiada.md`; o passo a passo de quem compra, em
`manual/compra-guiada.md`.

- **Compra guiada**, a segunda tela de Compras (e o botão Começar no alto da Lista de compra):
  o pedido de um fornecedor montado em perguntas, uma por tela, num cartão de apresentação com
  a barra de andamento. A primeira tela lê a loja inteira (prateleira, parado sem vender, o que
  falta, quanto cabe no mês e os que mais vendem e estão acabando) e pergunta o fornecedor; as
  outras perguntam o prazo de entrega (quando ninguém informou), quando se volta a comprar,
  que tipos entram, em que venda se basear, a quantidade dos cinco que mais vendem, as
  encomendas e as sugestões da equipe, e o orçamento. No fim, a conferência com a tabela
  inteira editável, o recado ao fornecedor e Gerar o pedido.
- **Cada resposta mostra a consequência antes de ser escolhida**: quantos produtos, quanto
  custa e por quanto tempo o pedido segura a loja. A conta é a da Lista de compra, com as
  respostas no lugar dos números fixos: com a próxima compra "na semana que vem", dá o mesmo
  número da Lista.
- **Fica registrado como cada compra foi decidida**: quem, quando, o pedido e um resumo das
  respostas, na primeira tela e na pergunta da próxima compra do mesmo fornecedor. O prazo de
  entrega respondido vai para a ficha do fornecedor e passa a valer na Lista de compra.
- **A conferência pergunta antes de comprar o que dura mais de um ano** na prateleira, com
  "Tirar do pedido". Quase sempre é o estoque mínimo cadastrado no SET (2.807 produtos têm um)
  maior do que o produto vende.
- **O pedido segue a regra de Pedidos**: o da gerência nasce valendo; o da Líder de loja e o
  do perfil Compras, esperando a gerência; quem só monta baixa a folha com o aviso. Gerar duas
  vezes não faz dois pedidos, e o Enter numa quantidade não gera pedido (desce para a linha de
  baixo).
- **A linha branca em volta do logotipo foi erro meu na 1.44.0**: a etiqueta nova da tela de
  perfis tinha o mesmo nome da classe do logotipo (`marca`), e o logotipo ganhou a moldura e
  as letras de etiqueta. A mesma troca de nome mexeu no alinhamento dos botões "Gerar pedido"
  da Lista de compra e de Pedidos e do "Enviar agora" da cópia do programa no GitHub
  (`formulario-em-linha`). Os dois voltaram, e um teste novo recusa a mesma classe definida
  em dois cantos do `sistema.css`.
- **Faturamento mês a mês** ganhou as faixas de 10, 50, 80, 120, 150 e 250 mil no eixo
  vertical, junto com as redondas. Rótulo que encostaria no vizinho fica só com a linha.
- **O botão que trava contra o duplo clique é o que foi apertado.** Antes era sempre o
  primeiro do formulário: num formulário com dois botões, "Salvar" mudava o outro para
  "Gerando…".

## 1.44.0 — 02/11/2026

Pedido dele: o prompt "Implementação do módulo de usuários e controle de acesso do Aux SET",
com perfis por cargo (*"Gerência, Administrador de acessos, Compras, Estoque, Operador,
Consulta/Auditoria"*), regras de concessão, sessões, auditoria e *"Comece examinando o
projeto e apresente um plano curto. Depois implemente em etapas funcionais, mantendo a
aplicação utilizável."* Esta é a etapa 1 de 4 (`diagnostico-controle-de-acesso.md`); como
ficou está em `controle-de-acesso.md`, e o passo a passo da gerência em
`manual/usuarios-e-acessos.md`.

- **Ninguém muda de acesso na atualização.** Os quatro perfis de hoje ficam com o que tinham
  e as mesmas pessoas. Chegam quatro prontos para usar, sem ninguém dentro: **Administrador
  de acessos** (cuida de contas sem ver número da loja), **Compras**, **Estoque** e
  **Consulta e auditoria**. (A decisão do cartão "somar ou trocar pelos seis" seguiu a
  recomendada, somar, enquanto ele não responde.)
- **Usuários virou lista e ficha.** A lista tem busca e filtro pela situação (ativos,
  pendentes de ativação, bloqueados, desligados). A ficha de cada pessoa junta perfis (pode
  ser mais de um, e a pessoa pode a soma), senha e e-mail, a situação, **o que ela pode de
  fato** e de qual perfil vem cada coisa, as **sessões abertas** com o aparelho e de onde (e
  o botão para encerrar uma ou todas) e o **histórico** do acesso dela, inclusive as
  tentativas de abrir o que não podia.
- **Perfis e permissões**, uma tela nova dentro de Usuários: a tabela de cada perfil contra as
  37 permissões, com as de dinheiro e as de administração marcadas; editar o que um perfil
  pode (com o motivo, que vai para a auditoria); criar perfil para um cargo novo copiando o
  mais parecido; retirar perfil vazio; e o quadro **O que pede atenção** (quem administra,
  quem vê dinheiro, quem está sem perfil, as contas técnicas do servidor).
- **As travas**: ninguém muda o próprio acesso; ninguém dá a outra pessoa acesso a dinheiro
  ou à administração que não tem (nem mexe na senha de quem tem); a conta técnica do
  servidor só se mexe no servidor; e **sempre fica alguém administrando**: o sistema não
  deixa bloquear, encerrar ou tirar o perfil da última pessoa que administra, nem pela data
  marcada para o acesso acabar. Valem também para o envio montado à mão, porque são
  conferidas no servidor na hora de gravar.
- **A senha de novo** para abrir a área de acessos: fica aberta enquanto se usa e fecha com
  15 minutos parada; cinco senhas erradas encerram a sessão.
- **Bloqueado é diferente de desligado**: bloquear (férias, afastamento) para o acesso por um
  tempo, com o motivo, e desbloquear devolve tudo como estava; encerrar é para quem saiu da
  empresa. Os dois derrubam as sessões abertas na hora.
- **O "ver os indicadores" foi dividido** em cinco: indicadores, lista de compra, vendas,
  custo e margem, e importações. Até a 1.43.0 era uma permissão só que abria todo número da
  loja, e um perfil de Compras veria o lucro. Quem tinha a antiga ganhou as quatro novas na
  atualização: cada pessoa abre exatamente as telas de antes.
- **Os grupos antigos** que a reinstalação da 1.4.0 recriou em 22/10 (Gerência, Compras,
  Estoque, Operadores, Consulta e auditoria, com as permissões do começo e ninguém dentro)
  foram limpos: os perfis novos com o mesmo nome não herdam o que eles tinham.
- **Na auditoria, a mais**: tentativa de abrir tela sem permissão (uma por minuto por pessoa
  e endereço), cada arquivo baixado (planilha, CSV, PDF ou texto com dado da loja), perfil
  editado com o que entrou e o que saiu, bloqueio, sessão encerrada, a senha confirmada ou
  errada, e a entrada da conta técnica marcada como tal. Senha nunca.
- **As frases do prompt**: "Use seu próprio usuário. As ações ficam registradas para controle
  e organização do trabalho." no alto e na entrada, e "Seu usuário não tem permissão para
  esta ação. Procure a gerência." no acesso negado.
- **O instalador não desfaz mais** o que a gerência mudar num perfil: até a 1.43.0 ele
  regravava cada perfil com o que estava no código a cada atualização.
- **No servidor**: `recuperar_administrador`, para quando ninguém mais consegue administrar
  pela tela (reativa a conta, devolve o perfil e pede a senha nova), e
  `relatorio_de_acessos`, para conferir quem pode o quê sem entrar no sistema.
- A suíte tem 1.903 testes, 79 a mais que na 1.43.0, e passou inteira.

## 1.43.0 — 31/10/2026

Pedido dele, com o print do Dashboard e a foto da fachada: *"gostei do visual escuro / na
tela de login manter o layout com as cores da empresa, mas com umas pegadas degrade para o
escuro (...) usar como teste o a foto da frente da loja no plano de fundo da tela de login
como marca d'agua bem franquinho em preto e branco (...) adotar recurso de recuperar senha
por e-mail cadastrado via confirmação de código, senão tiver cadastro informe que não é
possível, procure o administrador do sistema. / melhor visualização e cansa menos os olhos /
adaptar e aplicar em todo o sistema (...) logo quando fazer login quero que abra o
Dashboard (...) no mesmo menu (principal) colocar ao lado como segunda opção a visão geral.
/ adotar o esquema Grafana em todo o sistema."*

- **O sistema inteiro ficou escuro, nas cores do Dashboard**: fundo quase preto puxado para
  a madeira, quadros um tom acima, letra creme em vez de branco puro (cansa menos), e as
  cores de situação do Grafana em toda tela (verde bom, laranja atenção, vermelho ação, azul
  para link). Nenhuma tela mudou de desenho nem de conta. As 48 telas foram abertas no
  computador e no celular por um programa que mediu o contraste de cada letra visível
  (`docs/evidencias/contraste-1.43.0.md`). As páginas de erro também ficaram escuras.
- **O que vai para o papel continua claro**: folha do pedido, etiquetas, folha de contagem
  e qualquer tela impressa voltam às cores de antes na impressão. Os PDFs e os e-mails não
  mudaram. A folha de etiquetas parou de imprimir o aviso da data dos dados em cima da
  primeira fileira, e a Visão geral impressa ganhou letra escura no título.
- **Entrar abre o Dashboard**, e o menu de cima tem sete entradas: **Dashboard, Visão geral**,
  Compras, Vendas, Estoque, Dinheiro e Sistema. O Dashboard saiu de dentro de Vendas. Ele
  fica guardado depois de cada importação, como a Visão geral, então abrir com ele não ficou
  mais lento (36 consultas guardado, contra 90 sem guardar). Quem não abre o Dashboard (o
  vendedor) continua caindo na Consulta.
- **Tela de entrada nova**: o mesmo desenho (marca em cima, cartão no meio, versão e servidor
  embaixo) num fundo que desce da madeira e da brasa da loja para o escuro, com a **fachada
  da loja em preto e branco, bem fraquinha**, por trás. **A foto é teste**: para tirar, é uma
  linha do CSS (`docs/tela-escura.md`). Ganhou o botão **Mostrar** a senha e o aviso de
  **Caps Lock ligado**, as duas causas comuns de "a senha não entra".
- **Esqueci a minha senha**, na tela de entrada: a pessoa digita o usuário (ou o e-mail) e
  recebe no **e-mail cadastrado** um código de seis números, que vale 15 minutos e uma vez
  só, com 5 tentativas. Com ele, cria a senha nova na mesma tela, e um segundo e-mail avisa
  da troca. **Sem e-mail cadastrado, a tela diz que não é possível e manda procurar o
  administrador do sistema.** O bloqueio de 5 senhas erradas sai junto com a senha nova.
- **Onde se cadastra o e-mail**: a própria pessoa, em Trocar a minha senha (pede a senha de
  agora); a gerência, no quadro novo "E-mail para recuperar a senha" da tela de usuários,
  que também marca quem está sem e-mail.
- Proteções: a mesma frase para usuário que não existe, sem e-mail ou desligado (ninguém
  descobre quem tem conta); o código não fica guardado, só a assinatura dele; no máximo 5
  códigos por pessoa e 10 pedidos do mesmo computador por hora; tudo na auditoria, com o
  meio do e-mail escondido (`docs/sessao-e-acesso.md`).
- **O código sai pelo envio da tela Alertas.** Enquanto a senha da caixa `naoresponder@` não
  estiver colada lá, a recuperação responde que o envio de e-mail não está configurado.
- **Correção no endereço seguro (8443, o do celular)**: cerca de 1 em cada 200 páginas, e
  até 3 em cada 100 com o servidor ocupado, podiam chegar cortadas, sem o fim (às vezes sem
  o CSS ou uma imagem), porque o túnel do HTTPS usava o mesmo TLS em duas linhas ao mesmo
  tempo. Agora é uma linha só por conexão: nenhuma cortada em 1.200 seguidas
  (`docs/https-e-camera.md`). O balcão, que entra por HTTP, nunca passou por isso.

## 1.42.0 — 31/10/2026

Pedido dele, com a ficha e a descrição do cargo da Cássia: *"criar acesso para nova
funciona Cassia inicio 26/10/2026 / ficara no lugar da barbara ate dia 12/11/2026 / será
líder de loja / acesso moderado as informações gerenciais / foco sera compras de
mercadorias / controle de fornecedores / gestao da equipe local / lançamentos de
pagamentos / controle de estoque"*.

- **Perfil novo, Líder de loja**: tudo do Operador administrativo (fornecedores, lançar
  pagamento, financeiro, caixa, conciliação, contagem e inventário, painéis), mais **montar
  o pedido ao fornecedor** e **responder as sugestões da equipe**. Não mexe em usuários,
  auditoria, importação, configurações, dados da empresa, lista de compra nem na regra do
  alerta.
- **O pedido que a Líder de loja monta espera a aprovação da gerência**, como diz a descrição
  do cargo ("Nenhuma compra é confirmada sem aprovação prévia"). A folha sai com o aviso em
  vermelho, no alto, de que ainda não vale; a gerência aprova com um clique na tela do
  pedido, e a folha que vale fica anexada com o nome de quem montou e de quem aprovou.
  Recusar é cancelar, com o motivo. Enquanto espera, ela muda a quantidade no próprio
  pedido; depois de aprovado, só a gerência mexe.
- **"Aprovar os pedidos da loja"** entra em O que fazer agora, na Visão geral e no Dashboard,
  com quantos pedidos esperam e quanto somam. Só para a gerência. Vem logo depois das
  urgentes, e aparece e some na hora: a agenda fica guardada até a próxima importação, mas o
  que alguém da loja espera de resposta é contado a cada abertura. A sugestão da equipe, que
  também esperava a importação seguinte para aparecer, passou a fazer o mesmo.
- **Data para o acesso acabar**, no quadro "Acesso com data para acabar" da tela de usuários
  e na criação da conta.
  "Até 12/11" entra no dia 12 inteiro; no dia 13 a conta se desliga sozinha, a sessão aberta
  cai e a auditoria registra o motivo. Liberar de novo tira a data.
- **Trocar a minha senha**, pelo nome no alto da tela, para todos os perfis. A tela de
  usuários mandava "peça para ela trocar na primeira entrada" e não havia onde. Pede a senha
  de agora, segue as mesmas regras e derruba as sessões dos outros aparelhos.
- A foto que veio junto não tem lugar no sistema e não foi guardada.
- Traz junto tudo da 1.40.2 à 1.41.0.

## 1.41.0 — 31/10/2026

Pedido dele, com o print de um painel do Grafana: *"adaptar os recursos de grafana no
dashbord / a visualização fica bem bonita e facil de entender"*.

- **O Dashboard ganhou o jeito do Grafana**, na mesma tela e no mesmo menu: fundo escuro,
  quadros numa grade, o número grande na cor da situação (verde bom, laranja atenção,
  vermelho ruim) com um minigráfico do período embaixo, o faturamento mês a mês em linha
  (este ano e o ano passado), a margem num mostrador, roscas para ruptura, estoque
  parado, forma de pagamento e grupos, e colunas para dia da semana e hora.
- **Situação da loja**, o primeiro quadro: a palavra do item mais grave de "O que fazer
  agora" (Urgente, Atenção ou Tudo em dia). Clicar leva à lista.
- **O que fazer agora** também no Dashboard, com a gravidade escrita ao lado de cada item.
  É a mesma lista da Visão geral, e cada um vê só o que o seu perfil abre.
- As explicações de cada quadro foram para o **"i"** no canto, e o valor de cada mês, para
  **"Ver o valor de cada mês"** embaixo da linha. Nada saiu da tela.
- A forma de pagamento aparece com o nome da loja ("Cartão de crédito", "Dinheiro"), igual
  ao e-mail do caixa.
- Não é o Grafana instalado: seria um programa a mais no servidor, com senha e permissão à
  parte e as contas copiadas, que um dia discordariam das do sistema. Ficaram de fora o
  mapa do modelo e a atualização a cada 10 segundos.
- Traz junto tudo da 1.40.2 à 1.40.6.

## 1.40.6 — 29/10/2026

Pedido dele, antes de instalar a 1.40.5: *"inserir o total de vendas do dia, somando
tudo(dinheiro + pix + cartão de debito + cartão de credito)"*.

- **Total de vendas do dia** no fim do bloco Caixa do dia, somando as quatro formas de
  todos os caixas. Quando o número fica abaixo do "vendeu" da manchete por causa do
  desconto no fechamento do cupom, a linha diz o desconto; quando não bate com os cupons
  por outro motivo (venda a prazo, estorno, recebimento de outro dia), diz o total dos
  cupons e manda conferir na tela Caixa.
- Traz junto tudo da 1.40.5.

## 1.40.5 — 29/10/2026

Ele corrigiu o caixa do e-mail: *"inicio do caixa em dinheiro, final do dia caixa em
dinheiro, pagamento por pix, pagamento por cartao de debito"* e de crédito.

- **O final do caixa no e-mail Vendas do dia agora é o DINHEIRO na gaveta**, pela mesma
  conta da tela Caixa (início + vendas em dinheiro + entradas − sangrias − pagamentos),
  com a conta escrita embaixo. A 1.40.4 usava o saldo final do SET, que soma PIX e
  cartão: R$ 8.180,65 num dia em que a gaveta tinha R$ 867,65.
- **PIX, cartão de débito e cartão de crédito** vêm cada um na sua linha, pelo que o SET
  gravou no turno.

## 1.40.4 — 28/10/2026

Pedido dele: *"no disparo de e-mail diário sobre vendas do dia inserir o valor de caixa
inicial e final junto com o operador que abriu e fechou o caixa"*.

- **O e-mail Vendas do dia ganhou o bloco "Caixa do dia"**, logo depois do resumo: para
  cada caixa do dia, quem abriu, a que horas e com quanto, e quem fechou, a que horas e
  com quanto. Os valores são os do SET, os mesmos da tela Caixa.
- Caixa ainda aberto na importação sai como "Ainda aberto", sem valor final inventado;
  caixa que virou a noite leva a data do fechamento junto da hora.
- O Telegram leva as mesmas linhas ("Abriu: MARIA — R$ 200,00").

## 1.40.3 — 27/10/2026

Ele viu "a última cópia subiu em 22/10" no dia 27 e perguntou se estava errado. Não
estava, mas a tela levava a pensar outra coisa: *"no sistema, a nomenclatura deixa a
entender outra coisa"* e *"mencionar que [é] algo relacionado ao github, mas somente quando
ha alteracoes ou implementacoes"*.

- **"Backup" virou "Cópia do programa no GitHub"**: no menu Sistema, no título da tela, no
  e-mail e no Telegram do aviso e nas linhas que a atualização escreve. "Backup" sozinho
  fazia pensar nos dados da loja, que nunca vão para o GitHub.
- **Em dia, a tela diz qual versão está lá e por que a data fica parada**: "O GitHub tem a
  versão X, copiada em ... Esta data só muda quando há alteração ou implementação no
  sistema". Logo abaixo, lembra que os dados do dia têm cópia própria toda noite às 23:30,
  no servidor.
- O nome do aviso diário na tela Alertas mudou junto (migração `alertas.0005`, só o
  rótulo; nada no banco muda de valor).

## 1.40.2 — 22/10/2026

Ele colou o token na tela Backup e a tela ficou parada em "Enviando…": *"coloquei o token
no campo indicado e travou nessa tela, mitigar e corrigir"*.

- **A causa.** O primeiro envio é o sistema inteiro, perto de 500 arquivos, e cada arquivo
  virava um pedido próprio ao GitHub, um atrás do outro, dentro do clique de gravar. Isso
  leva minutos, e o GitHub limita as escritas a 80 por minuto e 500 por hora: o primeiro
  envio esbarrava no limite antes de terminar. O token ficou gravado; o que não terminou
  foi a cópia.
- **O texto agora vai dentro da árvore, em lotes**, e só o que é binário (logo, ícones)
  pede envio próprio. O sistema inteiro sobe em menos de 15 pedidos e num commit só. O
  conteúdo vai com os mesmos bytes, então a atualização seguinte continua mandando só o
  que mudou.
- **Limite do GitHub não é mais confundido com token errado.** Antes a tela dizia para
  conferir a permissão do token; agora diz que o GitHub pediu para esperar, que o token
  está certo e que o sistema tenta de novo sozinho.
- A tela Backup recomenda escolher **No expiration** no token: sem vencimento, o passo
  dele acontece uma vez só.

## 1.40.1 — 22/10/2026

Duas respostas dele à 1.40.0: escolheu **"Quatro no menu"** no cartão sobre o menu de
Compras, e esclareceu o alerta: *"me refiro 30% estoque minimo"*.

- **O menu de Compras caiu de oito telas para quatro**: Lista de compra, Pedidos,
  Fornecedores e Indicadores de compra. Antes de comprar, Sugestões, Sugestões da equipe e
  Últimas compras saíram do menu, não do sistema: abrem pela fileira "Também em Compras",
  logo abaixo do título da Lista, cada uma só para quem tem permissão. Dentro delas
  "Compras" continua aceso e a seta do pé volta para a Lista. O operador administrativo
  continua chegando às Sugestões da equipe.
- **Os 30% passaram a se chamar estoque mínimo**: o cartão do topo virou "Carros-chefe no
  estoque mínimo", e a regra que a gerência muda diz "Estoque mínimo (% do ideal)". A
  conta não mudou: o mínimo é 30% do estoque ideal e não mexe na quantidade a comprar. O
  mínimo cadastrado no SET continua escrito como "Mínimo cadastrado no SET".

## 1.40.0 — 22/10/2026

Pedido dele: *"deixar como padrão alerta de 30% para cada produto no estoque e destacar
para os produtos mais vendidos, carro chefe da loja. manter o modulo mais simples e
intuitivo [...] eu acho que tem muita informação para tomada de decisão rápida"*.

- **Alerta de 30% em cada produto.** A régua é o estoque ideal que a lista já usava (o
  que o produto vende no prazo do fornecedor, mais a semana até a próxima compra e a
  margem de segurança), contando o que está a caminho. O alerta não muda quanto comprar:
  diz o que não pode mais esperar. Mora em `PoliticaDeCompra` (migração 0005), nasce em
  30% e a gerência muda na própria Lista de compra, com o antes e o depois na auditoria.
- **Carro-chefe são os 100 produtos que mais faturaram em 12 meses**, por faturamento e
  não por unidades, só mercadoria de revenda. Na foto de 20/09/2026 eles são perto de um
  terço do faturamento. O número também se muda na tela (de 10 a 500).
- **Cartão "Carros-chefe em alerta" no topo da Lista de compra**: o cruzamento dos dois.
  O alerta sozinho acenderia em 2.100 dos 2.235 produtos da lista, porque a loja nunca
  contou o estoque e quase todo saldo está em zero; cruzado com o carro-chefe são 27. O
  cartão mostra os 10 primeiros com três colunas (produto, tem, comprar) e o nome leva à
  linha onde a quantidade se muda.
- **Dentro de cada fornecedor o carro-chefe vem primeiro**, com selo e um fio dourado.
- **Linha do produto mais enxuta.** A tabela caiu de sete colunas para cinco: A caminho e
  Mínimo, o grupo, o giro de 90 dias, a conta da reposição, o movimento do ano e a última
  compra foram para "Por que este número", que nasce fechado. Nada foi apagado. A
  porcentagem do ideal só aparece quando o produto ainda tem peça: com zero na prateleira
  o selo "Está faltando" já diz tudo. No celular a lista ficou 13 mil pixels mais curta (de 72 mil para 58,5 mil).

## 1.39.1 — 22/10/2026

Pedido dele: *"verificar o que aconteceu, desconfiguou o sistema, mitigar e corrigir"*,
com o print da tela de início de 05/10 no lugar do sistema de hoje.

- **O que aconteceu.** O programa inteiro mora numa pasta só, `C:\cabana-sistema\app`,
  que o instalador apaga e copia de novo a cada atualização. Quem decide o que vai para lá
  é o `atualizar.ps1`, escolhendo um zip entre os que estiverem em `C:\instalacao` — e ele
  escolhia **o de data mais nova**. Data de arquivo mente: copiar um zip de uma pasta para
  outra, ou restaurá-lo de um backup, leva junto a data antiga, e aí o zip velho passa a
  parecer o mais novo. O script instala uma versão de semanas atrás, roda até o fim e
  escreve "Concluído", sem nada dizendo que o sistema andou para trás. É o mesmo defeito
  que em 06/10 fez três pacotes serem ignorados em silêncio, por outra porta.
- **A escolha passou a ser pelo número da versão no nome do arquivo**, e só em caso de
  empate pela data. Zip sem versão no nome vale 0.0.0 e nunca ganha de um pacote com nome
  certo. A comparação é numérica, então a 1.9.0 não passa mais na frente da 1.35.0.
- **Pacote mais antigo do que o que está no ar faz o script parar** antes de encostar em
  qualquer coisa, dizendo as duas versões e avisando que nada foi mexido. Vale nos dois
  caminhos: zip novo na pasta e repetição do pacote que já estava lá. A conferência
  acontece antes de trocar `C:\instalacao\pacote`, senão o pacote velho ficaria armado
  para a próxima execução. Voltar de propósito continua possível, com `-Voltar`.
- **Toda execução diz em voz alta a versão que está no ar e a que vai entrar**, para a
  troca errada aparecer na hora e não na loja, horas depois.
- Sete testes leem o script e travam cada uma dessas regras, em
  `apps/core/tests/test_atualizador.py`.
- O banco nunca foi afetado: migração do Django só anda para a frente, e a volta trocou
  apenas a pasta do programa. Nada aqui toca no SET.

## 1.39.0 — 22/10/2026

Pedido dele: *"controle inventario padrão aplicado no mercado varejo produtos de
artesanatos, utilizar as melhores praticas, estipular prazos de tempos em tempos realizar
o inventario. Precisamos organizar os produtos sem etiqueta, danificados, produtos muito
tempo parados. Fazer relatório comparando o que o set sistema apresenta e o que o nosso
sistema fez de leitura do inventario (...) planejar relatório de descartes de produtos sem
aproveitamento, planejar relatório de produtos para conserto/reparo, realizar
classificação desses produtos"*.

- **Contagem cíclica, que é o padrão do varejo.** Parar a loja para contar doze mil
  produtos é o que ninguém faz duas vezes. Agora cada produto tem um prazo, e o prazo sai
  da curva ABC: classe A a cada 30 dias, B a cada 90, C e produto sem venda a cada 180, e
  a contagem geral uma vez por ano. A tela Inventário abre com o plano — quantos produtos
  em cada classe, quantos estão em dia, quantos esperam e quanto vale ao custo o que está
  vencido. Hoje são 5.617 produtos com peça na prateleira, R$ 741 mil, e **nenhum deles
  jamais passou por uma contagem**.
- **A folha com que se anda pela loja.** Um botão abre a contagem já nomeada ("Contagem
  cíclica da classe A · 22/10") e outro gera a folha, em PDF ou planilha, com os 50
  produtos da frente: classe mais urgente primeiro e, dentro dela, o maior dinheiro na
  prateleira.
- **A classe do produto passou a ser UMA.** A curva ABC morava dentro do painel; agora
  mora em `apps/core/curva_abc.py` e as duas telas leem a mesma regra, com teste
  comparando as duas. Calculada só entre os produtos com estoque, ela faria o mesmo
  produto ser classe A no inventário e B no painel — o defeito que a 1.34.0 consertou
  entre o Painel e a Visão geral, de volta por outra porta.
- **A contagem passou a dizer COMO a peça foi achada**, além de quantas são: perfeita, sem
  etiqueta ou danificada. Dá para marcar na tela do computador e na da câmera, sem
  recarregar — quem está marcando "danificada" está com a outra mão segurando a peça.
- **A classificação é em dois tempos, e é a decisão desta versão.** Quem está na prateleira
  marca só "danificada". Na hora da contagem não se decide se uma luminária de vime
  descascada vale um conserto ou vai para o lixo, e obrigar a decidir ali faria a pessoa
  marcar o que for mais rápido. Quem decide é a gerência, na tela Organizar, com o custo da
  peça à vista. O servidor recusa descarte vindo da tela de contagem, não só esconde o
  botão.
- **Tela Organizar, nova, com cinco grupos:** danificadas a classificar, sem etiqueta, para
  conserto, para descarte e parados na prateleira. Cada uma com o que fazer escrito e o
  botão que faz. **Nada sai das listas sozinho**: sai quando alguém diz que a providência
  foi tomada, e isso fica na auditoria com o nome e a hora.
- **Parados**: produto com peça na prateleira e nenhuma unidade vendida há mais de 6 meses;
  a partir de 12 meses, ou nunca vendido, a linha sai em vermelho. Seis meses, e não três,
  porque abaixo disso ainda cabe estação — peça de Natal não vende em março. Só mercadoria
  de revenda entra: sem isso a lista traz o "CONSUMO PROPRIO - CESTO/PAPEL", que nunca
  vendeu porque nunca foi para vender.
- **Folha de etiquetas para reimprimir**, uma por peça que perdeu a sua, com o mesmo
  desenho de código de barras que a tela de consulta mostra e que o leitor da loja já lê.
  Um segundo desenho seria um segundo lugar onde a etiqueta pode sair errada, e etiqueta
  errada o leitor lê como OUTRO produto.
- **O SET contra a nossa leitura, com o laço fechado.** O relatório da divergência agora
  sai em PDF e em planilha, além do arquivo de texto de sempre. E o sistema passou a
  **conferir sozinho se o ajuste foi digitado no SET**: a importação lê o backup novo três
  vezes por dia e, na primeira depois da digitação, diz produto a produto se o saldo do SET
  virou o contado. São três respostas e não duas, porque a loja vendeu no meio: "entrou",
  "ainda não entrou" e "mudou, mas não para o contado" — este último o sistema não afirma,
  mostra e deixa para alguém olhar.
- **Quatro relatórios novos**, todos em PDF e em planilha, montados pela mesma função: o
  plano de contagem, o SET contra a contagem, o descarte (com a perda ao custo) e o
  conserto (com o valor que se recupera), mais a lista de parados.
- **Nada disto escreve no SET.** O acerto do saldo e a baixa do descarte são digitados lá
  por uma pessoa, porque é lá que o estoque vale, e porque o SET não permite integração —
  regra dele, de 05/10/2026.
- O vendedor não chega na tela Organizar nem nos relatórios: eles mostram custo e valor da
  peça. Há teste para isso.
- De borda: a tabela que vira cartão no celular passou a ter **uma** classe
  (`tabela-em-cartao`) em vez de três nomes repetidos em quinze seletores de CSS. A tabela
  nova que esquecesse um deles voltava a rolar de lado — calada, porque rolagem lateral não
  quebra teste nenhum. Agora um teste cobra o contrato.

## 1.38.0 — 21/10/2026

Pedido dele: *"sobre o modulo de inventario: usei smartphone samsung s24 fe para fazer teste
de utilização a câmera foi habilitada e nao leu nenhuma etiqueta de código de barras,
precisa ajustar melhor para fazer a leitura rápida para fazer sentido o modulo. Quando
digita o código reconhece o produto, porém é um método usado de forma escalável fica muito
demorado, por isso que precisamos que a câmera faça a leitura rápida"*.

- **A causa era o tamanho da imagem, e isso foi medido.** O sistema pedia à câmera
  1280 pixels de largura. A etiqueta da loja tem 95 barras e espaços em pouco mais de 2 cm:
  em 1280, com a etiqueta ocupando um quarto da tela, cada barra fica com menos de um pixel
  e meio, e depois da compressão do vídeo barra fina e espaço fino viram a mesma mancha.
  Nenhum leitor acerta isso. Trocando **só** 1280 por 1920 no código antigo, a etiqueta que
  nunca era lida em 15 segundos passou a ser lida em 0,0 s. A câmera agora é pedida em
  1920×1080.
- **O leitor do próprio aparelho passou a vir primeiro.** O Chrome do Android — que é o caso
  do S24 FE — tem leitor de barras embutido, em código nativo, muito mais rápido que o
  nosso. Quando existe, é ele que lê; o nosso (ZXing) fica como segundo, para o iPhone e
  para quem não tem. A tela escreve qual dos dois está valendo, numa linha, para o
  diagnóstico não depender de adivinhação.
- **A faixa branca da tela agora é exatamente o pedaço que o leitor analisa.** Eram dois
  retângulos diferentes: a pessoa mirava num lugar e o sistema lia outro, porque a conta não
  compensava o corte que a tela faz no vídeo. E o pedaço era reduzido antes de ser lido, o
  que jogava fora justamente os pixels que faltavam. A faixa também cresceu de 32% para 48%
  da altura, porque etiqueta de vaso não fica reta.
- **Foco contínuo, lanterna e aproximar.** O foco contínuo é pedido à câmera depois que a
  imagem começa, e é o que resolve o borrão de quem encosta o celular na etiqueta. A lanterna
  e o aproximar (2x) aparecem como botões só quando o aparelho os oferece.
- **A tela manda encostar.** Abaixo de mais ou menos um sexto da largura do quadro não existe
  pixel para as barras finas — é limite físico, não defeito. Então o recado mudou: "Encoste a
  câmera quase na etiqueta, até as barras preencherem a faixa branca de ponta a ponta."
- **Duas ferramentas novas para conferir isso de novo** (`docs/ferramentas/`): uma desenha a
  etiqueta de um produto real da loja em três distâncias, a outra abre a tela de verdade num
  navegador com câmera de mentira e cronometra a leitura. A tabela de antes e depois está em
  `docs/https-e-camera.md`.
- **Correção de borda**: no celular a página rolava 9 pixels para o lado em toda tela, não só
  na da câmera — o aviso de "endereço sem https" mostra o endereço inteiro como link e o
  endereço não quebra linha. Agora quebra.
- Digitar o código à mão continua na mesma tela, e o leitor de mão do balcão segue valendo.

## 1.37.0 — 20/10/2026

Pedido dele: *"nesse momento vamos focar na compra inteligente. Na tela pedidos, gerar
automaticamente pedidos de compra mercadorias por fornecedor, com a quantidade sugerida
pelo formula informada anteriormente aqui. No campo de quantidade sugerida, adicionar
quantidade manual, com a soma dois campos gera a quantidade total de cada produto por
fornecedor"*, com a fórmula da sugestão de compra em imagem.

- **A quantidade manual agora SOMA com a sugerida.** Cada linha da lista de compra mostra
  a conta: `sugerida + à mão = total`, com um campo só editável — o da mão. O total é o
  que vai no pedido, no PDF e no arquivo.
- **O que fica guardado é a PARCELA da mão, não o total.** É a diferença que só aparece
  três horas depois: quem acrescenta 5 unidades porque um cliente encomendou quer 5 a
  mais do que o sistema achar certo, e o sistema muda de ideia três vezes por dia, a cada
  sincronização. Com o total guardado, a conta andava de 10 para 14 e o pedido continuava
  saindo com os 15 pensados para outra situação. Com a parcela, vira 19 sozinho.
  Parcela negativa compra menos sem tirar o produto da lista.
- **"Não comprar agora" virou botão próprio.** Até aqui isso era digitar 0 no total; com a
  soma, zero deixou de querer dizer isso (menos dez só zera enquanto a sugestão for dez).
  O produto sai do pedido, continua na lista explicando o que o sistema pediu, e continua
  fora depois da sincronização. A migração converte sozinha o que já estava salvo.
- **Gerar os pedidos por fornecedor na tela de Pedidos.** Era preciso abrir a lista de
  compra, filtrar um fornecedor e clicar lá. Agora a tela de Pedidos abre com o que falta
  pedir hoje: um fornecedor por linha, com itens, unidades e valor, um botão por
  fornecedor e um para os que cabem no teto do mês. Cada pedido nasce com a folha em PDF
  anexada, como na lista de compra — é o mesmo serviço (`apps/pedidos/geracao.py`), porque
  pedido guardado com a folha de outro fornecedor é erro que só aparece quando a carga
  chega.
- **Nenhum pedido nasce sozinho.** "Automaticamente" aqui é o sistema montar tudo —
  fornecedor, linhas, quantidade e papel. O clique é de uma pessoa, e é a regra do próprio
  prompt dele: *"Não aprovar nem emitir pedidos automaticamente"*. O teto do mês entra como
  informação: o botão de gerar de uma vez só pega os que cabem, e quem passa do teto
  continua podendo ser pedido, um a um.
- **A fórmula dele conferida contra a que já roda.** `SC = max(0, ⌈VMD × (PE + IR) + ES −
  EP⌉)` é, letra por letra, a conta de `apps/compras/calculos.py`. A única diferença é que
  o sistema só compra quando a posição de estoque chega ao ponto de reposição. Medido na
  foto de 20/09/2026: hoje 2.237 linhas e **R$ 95.184,54**; sem o freio, 2.248 linhas e
  **R$ 95.307,15** — 11 linhas e R$ 122,61 a mais, todas de 1 unidade de produto cujo
  estoque já cobre o prazo do fornecedor. O freio ficou, e o número está escrito aqui
  porque a ETAPA 5 do prompt dele exige a comparação antes de trocar qualquer regra.
- Na trilha de auditoria o ajuste passou a guardar as duas parcelas, antes e depois.
- O arquivo da lista de compra ganhou a coluna "Quantidade a mais", ao lado do total e da
  sugestão.

## 1.36.0 — 20/10/2026

Pedido dele: *"Pedidos ao fornecedor = permitir editar pedido ou descartar/cancelar
(informar motivo). Pedido, nessa tela gerar pedido de compra de mercadorias"*, junto do
prompt "Otimização inteligente de compras e estoque" (14 seções).

O prompt manda abrir pelo diagnóstico, e foi o que esta versão fez: `docs/diagnostico-compra-inteligente.md`
responde seção por seção o que já atende, o que precisa de ajuste e o que não existe. O
que entrou aqui é o que ele pediu direto e o que era de baixo risco; o resto espera a
autorização dele, como o próprio prompt exige.

- **Editar o pedido ao fornecedor**, enquanto está aberto: muda a quantidade de qualquer
  linha, tira o item escrevendo 0, muda o prazo combinado e a observação que sai na folha.
  A folha nova é gerada e **anexada ao pedido**; a anterior continua guardada, porque o
  fornecedor pode já ter recebido a primeira. O custo não se edita: ele é a referência do
  dia e é contra ele que a nota é conferida. Um pedido não pode ficar sem nenhum item —
  desistir dele tem caminho próprio.
- **Cancelar o pedido com motivo obrigatório.** `Situacao.CANCELADO` existia desde a
  1.31.0 e nunca teve tela nem motivo: dava para um pedido estar cancelado no banco sem
  ninguém saber por quê. Nada é apagado — o pedido e os itens ficam, com o motivo, quem
  cancelou e quando, e o número não é reaproveitado. Pedido cancelado não se edita nem se
  marca como recebido.
- **Gerar o pedido de compra na tela do pedido.** É a MESMA folha da lista de compra
  (`apps/compras/pedido.py`), montada a partir do que está guardado e não da lista de
  hoje, que já mudou. `apps/pedidos/folha.py` veste o pedido guardado com o formato que a
  folha espera. A folha de um pedido cancelado sai avisando que foi cancelado, e por quê.
- **Vendas em 90 dias na lista de compra** (seção 6 do prompt). O número já vinha
  importado do SET e não chegava à tela. Vai comparado com o ritmo do ano — "1 em 90
  dias, acima do ritmo do ano (0,25 seria o normal)" —, porque o número cru não diz se é
  muito ou pouco. Diferença abaixo de um quinto é ruído de calendário e não vira frase.
- **Os cinco números da reposição, separados** (seção 4 do prompt). O sistema calculava
  estoque de segurança, ponto de reposição, disponível, estoque-alvo e quantidade, e a
  tela mostrava dois — a coluna "Mínimo" é o mínimo do SET, que é outra coisa. Agora a
  conta vai escrita na linha. Quando o estoque-alvo fica abaixo de uma unidade, a linha
  **cala**: quem decide ali é o arredondamento, e "estoque de segurança 0,0392" só faria
  o número parecer defeito.
- **A trilha de auditoria do ajuste de quantidade passou a guardar a justificativa e o
  número anterior** (seção 11 do prompt). Ela registrava a sugestão do sistema e o número
  novo; a pergunta de três meses depois é "quem mudou de 10 para 6, e por quê", e essa
  ela não respondia. O ajuste é sobrescrito a cada edição, então o valor anterior se
  perdia de vez.
- **A rolagem lateral no celular voltou a aparecer, e foi fechada na raiz.** Na tela do
  pedido o campo da quantidade saía da tela de 390px — o mesmo defeito da 1.30.0, por
  três causas somadas: a regra `input[type=text]` vence uma classe e o campo ficava com
  100% de largura; `td.numerico` vence `.celula-quantidade` e a célula não virava bloco;
  e, a mais escondida, o `<table>` continuava com `display: table` no modo cartão, o que
  faz o navegador criar uma célula anônima e impedir a tabela de encolher — a legenda
  "As 34 linhas do pedido" sozinha pedia 356px numa tela de 390. Agora a tabela, o corpo
  e a legenda viram bloco no celular, e isso vale para as três tabelas em cartão.
- Testes: 1.543 passando, com 28 novos só para editar, cancelar e gerar a folha.

## 1.35.1 — 19/10/2026

Pedido dele, no mesmo dia: *"sempre exibir o comando de atualizacao junto com o de
higienização"*.

- **Os dois comandos do servidor passaram a andar juntos**, nos três lugares em que
  aparecem: a tela Ficha técnica (Sistema · Base de processos), o `LEIA-ME.txt` que vai
  dentro do pacote e `docs/higienizacao.md`. Na tela ficam numa lista só, na ordem em
  que se usam: atualizar, conferir a limpeza, higienizar.
- Por que importa: quem abre o PowerShell no servidor faz as duas coisas na mesma visita.
  Um comando numa seção e o outro três parágrafos acima obriga a procurar justamente
  quem está com o servidor parado na frente.
- Virou **teste** (`test_os_dois_comandos_do_servidor_aparecem_juntos` e
  `test_o_leia_me_do_pacote_tambem_traz_os_dois`), senão a próxima edição de qualquer um
  dos dois textos separa os comandos outra vez sem ninguém notar.

## 1.35.0 — 19/10/2026

Pedido dele: *"o sistema está ficando com muitos menus, acaba dificultando o acesso e a
tomada de decisões rápidas (...) imagine os gestores em viagem, precisando tomar uma
decisão rápida para comprar, como se fosse uma bolsa de valores (...) Dados da Empresa,
definir um layout de formulário e inserir o logo (...) FINANCEIRO, permitir exportar além
do pdf para planilha de excel ajustado no mesmo layout (...) o sistema está trazendo
muitas informações, deixando os gestores confusos"*.

**O menu virou seis assuntos.** Eram vinte e sete telas em duas fileiras, todas à vista
ao mesmo tempo. Agora o topo tem **Visão geral · Compras · Vendas · Estoque · Dinheiro ·
Sistema**, e a segunda fileira mostra só as telas do assunto aberto: seis rótulos mais os
cinco ou seis do assunto em que a pessoa está, nunca os vinte e sete juntos. Nenhuma tela
foi apagada — as vinte e sete continuam lá, cada uma dentro do assunto a que pertence.

- **Clicar no assunto cai na tela que decide, não num índice.** "Compras" abre a Lista de
  compra; "Dinheiro" abre o Financeiro. Uma página intermediária que só oferece links
  custaria um clique a mais justamente a quem está com pressa.
- **Compras vem logo depois da Visão geral**, e a primeira tela dela é a Lista de compra,
  que é onde a quantidade é escolhida e o pedido sai. A ordem do menu é a da decisão.
- **Assunto sem nenhuma tela aberta some do topo.** O operador vendedor enxerga um
  assunto só, Estoque, com a Consulta dele, e por isso não recebe segunda fileira
  nenhuma. Mostrar "Dinheiro" a quem não abre nada de dinheiro é oferecer porta trancada.
- As setas de "anterior" e "próxima" do pé continuam lendo a mesma lista
  (`apps/core/menu.py`), então menu e setas não saem de sincronia. Detalhe em
  `docs/menu-por-assunto.md`.

**A tela Dados da empresa ganhou layout, logotipo e os dados de verdade.** Era uma coluna
de doze campos iguais, em que ninguém via que "endereço" era o da nota e não o da porta.

- O **timbre** abre a tela, desenhado igual ao papel: o logotipo da loja, o **nome
  fantasia em destaque** — é por ele que o fornecedor conhece a Cabana — e a razão social
  embaixo, que é o papel dela, aparecer na nota. Dá para conferir como o pedido vai sair
  sem gerar um pedido.
- O formulário virou **quatro blocos**: quem é a loja, endereço da nota, endereço da
  entrega e contato, com os campos **em duas colunas** no computador. Doze caixas de 640
  px empilhadas deixavam dois terços de um monitor de 1600 px vazios. Endereço, razão
  social, e-mail e recado continuam na largura inteira, porque não cabem em meia; no
  celular continua tudo em uma coluna.
- **A frase do bloco não se repete embaixo do campo.** "O endereço que consta no CNPJ"
  aparecia no alto do bloco e de novo sob o campo, com outras palavras. É exatamente a
  informação a mais de que ele reclamou.
- **Dois endereços, de propósito.** O CNPJ está na R. Claudionor Assis Dias, 171 e a loja
  fica no Largo dos Jesuítas, 64. O pedido trazia só o endereço da nota, então a carga ia
  parar no endereço fiscal — erro que só aparece no dia da entrega. Agora o papel diz
  **"Entregar em: ..."** numa linha própria, e só quando os dois são diferentes.
- **Tudo o que ele mandou já veio preenchido** (razão social, CNPJ, inscrição estadual,
  os dois endereços, telefone e e-mail), por migração que não passa por cima do que
  alguém tiver digitado na tela: só preenche campo em branco ou que ainda carregava o
  padrão antigo.
- De brinde, **a cidade da loja parou de ser pergunta**: os dois endereços são em Embu
  das Artes, então a previsão do tempo, que esperava alguém digitar a cidade desde a
  1.29.0, passa a funcionar sem ninguém abrir a tela.

**O financeiro exporta em planilha, ao lado do PDF.** Mesma lista, mesmo filtro, mesma
busca, mesmo layout — e **número de verdade na célula**: dinheiro soma, data ordena,
atraso ordena do mais vencido para o menos. Planilha em que o valor é o texto
"R$ 1.234,56" é um PDF mais feio.

- O relatório é montado **uma vez só** (`apps/financeiro/relatorio.py`) e sai nos dois
  formatos. Se fossem duas funções, começariam iguais e divergiriam na primeira correção,
  que é o defeito que a 1.34.0 consertou entre o Painel e a Visão geral.
- A tabela das contas vai com **cabeçalho congelado e filtro ligado**: na linha 400 ainda
  se sabe de que coluna é cada número.
- Escrita à mão, sem biblioteca nova, pelo mesmo motivo do PDF: o pacote é instalado sem
  internet e uma roda errada já custou uma versão inteira. Um `.xlsx` é um zip com seis
  XML dentro. Detalhe em `docs/relatorio-em-planilha.md`.
- Um defeito achado e corrigido no caminho: **a cor ganhava do formato na mesma célula**.
  O atraso vermelho saía como texto, e uma conta vermelha de dinheiro teria saído como
  1234.56 em vez de R$ 1.234,56 — ou seja, a coluna não ordenaria justamente na lista de
  vencidas, que é a primeira que alguém ordena.

**Menos informação no caminho de quem decide.** Na Lista de compra, "Como esta lista é
feita" ficava ENTRE o cartão que diz por onde começar e a lista em si: trinta linhas de
regra atravessadas por quem abriu a tela para comprar. Desceu para o fim e nasce fechada.
O texto continua inteiro — recolher não é apagar. O título leva uma seta e uma linha
dizendo o que tem dentro ("a conta, o prazo do fornecedor e o teto do mês"), senão o
bloco fechado parece um cartão vazio e ninguém descobre que abre.

Cada coisa acima entrou com teste próprio: a suíte foi de 1.452 para **1.497 testes**,
todos passando. Prints no computador e no celular em
`implantacao/prints-1.35.0/`.

## 1.34.0 — 15/10/2026

Pedido dele: *"login para acessar o sistema está um pouco lento / fazer uma revisao geral
no codigo e na logica, mitigar problemas e corrigi-los / usar skill para correções de
bugs"*.

**O login.** Medido de ponta a ponta antes de mexer em qualquer coisa. A senha custava
0,31 s e não era o problema; o problema era a tela de abertura, que é a primeira coisa que
aparece depois de entrar: dois segundos e meio e 103 consultas. As três contas da abertura ficam
em cache, e a chave do cache carrega o número da importação, então **cada sincronização
derrubava o cache de propósito e a conta de dois segundos sobrava para a primeira pessoa
que abrisse o sistema** — três sincronizações por dia, três pessoas pagando a conta.

- **O cache saiu da memória e foi para um arquivo em `dados\cache`.** Quem importa é a
  tarefa `CabanaImportacao`; quem mostra a tela é o serviço `CabanaSistema`. São dois
  processos: com o cache na memória de cada um, a conta feita pela tarefa nunca chegava ao
  serviço, e por isso adiantar a conta na importação não teria resolvido nada.
- **A importação passou a adiantar as contas da abertura.** A conta tem que ser feita de
  qualquer jeito; a escolha é só sobre QUEM espera — a tarefa agendada, que já está
  rodando e não tem pressa, ou a pessoa, que acabou de digitar a senha. Agora é a tarefa.
  Vale também quando não há backup novo: a foto anterior continua valendo, e é dela que a
  tela sai.
- **A tarefa de hora em hora refaz a conta do dia.** A chave carrega o dia, porque a
  Visão geral conta conta vencida e conta a vencer, e isso vira à meia-noite sem ninguém
  tocar em nada. Sem isso, quem abrisse o sistema antes da sincronização das 08:30 pagava
  a conta inteira.
- **A senha ficou como está, de propósito.** O embaralhamento da senha custa 0,31 s porque
  são um milhão de voltas, que é o padrão do Django 5.2. Baixar para 600 mil (o mínimo que
  a OWASP recomenda) economizaria 0,12 s e trocaria a senha de todo mundo de formato numa
  máquina que não dá para acompanhar daqui. Não vale.
- Resultado medido sobre a foto de verdade da loja, com os 11.274 produtos: a abertura
  caiu de **103 consultas para 38**, e o login inteiro de cerca de 2,5 s para meio segundo.
  A contagem de consultas é o número firme; o tempo varia com a carga da máquina, e no
  servidor da loja vai ser outro.
- De passagem, o túnel do HTTPS parou de esperar o pacote seguinte antes de repassar o que
  já tem (Nagle), que custava até 40 ms por ida e volta no celular.

**A revisão geral.** Rodada com a skill de correção de bugs sobre os módulos onde a
decisão de compra e de dinheiro acontece. Quinze achados, todos conferidos linha a linha
antes de mexer, mais um décimo sexto que apareceu na conferência dos prints, e cada
correção com teste próprio: a suíte foi de 1.395 para 1.452 testes. O que estava errado:

- **O pedido ao fornecedor saía com outra quantidade que a da tela.** A tela deixa escolher
  de que período sai a média de venda; os dois botões de gerar o pedido levavam no endereço
  o fornecedor e a situação, e não a janela. Filtrava-se por 30 dias, lia-se COMPRAR 4 na
  linha, clicava-se, e saía uma folha de doze meses dizendo COMPRAR 1 — e, desde a 1.31.0,
  esse clique não é só uma folha: é pedido gravado com a folha errada anexada. Produto que
  só entra na lista pela janela curta nem aparecia na folha, e o botão dava erro.
- **A estação estava sendo contada duas vezes.** O fator do ano passado conserta UMA
  distorção: a média de doze meses é plana e não sabe de estação. Quando a média já sai de
  uma janela curta, ela JÁ É a venda da estação de agora, e o fator entrava em cima —
  com o teto de 2, até o dobro de unidades pedidas ao fornecedor no mês de pico. Agora ele
  só entra onde a base é plana.
- **A conciliação amarrava duas saídas do banco na mesma conta do SET.** Duas saídas iguais
  com uma conta só apareciam as duas como "uma conta bate", o botão de conferir as óbvias
  marcava as duas, o resumo somava o mesmo dinheiro duas vezes e a tela declarava o extrato
  inteiro conferido — enquanto uma retirada de verdade não tinha lançamento nenhum no SET,
  que é exatamente o que a conciliação existe para encontrar.
- **Conta em aberto sem data de vencimento no SET ficava fora do comprometido.** "Venceu" e
  "vai vencer" são os dois lados de uma comparação com hoje, e comparação com data vazia
  não dá verdadeiro nem falso: a conta não entrava em nenhum dos dois. A loja devia mais do
  que o sistema dizia, e o teto de compra de "Antes de comprar", que desconta o compromisso
  do caixa, aparecia maior do que é. Agora existe a fatia "Sem data no SET", que só aparece
  quando existe.
- **Uma importação boa podia virar loja sem dado nenhum.** Depois de a foto estar gravada e
  commitada, a execução seguia DENTRO do mesmo `try` para escrever a auditoria e podar as
  fotos antigas — e o `except` desse `try` apaga a foto e marca a importação como falha. Um
  tempo esgotado na poda, que é um DELETE em massa sobre oito tabelas, apagava a foto nova;
  e, como a poda já havia tirado as anteriores, a loja ficava sem nada. O desfazer também
  esquecia quatro tabelas, que ficavam penduradas até a poda seguinte.
- **O Painel discordava das outras telas no mesmo número.** O consumo próprio da loja e o
  DIVERSOS do balcão não são compra que alguém decida, e todas as telas de compra os tiram
  da conta. O Painel não tirava: o "Dinheiro parado sem venda em 12 meses" dele dava cerca
  de R$ 4,9 mil a mais que a tarefa "Pôr para girar o que está parado", na mesma tela de
  abertura e com a mesma definição. Os dois números de loja inteira do alto — produtos
  cadastrados e valor em estoque — continuam inteiros, que ali é o certo.
- **O caixa esquecido não era apontado quando o turno virava a noite.** A data da abertura
  saía do campo gravado em UTC, e em São Paulo todo turno aberto das 21h em diante cai no
  dia seguinte em UTC: o caixa aberto às 21:30 e esquecido a noite inteira aparecia como
  aberto "hoje" e nunca era apontado — justamente o turno que mais engole a venda do dia
  seguinte. A tela também prometia "mais de 24 horas" sobre uma conta que só sabe de dias,
  e agora diz o que conta.
- **A tela de Despesas tinha duas janelas diferentes chamadas de doze meses.** "Para onde o
  dinheiro foi" contava 30 dias por mês (360) e o mês a mês contava 31 (372): somar uma
  coluna e conferir com a outra deixava doze dias de pagamento de diferença, sem causa
  visível. As duas começavam no meio de um mês, então o mês mais antigo entrava com um
  terço dos dias. Agora as três consultas da tela começam no mesmo dia 1º.
- **A "despesa média por mês" era maior do que a realidade.** O divisor era a quantidade de
  meses que TIVERAM pagamento, e mês em que a loja não pagou nada simplesmente não existia
  como chave: ele saía do divisor e empurrava a média para cima. Agora o divisor é mês de
  calendário.
- **O prazo impresso no pedido era o da primeira linha do bloco.** Sem prazo na ficha do
  fornecedor, cada produto cai no prazo medido no SET, que varia de produto para produto; o
  bloco copiava o da primeira linha iterada. Um fornecedor cuja primeira linha mediu 3 dias
  e as outras 21 saía com "Prazo de entrega: 3 dias" na folha. Agora é o maior prazo do
  bloco, porque o pedido só está completo quando a última caixa chega.
- **"Antes de comprar" afirmava uma régua que não usa.** O veredito da ruptura dizia "está
  zerado e vendeu nos últimos 90 dias", mas a conta daquela tela é sobre os doze meses:
  produto que vendeu duas unidades em novembro e está zerado desde então recebia essa
  frase, que é a única coisa que a pessoa lê antes de comprar.
- **Data impossível no pagamento previsto derrubava a tela.** A data ia crua para o campo
  do banco; qualquer coisa que não fosse o que o calendário do navegador escreve estourava
  na gravação, num formulário de dinheiro que já tem recado pronto para todo o resto. De
  brinde, agora aceita a data escrita como gente escreve.
- **A lista de compra montava a tela "Antes de comprar" inteira para ler um número.** Ela e
  o pedido chamavam a função que traz os onze mil produtos para a memória e monta a tabela
  de todos os fornecedores, para jogar tudo fora menos o teto do mês — duas varreduras de
  onze mil linhas em Python na tela mais pesada do sistema, e a mesma conta ainda estava
  dentro da tela de abertura. Agora o teto sai do banco em uma consulta de soma.
- **E a contagem do dinheiro parado também passou a bater.** Produto sem custo cadastrado
  somava zero reais e mesmo assim era contado: nos dados da loja, o Painel dizia "1.490
  produtos" e a tarefa da Visão geral dizia "1.443 produtos", para os mesmos R$ 227 mil.
  Agora os dois dizem 1.443, e quantos são os produtos sem custo a tela já diz na linha
  embaixo dos números.
- A tarja "Está faltando" continua sendo sobre o ano, e agora está escrito por quê: ela é a
  resposta a "esta prateleira está vazia?", e trocá-la junto com o filtro faria a mesma
  prateleira vazia aparecer e desaparecer da tarefa urgente da abertura conforme o período
  escolhido.

## 1.33.1 — 14/10/2026

Pedido dele: *"revisar github / usuário: e-fonseca / conectar e ativar automaticamente /
tornar um processo automático sem ação humana"*, com a foto do repositório
`e-fonseca/sistema` vazio na tela.

- **O primeiro envio de todos não funcionava, e é o único que todo mundo faz.** Um
  repositório recém-criado não tem commit nenhum, e nesse estado o GitHub responde
  **409 "Git Repository is empty."** à pergunta "em que commit está o ramo main?". O
  sistema esperava 404 ali, tratava o 409 como erro e parava com o recado *"o
  repositório está vazio ou o ramo mudou; tente de novo"* — e tentar de novo dava no
  mesmo, para sempre. Medido contra a API de verdade, no repositório dele, em
  14/10/2026. Agora a LEITURA entende os dois jeitos de o GitHub dizer "ainda não há
  nada aqui"; escrever em repositório vazio sempre funcionou, então um 409 vindo de uma
  escrita continua sendo erro de verdade, que é o ramo ter se mexido no meio do envio.
- **O motivo do erro não se perde mais.** O corpo de uma resposta de erro é um fluxo:
  quem lê primeiro leva tudo. Como o 409 passou a ser olhado duas vezes — para saber se
  é repositório vazio e para virar frase na tela —, a segunda leitura vinha vazia e a
  tela mostraria um erro sem motivo nenhum. A leitura agora fica guardada.
- **Ramo parecido não vale pelo ramo pedido.** Pedindo `main`, o GitHub pode responder
  com a LISTA dos ramos parecidos em vez de um só; o sistema lia isso como se fosse a
  resposta e quebrava. Agora nenhum deles passa pelo que foi pedido.
- **A tela parou de afirmar o que não sabe.** Sem token, ela dizia que o código "só
  existe no servidor da loja: se o computador queimar, não há cópia em nenhum outro
  lugar". O sistema não tem como saber isso — o repositório pode ter sido enchido de
  fora. Agora ela diz o que de fato sabe: que ESTE servidor não está mandando nada.
- **Ligar virou UM passo: colar o token e gravar.** Eram três — colar, marcar *mandar a
  cada atualização* e clicar em *Enviar agora* —, e entre o primeiro e os outros a tela
  ficava dizendo que estava tudo preenchido e que nada tinha subido, esperando alguém
  achar o botão. Agora a marca já nasce marcada e gravar manda a primeira cópia na hora,
  com o resultado na própria tela. Só a primeira: trocar o token de um backup que já
  funciona não reenvia o sistema inteiro. Se o GitHub recusar o token, o que foi gravado
  FICA gravado e o motivo aparece na tela — perder a configuração por causa de um token
  errado obrigaria a digitar tudo de novo.

## 1.33.0 — 14/10/2026

Pedido dele: *"a questão da sugestão inteligente ainda nao ficou clara e nem ficou boa pra
mim (...) exiba uma sugestão de compra analisando o que foi comprado de um determinado
produto e o que foi vendido e o resultado que seria o estoque (...) faça analise do periodo
definido no filtro e usar a media de vendas nesse mesmo período"*, mais *"acessar de forma
automática o github, sem ação humana"*.

- **A sugestão estava inflada em R$ 89 mil, e isto é o conserto mais importante da
  versão.** São 1.023 produtos com saldo abaixo de zero no SET, porque a loja nunca fez
  contagem física: saíram unidades que nunca foram registradas entrando. A conta somava
  esse buraco à compra, como se fosse mercadoria a repor — e as vendas que abriram o
  buraco já estão na média, ou seja, já estão na demanda. Era comprar a mesma venda duas
  vezes. Na cópia de 20/09/2026 a lista inteira caiu de **R$ 184.577 para R$ 95.459**, e
  casos como o PRATO G MARAJOARA, que vende 1 por ano, deixaram de pedir 16 unidades —
  dezesseis anos de venda numa compra só. A cobertura em dias e o valor de estoque já
  usavam o piso de zero; a compra era a única das três que não usava, e a única que vira
  pedido ao fornecedor. A situação continua "Em falta" e a coluna TEM continua mostrando
  -69: esconder o número não conserta o cadastro.
- **Cada linha passou a explicar o próprio número.** "Em 12 meses comprou 50 e vendeu 360:
  o estoque caiu 310, de 290 para -20." E, quando houve compra: "Última compra: 9 em
  02/10/2025, há 11 meses; vendeu 9 desde então, e já saiu tudo." Antes a linha mostrava
  TEM, A CAMINHO, MÍNIMO e COMPRAR, e nenhum desses números explicava o outro — era disso
  que ele estava reclamando. Onde o saldo é negativo, a linha diz também que a compra conta
  zero, senão TEM -69 e COMPRAR 1 na mesma linha não fecham.
- **A média de venda agora sai do período escolhido na tela.** Filtro novo, "Média de venda
  de": 12 meses, 6 meses, 3 meses ou 30 dias. O divisor é dia de porta ABERTA e não dia de
  calendário. Produto que não vendeu nada no período volta para os doze meses e a linha
  dele avisa: zerar a sugestão faria ele sumir da lista, que é justamente o produto que
  some da prateleira sem ninguém notar. A janela escolhida é dita uma vez, embaixo do
  filtro, com quantas linhas voltaram — e não em cada linha, que seria ruído.
- **Agora cada quantidade diz quanto tempo ela dura e quanto dinheiro prende.** "Cobre 2
  meses de venda e prende R$ 56,00", embaixo do campo. Fala da quantidade DO PEDIDO: quem
  digita 70 lê "cobre 5,8 anos e prende R$ 1.960,00" e muda de ideia sozinho. Acima de um
  ano a frase sai em âmbar. O sistema avisa; travar quem decide, não.
- **O backup no GitHub passou a se reenviar sozinho.** Se a última cópia que chegou lá tem
  mais de uma semana, o sistema tenta de novo por conta própria, na tarefa que já acorda de
  hora em hora. Isso cobre a atualização que falhou no meio e o mês sem atualização
  nenhuma. Uma tentativa por dia, no máximo.
- **E avisa dez dias antes de o token vencer.** O sistema lê a validade do token na própria
  resposta do GitHub, uma vez por dia, e vira aviso na tela e alerta por e-mail e Telegram.
  A rotina é diária e **calada quando está tudo bem**: aviso que chega todo dia deixa de
  ser aviso. O que não dá para automatizar é a autorização — o GitHub exige que uma pessoa
  dê a permissão, e é isso que impede um programa de escrever na conta de alguém sozinho.
  A tela diz isso com essas palavras, e o link dela já vai direto para a página de gerar o
  token.
- **Conserto de tela:** uma instrução do modelo da página quebrada em duas linhas fazia a
  lista de compra mostrar o código-fonte escrito na tela, no meio da frase do estoque. O
  Django não reconhece instrução que atravessa fim de linha, e isso não dá erro nenhum —
  virou teste, ao lado do que já travava comentário aberto em duas linhas.

## 1.32.0 — 14/10/2026

Dois pedidos dele: *"fazer conexão com o diretório sistema, destinado para este projeto no
github"* e *"preciso saber a quantidade que o sistema inteligente sugeriu para comprar,
avaliando o período vigente do pedido atual com o mesmo período do ano anterior"*.

- **O ano passado entrou na conta da sugestão.** A quantidade sugerida nascia de uma média
  plana — venda de doze meses dividida por dias —, e a loja vende por estação: assim a
  conta manda comprar de menos antes de a estação começar e de mais depois que ela passou.
  Agora o sistema pergunta quanto o produto vendeu, um ano atrás, nos **mesmos dias do
  calendário que este pedido vai cobrir** (prazo do fornecedor mais a próxima compra e a
  segurança), compara com a média dele no ano e ajusta a quantidade por aí.
- **Com freio, porque fator errado vira pedido errado.** Produto que vendeu menos de seis
  unidades no ano fica de fora, e também o que normalmente venderia menos de duas na
  janela — o zero dele é o tamanho da amostra, não a estação. Diferença menor que um
  décimo não conta, e o ajuste nunca passa do dobro nem desce da metade. Nos dados de
  20/09/2026, 26 das 2.237 linhas mudam, metade para cima e metade para baixo.
- **A sugestão passou a estar escrita com o nome dela.** Embaixo do campo, em toda linha:
  "sugestão do sistema: 43". Número solto dentro de um campo não diz de quem é. Quando o
  ano passado mexeu, vem a explicação junto, com a MUDANÇA na frente do motivo: "de 36
  para 43: no ano passado este período vendeu 1,2x a média do produto". O fator sozinho
  promete mais do que entrega quando o estoque está muito negativo, porque aí o grosso da
  compra é tapar o buraco e a estação mexe só no resto. O campo continua editável.
- **A cobertura e o excesso não mudaram.** Continuam saindo da média dos doze meses: dizer
  que um produto de verão está "em excesso" em julho porque a demanda ajustada caiu seria
  trocar informação por palpite.
- **A tela Backup já vem com o repositório dele preenchido**
  (`e-fonseca/sistema`), como a tela de Alertas já vem com o servidor de e-mail. Só falta
  colar o token, que é dele e não pode vir escrito no programa. O passo a passo da tela
  mudou junto: o primeiro passo não é mais criar o repositório, é conferir o que está lá.
- **Conserto de tela, no celular.** A explicação da estação é uma frase, e ela mora na
  célula da quantidade, que é `nowrap` para os números não quebrarem: saía numa linha só,
  esticava a tabela para 557 px num visor de 390 e era cortada no meio. Junto apareceu um
  defeito mais velho — o cartão do celular desligava a rolagem lateral só no eixo X, e
  pelo CSS "visível de um lado e recortado do outro" não existe, então ela voltava a
  valer. As duas coisas viraram teste (`CartaoNoCelular`).

## 1.31.0 — 14/10/2026

Três pedidos dele: *"nos novos pedidos permitir anexar arquivo dos pedidos e/ou romaneios
e nota fiscal para os fornecedores ou artesões que consegue fazer emissão, para controle
futuros e fazer com o sistema faça a leitura de todo o conteúdo do arquivo também para
checar se as informações estão corretas"*, *"FORNECEDORES = campo de pesquisas com recurso
de auto complete"* e *"BACKUP = criar rotina de backup no github, conectar automatico a
cada atualizacao"*.

- **O pedido ao fornecedor virou registro.** Até agora ele era só um PDF que saía e
  acabava ali. A lista de compra é refeita três vezes ao dia, então uma semana depois não
  havia como saber o que tinha sido pedido. Agora o botão "Gerar o pedido" **grava** o
  pedido — numerado, por fornecedor, com as linhas congeladas: quantidade, custo de
  referência e código de barras de cada item — e anexa a ele a própria folha que foi para
  o fornecedor. Tela nova em Compras > Pedidos. Reabrir o PDF pelo link só reimprime, e
  gerar duas vezes no mesmo dia com as mesmas linhas reaproveita o pedido em vez de
  duplicar.
- **Os documentos que voltam ficam no pedido.** Cada pedido aceita quantos arquivos vierem,
  classificados em pedido, romaneio, nota fiscal ou outro: XML, PDF, foto, CSV ou TXT. O
  arquivo é guardado com nome calculado, nunca com o nome que veio de fora, fica em
  `dados\anexos`, e o mesmo arquivo não entra duas vezes. A assinatura do arquivo é
  conferida, não a extensão.
- **A nota fiscal é conferida item a item.** Do **XML** da NF-e o sistema lê cada item em
  campo próprio e monta a conferência: linha por linha, o que veio contra o que foi pedido,
  com a frase do que está errado — *veio sem ter sido pedido*, *pedido e não veio*, *veio
  mais*, *veio menos*, *quantidade certa, preço acima da referência*, *confere* — e o total
  da nota contra o total do pedido. Romaneio em CSV ou TXT também é lido, pelos nomes das
  colunas. O preço só reclama passando de 2% do custo de referência.
- **O casamento das linhas é pelo código de barras.** Na nota, o código do produto é o do
  **fornecedor**, não o da loja. Então a ponte é, em ordem: código de barras, código do
  produto e, por último, a descrição reduzida ao que distingue — e essa última sai marcada
  "pela descrição (confira)", porque é palpite fundamentado. Descrição repetida dentro do
  pedido fica fora do casamento por nome: entre dois candidatos iguais, errar em silêncio é
  pior que não casar.
- **Do PDF e da foto, o sistema guarda e diz que guardou.** O PDF da nota (o DANFE) é o
  *retrato* dela: o conteúdo não está em campo nenhum, são posições de texto numa página, e
  o que se tira dali é adivinhação. Em tela que confere dinheiro, adivinhação é pior que
  nada. Então o arquivo fica guardado e à vista, com a explicação, e vale pedir ao
  fornecedor o XML — é o mesmo arquivo que a contabilidade já recebe.
- **Fornecedores com busca e autocomplete.** Um campo de procurar que sugere enquanto se
  digita, sem acento e ordenado por quem a loja mais compra: nome que começa com o que foi
  digitado vem antes de palavra que começa com ele, que vem antes de achar no meio, e entre
  iguais vem primeiro quem tem mais compra em doze meses. Cada sugestão traz quanto foi
  comprado e quantos produtos. Como no resto do sistema, a busca é nossa, roda no servidor
  da loja e não manda nada para fora.
- **Backup do código no GitHub.** Tela nova em Apoio > Backup: cola-se o repositório
  **privado** e um token, e no fim de **cada atualização** o código recém-instalado sobe
  sozinho. Sobe só código; o banco **não vai** e nem poderia — tem nome de cliente vindo do
  SET, extrato bancário e nota de fornecedor dentro. O envio fala direto com a API do
  GitHub, sem precisar de git instalado no servidor, e calcula o mesmo SHA-1 que o git
  calcularia para mandar só o que mudou. O token fica cifrado, nunca volta para a tela e
  nunca entra na auditoria. Falhar o envio não derruba a atualização: o sistema já está no
  ar e o motivo aparece na tela.
- **Conserto na lista de atrasados.** A sugestão da busca do contas a pagar escrevia
  "código atrasados" embaixo do nome, porque a linha de ajuda era a mesma do produto. Agora
  cada tela diz o que tem a dizer na sugestão.

## 1.30.0 — 14/10/2026

Dois pedidos dele, no mesmo dia da 1.29.0: *"comparação, aumentar os filtros, permitir
edição por período e trazer outro comparativo de vendas do mesmo período dos anos
anteriores"* e *"na sugestão inteligente de compra, não está aparecendo a quantidade
como foi pedido anteriormente e também precisa ser um campo editável"*.

- **A quantidade sumia no celular.** O campo existe desde a 1.28.0, mas a tabela da lista
  de compra tem sete colunas e rolava de lado: num visor de 390 px apareciam o nome do
  produto e um pedaço da situação, e a coluna "Comprar" ficava fora da tela, atrás de uma
  rolagem lateral que ninguém descobre. Agora, no estreito, cada linha vira um cartão —
  nome, situação, "tem / a caminho / mínimo" numa linha, o campo da quantidade com o botão
  Salvar e o custo —, e o rótulo de cada número vem escrito ao lado dele. No computador
  nada muda.
- **Comparação com mais filtro e período escolhido a dedo.** O quadro da lista de compra
  ganhou o filtro por grupo de produto, e as duas telas ganharam dois campos, *De* e *Até*,
  com todo mês fechado que a foto guarda. São dois caminhos, cada um com o seu botão:
  "Comparar" usa o período pronto, "Ver estes meses" usa os meses escolhidos.
- **O mesmo período, ano a ano.** Uma linha por ano, do mais novo para o mais velho, com as
  unidades e a variação em relação ao ano anterior — para separar "caiu este ano" de "vem
  caindo há três anos". Nos dados de 20/09/2026, junho a agosto rendeu R$ 464.503,85 em
  2026, R$ 439.705,05 em 2025, R$ 425.658,28 em 2024, R$ 289.580,10 em 2023 e R$ 138.512,90
  em 2022.
- **Cinco anos de venda mês a mês, e o mês pela metade.** A leitura do SET pegava 730 dias
  contados do dia do corte, e essa data cai no meio de um mês: o mês mais antigo da foto
  era meio mês, e a comparação de 12 meses o usava como mês inteiro — comparava outubro
  cheio com meio outubro e acusava crescimento que não existe. Agora a leitura começa no
  dia 1º, são 61 meses, e a foto grava onde o histórico começa (`Importacao.mes_a_mes_desde`,
  migração 0012). Período cujo ano anterior não cabe inteiro na foto não é comparado: a
  tela explica, em vez de mostrar número errado. A sincronização ficou ~2 segundos mais
  longa e a foto passou de ~27 mil para ~56 mil linhas de venda mensal.
- 1.154 testes.

## 1.29.0 — 14/10/2026

Duas telas saíram do menu e viraram recurso da tela onde a decisão é tomada, a pedido do
Edson: *"remover do menu COMPARAR COM O ANO PASSADO, virar recurso dentro da sugestão de
compra mercadoria. remover do menu TEMPO E VENDA. virar recurso dentro de visão geral,
configurar api de previsão do tempo automática, armazenar informações diárias e usar como
indicador."*

Menu de dezesseis linhas não é menu, e número só muda decisão se estiver à vista na hora
de decidir. Nenhuma das duas telas foi apagada: o que mudou é por onde se chega a elas.

- **Comparar com o ano passado virou quadro da Lista de compra** (`#ano-passado`). Traz o
  período (3, 6 ou 12 meses fechados) contra os mesmos meses do ano anterior, os que mais
  subiram, os que mais caíram, e o botão para a tabela produto a produto. **Herda o
  fornecedor filtrado na tela**: filtrando um fornecedor, a comparação é dele. O
  fornecedor que vale é o PEDIDO na tela, e não o que a lista validou — a lista só conhece
  quem tem produto abaixo do ponto de pedido, e comparar a loja inteira numa tela que diz
  estar filtrada seria um número certo no lugar errado.
- **O tempo virou o quadro "O tempo e a venda" da Visão geral**, e é o único indicador
  daquela tela que olha para frente: lidera com o **próximo fim de semana** — que é quando
  a loja fatura — e põe ao lado quanto um fim de semana de chuva custa, medido nos dias
  guardados. Chuva de terça não pinta o quadro de vermelho, e numa janela que pega dois
  fins de semana vale o próximo, não o de seis dias à frente.
- **A busca do tempo passou a se configurar sozinha.** Até a 1.28.0 ligá-la exigia
  latitude e longitude digitadas à mão, pegas no Google Maps: dois números de seis casas
  decimais para a função começar a existir, e por isso ela não começou. Agora basta **o
  nome da cidade** — `apps/tempo/lugar.py` pergunta as coordenadas ao serviço de geografia
  do próprio Open-Meteo, escolhe a cidade brasileira de maior população e **escreve na tela
  o lugar que entendeu** ("Sorocaba, São Paulo, Brasil"), para ninguém buscar o tempo da
  cidade homônima de outro estado sem perceber. Salvar faz o caminho inteiro de uma vez:
  descobre o lugar, busca o tempo e diz o que achou. A busca nasce ligada, e enquanto a
  cidade estiver em branco a tarefa da madrugada não faz nada e termina em paz, sem marcar
  tarefa quebrada no Windows.
- **A busca passou a trazer a previsão** dos próximos sete dias, além dos dias fechados.
  Dia previsto fica **marcado como previsão e não entra em conta nenhuma**: a medida de
  quanto a chuva custa é só de dia que já fechou, porque média de palpite pareceria medida
  e não é. O dia de hoje também nasce marcado — às 06:10 a chuva da tarde ainda é palpite —
  e a busca do dia seguinte o devolve fechado, apagando a marca. Quem anota o dia na tela
  apaga a marca também, porque viu pela janela.
- **Tela que é recurso de outra deixou de ser parada do vaivém.** `menu.Item` ganhou
  `dentro_de`: quem abre uma delas recebe a seta "anterior" apontando para a tela de
  origem, e as setas das outras telas não passam mais por elas — senão a seta de "próxima"
  viraria o menu que acabou de ser tirado.

Também entrou uma **trava contra teste que fala com a internet**: três partes do sistema
saem para fora (o tempo, a cidade e o Telegram) e todas recebem a função de abrir a
conexão por parâmetro, justamente para o teste passar uma de mentira. Quem esquecer agora
recebe um erro na hora, em vez de um teste que passa na máquina de quem tem internet e
falha na do servidor (`config/settings/test.py`).

1.133 testes, contra 1.086 da 1.28.0.

## 1.28.0 — 14/10/2026

Sete pedidos do Edson de uma vez, sobre comprar melhor, conhecer o fornecedor e entender
o clima. Seis viraram tela; o sétimo é decisão de negócio e virou estudo.

- **O campo de procurar passou a achar sem acento e a pôr o certo em cima.** O pedido foi
  "utilizar a melhor tecnologia de auto completar", com Algolia, Luigi's Box e Google Cloud
  Retail anexados. Os três foram **recusados, e vale registrar por quê**: são serviços de
  nuvem — mandariam o nome do produto, do fornecedor e do cliente para fora do servidor da
  loja, exigiriam internet no instante em que a pessoa digita cada letra e cobram por busca.
  Numa loja com 11.274 produtos, o que falta não é tamanho de motor, é **ordem**: quem
  digita "cad" quer CADEIRA e recebia BANCO PORTA-CADERNO primeiro, em ordem alfabética.
  Agora a busca tira o acento nos dois sentidos ("quiteria" acha QUITÉRIA), põe na frente o
  que **começa** com o digitado, depois o que começa uma palavra no meio, e desempata por
  **quem vende** — entre dois parecidos, o que saiu da prateleira no ano aparece primeiro.
  Roda no PostgreSQL da própria loja, numa consulta (`apps/core/procura.py`). `pg_trgm`, que
  daria tolerância a erro de digitação, ficou de fora porque `CREATE EXTENSION` exige
  superusuário e o papel do sistema não é.
- **A quantidade da sugestão de compra passou a ser editável, sem perder a sugestão.** Cada
  linha da lista tem o campo aberto com a sugestão dentro, e a sugestão continua escrita
  embaixo ("o sistema sugeriu 14"), porque é ela que explica o número. O que a loja digita é
  **da loja**: fica preso ao código do produto, não à importação, e sobrevive às três
  sincronizações do dia — pendurado na foto, o número digitado às 08:00 morreria às 08:30.
  Digitar exatamente a sugestão apaga o ajuste, senão o contador de "mudadas à mão"
  mentiria; zero é resposta válida ("não comprar agora") e tira o item do pedido sem tirar
  da tela. Quando a sugestão muda depois do ajuste, a linha avisa que o sistema agora sugere
  outro número, sem mexer no que a pessoa escolheu
  ([lista-de-compra.md](lista-de-compra.md)).
- **Botão que gera o pedido para o fornecedor, em papel timbrado.** Um pedido por
  fornecedor, com o timbre da Cabana do Jacarandá, a razão social Essenza e o endereço
  Largo do Jesuítas, 64; cada fornecedor numa página, para a folha poder ser separada; só
  linha com quantidade maior que zero; quantidade mudada à mão sai em marrom, para quem
  assina ver o que não é sugestão do sistema. Sai do `apps/core/pdf.py` escrito à mão, sem
  biblioteca. O CNPJ, a cidade, o CEP e o telefone ficam numa tela nova (**Dados da
  empresa**), não no código: timbre digitado no código envelhece sem avisar.
- **Tela nova: comparar com o mesmo período do ano passado.** 3, 6 ou 12 meses contra os
  mesmos meses do ano anterior, com filtro por fornecedor, grupo e nome, o que cresceu, o
  que encolheu e o produto a produto em arquivo. A armadilha que ela evita: o corte da
  sincronização cai no meio de um mês, e comparar "setembro parcial" com "setembro inteiro"
  daria uma queda de 84% que não existe — a tela compara **só meses fechados** e escreve
  qual mês ficou de fora. O dado vem de uma tabela nova que a sincronização passou a
  gravar (vendas por produto por mês, janela de dois anos, porque comparar 12 meses com os
  12 anteriores exige dois anos de histórico), e ela já nasceu dentro da higienização das
  03:40 — foi exatamente o esquecimento que a 1.26.0 teve que corrigir no caixa. Até a
  primeira sincronização depois desta versão a tela diz que ainda não há o ano passado para
  comparar ([comparar-com-o-ano-passado.md](comparar-com-o-ano-passado.md)).
- **Tela nova: Tempo e venda.** Grava a condição do tempo de cada dia ao lado do que a loja
  vendeu, e mostra quanto a chuva custa. A conta é sempre **dentro do mesmo tipo de dia** —
  fim de semana e feriado de um lado, meio de semana do outro — porque a loja faz 76% do
  faturamento no fim de semana e misturar mediria o dia da semana, e não o tempo. Garoa não
  conta (o corte é 1 mm). O dia pode ser anotado à mão na tela, com observação ("choveu só
  de madrugada", "rua interditada"), ou buscado sozinho às 06:10 num serviço aberto de
  meteorologia, sem cadastro e sem mensalidade; **o que a pessoa da loja escreve nunca é
  sobrescrito pela busca**, porque quem estava no balcão viu o que a média de um quadrado de
  quilômetros não vê. Abaixo de oito dias de chuva e oito sem chuva a tela diz que ainda não
  dá para concluir, em vez de deixar alguém decidir compra por uma média de três dias
  ([tempo-e-venda.md](tempo-e-venda.md)).
- **Tela nova: produtos do fornecedor.** Quantos produtos, de quantos tipos, quanto gira e
  quanto está parado, com busca e arquivo, ligada da ficha do fornecedor e da lista de
  compra. A ficha já mostrava os vinte que mais custaram no ano, o que responde "onde foi o
  dinheiro" e não "o que este fornecedor tem". A tela avisa o que o dado é de verdade: o
  fornecedor de um produto é o da **última compra** dele no SET, não um cadastro de quem
  fornece o quê — é o catálogo que a loja montou comprando, que é a memória que ela tem.
- **Vender fora do fim de semana virou estudo, não tela.** O pedido era de meios para vender
  mais no meio de semana e explorar o site. Os 12 meses mostram que o problema **não é
  sortimento, preço nem horário**: o ticket é R$ 82 a R$ 107 em todos os dias da semana, 80%
  do faturamento sai entre 11h e 17h tanto no sábado quanto na terça, e o mix por grupo é
  praticamente idêntico (MADEIRA 18,6% contra 18,8%). É **fluxo de gente**: sete vezes menos
  pessoas comprando a mesma coisa do mesmo jeito. E a venda digital tropeça hoje num fato
  duro: 99,8% do faturamento está lançado em "CONSUMIDOR FINAL" — são 6 clientes
  identificados com compra no ano, somando R$ 713,89, então não há para quem avisar que
  chegou peça nova. O estudo está em
  [vender-mais-fora-do-fim-de-semana.md](vender-mais-fora-do-fim-de-semana.md), com o que eu
  recomendo em ordem de custo e a pergunta que falta responder (o que é "o site" hoje).
- Tarefa nova no servidor, `CabanaTempo` às 06:10 (`scripts\tempo.ps1`, registro em
  `logs\tempo.log`), a **única** parte do sistema que sai para a internet — e é tarefa de
  servidor, nunca tela. Se não alcançar a internet, guarda o erro para aparecer na tela e
  nada mais no sistema sente. A decisão de projeto "nenhuma tela depende da internet"
  continua valendo e está escrita assim na ficha técnica.

## 1.27.0 — 14/10/2026

Pedido do Edson olhando o print da 1.25.0: "disponibilizar relatório para impressão em
todas as listas do contas a pagar".

- **O botão do PDF passou a ficar com a lista, e a dizer o nome dela.** Ele nasceu dentro
  do cartão "Procurar uma conta", **acima** da fileira de filtros, chamado "Gerar PDF desta
  lista para imprimir". O link sempre levou o filtro escolhido, então o PDF de qualquer uma
  das seis listas já saía — mas quem lê a tela de cima para baixo vê a busca, depois o
  botão, e só então as seis listas, e conclui que o botão não é delas. Agora ele fica
  **entre os filtros e a tabela** e se chama pela lista: "Gerar PDF de Atrasados para
  imprimir", "Gerar PDF de Programação futura para imprimir". Ao lado, uma linha avisa que
  trocando a lista acima o botão passa a gerar a outra. Aparece nas seis, inclusive nas
  vazias: sumir numa lista vazia devolveria a mesma dúvida.
- **O papel passou a dizer onde a lista se encaixa.** Antes da tabela, o PDF traz as seis
  listas com a contagem e o valor de cada uma, com a impressa marcada em marrom
  (`Do dia (esta)`). Quem recebe a folha não está na frente da tela, e "2 contas" sozinho
  não diz se é muito ou pouco. São os mesmos números dos botões, da mesma
  `filtros_de_contas`.
- Juntar as seis listas num PDF só foi considerado e descartado: elas se sobrepõem
  (`Todas em aberto` = `Atrasados` + `A vencer`), e o papel repetiria as mesmas contas três
  vezes ([relatorio-em-pdf.md](relatorio-em-pdf.md)).
- Teste novo percorre as **seis listas** e cobra de cada uma o seu PDF e o seu botão com o
  nome certo, na tela e no papel.

## 1.26.0 — 14/10/2026

Os dois comandos do servidor — atualizar e higienizar — e a correção de uma limpeza
que estava incompleta desde o começo.

- **A higienização virou um comando, e passou a rodar sozinha.** O sistema guarda uma
  foto inteira dos dados do SET a cada sincronização e, desde a 1.25.0, sincroniza três
  vezes por dia: o disco e o banco crescem sozinhos todo dia e ninguém olhava. Agora
  `scripts\higienizar.ps1` limpa o que já não serve, e a tarefa `\Cabana\CabanaHigienizacao`
  roda todo dia às **03:40**, depois da sincronização da madrugada e do backup, antes de a
  loja abrir. Com `-Conferir` ele só mostra o que achou e não apaga nada, então dá para
  rodar a qualquer hora ([higienizacao.md](higienizacao.md)).
- **A cópia do banco do SET não fica mais parada no disco.** A importação copia o backup
  para ler num Firebird próprio e nunca reaproveita a cópia: a sincronização seguinte
  copia de novo, do zero. Mesmo assim o arquivo ficava lá, um banco do SET de **382 MB**
  — **com nome e CPF de cliente dentro** — guardado sem motivo em
  `dados\copia-set` até a próxima sincronização sobrescrever. Agora ele sai na
  higienização, e sai primeiro: é a razão de ser do comando, mais do que o espaço. Com
  sincronização rodando, a cópia fica onde está e o comando diz por quê.
- **Correção: a limpeza das fotos antigas esquecia o caixa.** `limpar_antigas` apagava
  as fotos de produto, conta, cliente, fornecedor, compra e venda além das dez últimas
  sincronizações, e não apagava os turnos de caixa, que têm `importacao` igual às outras.
  São **950 turnos por sincronização**, cada um com os seus movimentos, que nunca saíam
  do banco: com três sincronizações por dia, uns 15 mil registros por dia para sempre.
  A lista de modelos saiu de dentro da função que apaga e virou `fotos_fora_do_limite`,
  usada pela limpeza automática e pelo comando novo — uma lista só, que não dá mais para
  uma andar sem a outra.
- **Também saem na higienização:** sessões vencidas (eram 706 no banco de
  desenvolvimento), registro de acesso e de envio de relatório com mais de 90 dias,
  tentativas de sincronização sem dados com mais de 90 dias (nunca as 60 que a tela
  mostra) e arquivo de anexo sem registro. No fim, um `VACUUM (ANALYZE)` — sem `FULL`,
  que trancaria a tabela com o sistema no ar.
- **O que a higienização não toca:** auditoria, ficha de fornecedor, pagamento previsto,
  inventário, extrato bancário conferido, usuários, processos e os backups do sistema.
  Sai só o que o sistema sabe refazer sozinho na próxima sincronização; o que uma pessoa
  digitou fica. E nada aqui encosta no SET.
- **O LEIA-ME do pacote** passou a trazer os dois comandos juntos, o de atualização e o
  de higienização, que é o que se procura quando o servidor está na frente.

## 1.25.0 — 13/10/2026

Quatro implementações pedidas pelo Edson no mesmo dia.

- **A sincronização com o SET passou a rodar três vezes por dia**, às **08:30, 12:30 e
  19:30**, no lugar da única da madrugada. O botão **Importar agora** continua valendo a
  qualquer hora, e sincronizar várias vezes continua **substituindo** os números, nunca
  somando ([sincronizacao-nao-soma.md](sincronizacao-nao-soma.md)). A tarefa do Windows
  passou a ter três gatilhos num mesmo agendamento, e a atualização de uma instalação
  antiga adota os horários novos sozinha. A tela de Importações avisa o que ninguém pode
  adivinhar daqui: **se o SET gerar o backup uma vez por noite, as três sincronizações
  vão achar o mesmo arquivo** e os números continuarão sendo os da noite anterior. Para a
  tela acompanhar o dia, o backup do SET precisa rodar mais de uma vez.
- **O caixa passou a contar o dinheiro vivo.** A tela de Caixa já somava tudo o que
  passou pelo turno — dinheiro, PIX e os dois cartões —, que responde "quanto este turno
  movimentou". Agora ela responde também o que interessa na hora de fechar a gaveta:
  **quanto papel deveria estar lá dentro**. Saldo de abertura + o que foi recebido em
  dinheiro + entradas − sangrias − contas pagas pelo caixa, linha a linha no turno. No
  período, só o que é inequívoco: o que entrou, o que saiu e a gaveta do turno mais
  recente — somar a abertura de todos os turnos contaria o mesmo dinheiro muitas vezes, e
  nesta loja a abertura nem sequer é o fecho do turno anterior (falha em **642 dos 949**
  turnos). Forma de pagamento que o sistema não conhece **nunca** entra na conta calada:
  aparece à parte, pedindo que alguém avise a gerência. Dos R$ 4,09 milhões que o caixa
  recebeu, só **9,0% é papel**. [Documentação](caixa.md).
- **Contas a pagar ganhou campo de pesquisa e relatório em PDF.** A busca procura em
  fornecedor, descrição, documento, parcela e classificação, e **aceita com acento ou
  sem**: quem digita "quiteria" acha "QUITÉRIA FLOR MILHO". Quando há busca, os filtros
  passam a contar só o que foi encontrado, senão o número do filtro e o da lista
  discordariam. O PDF sai pelo botão na tela, obedece ao filtro e à busca que estiverem
  nela, e é escrito pelo próprio sistema: a biblioteca mais usada para isso traria 12 MB
  de extensões compiladas para desenhar uma tabela de texto, num pacote que se instala sem
  internet e onde uma roda errada já custou uma versão. [Documentação](relatorio-em-pdf.md).
- **Nasceu a conciliação bancária.** Importa o extrato do banco em **OFX** ou **CSV** e
  confronta cada saída com as contas que o SET diz que foram pagas: mesmo valor, data a
  até cinco dias de distância, e o nome do fornecedor desempatando. O número que interessa
  é o das **saídas sem conta no SET** — dinheiro que saiu da conta e não tem lançamento.
  O sistema **não marca nada sozinho**: mostra as candidatas e quem confirma é a pessoa,
  com um clique, e tudo o que foi conferido guarda quem conferiu e quando. Entradas
  (venda e cartão) ficam fora do confronto. O mesmo arquivo trazido duas vezes é recusado
  pela impressão digital do conteúdo. A conferência **sobrevive à sincronização seguinte**,
  porque o que fica guardado é o código do lançamento no SET, não a chave da foto.
  [Documentação](conciliacao-bancaria.md).

Três consertos que apareceram ao conferir as telas em print:

- **No celular, a caixa de procurar virava um quadrado de 18 rem de altura**, com o texto
  flutuando no meio. Em coluna, o `flex-basis` do computador passa a valer para a altura.
  Afetava as quatro telas com busca, entre elas a **consulta de balcão, que é a única tela
  do vendedor**.
- **Valor negativo saía como "R$ -335,91"**. Em português o sinal vem antes do cifrão:
  agora é "-R$ 335,91", em toda tela do sistema.
- A conferência de "quanto entrou menos quanto saiu" do caixa **pode dar negativo** (dá
  −R$ 5.815,01 em dois anos e meio) e mostrava o número sem explicação. Agora a tela diz
  o porquê: cada turno abre com um valor digitado no SET, dinheiro que já estava na gaveta.

## 1.24.1 — 11/10/2026

Uma revisão geral para prevenir erro e inconsistência, pedida pelo Edson. O que ela achou
de mais sério: **o vendedor conseguia ver o faturamento do ano**.

- **A tela de versões virou tela de dinheiro.** Ela mostra o histórico de mudanças, e o
  histórico explica cada conserto citando o número que estava errado — faturamento, lucro
  bruto, margem, o que está parado na prateleira, as diferenças de caixa. A tela pedia só
  login, então o `Operador vendedor`, que só pode ver a consulta de balcão, abria tudo
  isso digitando `/sistema/versoes/`. Agora ela pede a mesma permissão das outras telas de
  dinheiro. **O número da versão continua à vista de todo mundo**, no alto de toda tela,
  porque é por ele que se confere se a atualização entrou; o que ficou guardado é o
  histórico. Para quem não pode abri-lo, o número deixou de ser link, em vez de virar um
  erro ao clicar.
- **A conferência de rotas × perfis virou teste automático.** Até agora ela era feita à
  mão, uma vez por verificação geral, e foi assim que o furo acima passou despercebido em
  1.20.2. A lista de rotas não é mais digitada: o teste a lê do próprio Django, então tela
  nova entra na conferência no dia em que nasce. São 155 rotas conferidas contra os três
  perfis a cada execução dos testes. Quem criar uma tela de dinheiro e esquecer a
  permissão descobre antes de o pacote sair. [Documentação](verificacao-geral.md).
- **As páginas de recusa e de endereço errado ganharam a cara do sistema.** Eram HTML sem
  estilo nenhum, e pareciam o sistema quebrado. Agora têm o topo escuro, o creme do fundo
  e o botão de voltar. Continuam sem depender de nada (nem do CSS, nem do menu): página de
  erro que depende do que quebrou não aparece.
- **Os conferidores da skill explicam a falha em português.** Com o banco fora do ar,
  `validar-importacao.py` e os outros despejavam quarenta linhas de Python. Agora dizem que
  o banco não respondeu, o que conferir e que não é defeito do sistema.
- O resto da revisão passou limpo e está registrado em
  [verificacao-geral.md](verificacao-geral.md): a foto da importação, as variáveis de
  template, os apelidos de soma do ORM, as migrações e o `check --deploy`.

877 testes.

## 1.24.0 — 11/10/2026

A relação de tudo o que a loja vendeu no dia, com custo, lucro e margem de cada produto, e
o aviso pelo Telegram ao lado do e-mail.

- **Tela Vendas do dia** (`/sistema/painel/vendas-do-dia/`): escolhe o dia e mostra o que
  saiu da loja, produto por produto, com quantidade, valor vendido, custo, lucro em reais e
  margem. Quatro números no topo (vendido, custo, sobrou, margem) e o botão de baixar para
  o Excel com a relação inteira. [Documentação](vendas-do-dia.md).
- **O item da venda passou a ser importado**: o SET guarda, em cada produto vendido, quanto
  ele custava no dia da venda. São 32 mil itens em 12 meses, 191 no dia mais movimentado.
- **O SET parou de gravar o custo da venda em 25/08/2026**: até 24/08 faltava em 0,5% dos
  itens; de lá para cá falta em 70% a 100% deles, todo dia. Vale perguntar à SET Sistemas o
  que mudou. Enquanto isso, o sistema usa o custo do **cadastro** do produto como
  estimativa, marca a linha como `estimado` e diz quanto do dia está nessa situação.
  Produto que saiu do cadastro fica sem custo e **fora** da conta do lucro — contar custo
  vazio como zero daria margem de 100%.
- **Vendido abaixo do custo** aparece destacado na tela e ganha um bloco no e-mail, mas só
  quando o custo é o da venda: pedra vendida a peso tem custo de cadastro por quilo e viraria
  alarme falso.
- **Relatório diário novo**: a mesma relação sai por e-mail todo dia, no horário da tela.
- **Aviso pelo Telegram** (`/sistema/alertas/`): token do robô gravado cifrado, botão que
  descobre a conversa, aviso de teste, e erro em português. O e-mail leva o relatório
  inteiro; o Telegram leva a manchete e os números. Os dois são independentes: um pode
  estar ligado e o outro não. [Documentação](alertas-por-email.md).
- **Skill `cabana-reporting-system`** em `.claude/skills/`: as regras da loja, o caminho de
  um número do SET à tela, as armadilhas que já custaram versão e três scripts de
  conferência que não gravam nada.

## 1.23.1 — 10/10/2026

Os alertas por e-mail passaram a sair pela caixa da própria loja.

- **Por onde sai**, dito pelo Edson em 10/10/2026: `naoresponder@cabanadojacaranda.com.br`,
  na Hostinger, para `cabanadojacaranda@gmail.com`. A tela de Alertas já abre com servidor
  (`smtp.hostinger.com`), porta (465), quem envia e para quem mandar preenchidos: só falta
  a senha da caixa, que é a mesma de quem entra no webmail dela. Não é mais necessária a
  senha de aplicativo do Google.
- **A porta decide o modo da conexão**: a 465 abre em SSL desde o primeiro byte e a 587
  sobe para TLS com STARTTLS. Trocar um pelo outro não dá erro de senha, dá conexão
  travada; agora o sistema escolhe sozinho pela porta e explica isso em português quando o
  erro acontece.
- A tela, a ajuda do F1 e [a documentação](alertas-por-email.md) falam da senha da caixa
  no lugar da senha de aplicativo.

## 1.23.0 — 10/10/2026

A importação passou a conferir o arquivo de backup antes de ler, e a gerência ganhou um
botão para forçar a atualização com o backup mais recente.

- **Conferência do backup** (quadro novo no topo de `/sistema/importacao/`): antes de ler,
  o sistema olha o tamanho do arquivo, para avaliar se a gravação terminou, e a data, para
  confirmar que é mesmo o backup mais recente. Mostra arquivo, tamanho, data e o tamanho
  da importação anterior, e escreve o que estranhou. Arquivo sem tamanho de backup não é
  lido de jeito nenhum; arquivo que encolheu demais só é lido forçando; backup velho ou
  mais antigo que o já importado entra como ressalva, e importa. A conferência inteira vai
  para o log da importação, inclusive quando passa.
- **Forçar atualização com o último backup**: lê de novo o mesmo arquivo e refaz os
  números a partir dele, em vez de terminar como *Sem backup novo*. Forçar não soma — é a
  mesma foto por importação de sempre, e a comparação logo abaixo do quadro é a prova
  disso. Forçar não passa por cima de arquivo quebrado, porque trocaria número bom por
  número pela metade; nesse caso o botão não aparece. Pela linha de comando,
  `importar_set --forcar`.
- **No histórico**, a importação feita pelo botão aparece marcada como *forçada*, e no
  painel há um atalho para conferir o backup antes de importar.
- Documentação em [conferencia-do-backup.md](conferencia-do-backup.md).

## 1.22.1 — 08/10/2026

Correção da instalação da 1.22.0, que parou no meio no servidor da loja.

- **A tarefa de relatórios não era registrada.** Para dizer "repetir para sempre" o
  instalador usava `[TimeSpan]::MaxValue`, que vira `P9999999999DT23H59M59S` no XML da
  tarefa, e o agendador do Windows recusa como valor fora do intervalo. Agora são 24
  gatilhos diários, um por hora cheia — valor que o Windows sempre aceita. As 24 horas, e
  não só o horário comercial, porque o horário dos relatórios é escolhido na tela: cobrir
  só parte do dia criaria um horário que a tela aceita e nunca acontece.
- **Falha no meio da atualização não deixa mais a loja sem sistema.** A atualização para o
  sistema no começo e só o reinicia no fim; quando ela morreu na tarefa agendada, o
  sistema ficou parado até alguém mandar iniciar à mão. O instalador agora reinicia o
  sistema em qualquer saída com erro, e diz isso na tela.

## 1.22.0 — 08/10/2026

O sistema passou a avisar sozinho, por e-mail, e a tela de entrada passou a dizer em que
máquina e em que versão a pessoa está.

- **Alertas por e-mail** (`/sistema/alertas/`): três relatórios que saem sozinhos para o
  e-mail administrativo da loja. **Contas a pagar todo dia** (o que já venceu, o que vence
  hoje, o que vence em até 7 dias); **Estoque** e **Sugestão de compra** toda semana. A
  tela liga o envio, mostra o que já saiu e manda um de propósito quando se pede.
- **Nenhuma conta é refeita no e-mail.** Cada relatório chama a mesma função que a tela
  chama. Número de e-mail diferente do número da tela derrubaria a confiança no sistema
  inteiro, e já divergiu uma vez (o "parado" do Dashboard, corrigido na 1.20.2).
- **O relógio é do Windows, o horário é da tela.** A tarefa agendada roda de hora em hora
  e pergunta ao sistema o que já passou da hora e ainda não saiu. Horário gravado na
  tarefa passaria a mentir na primeira vez que alguém mudasse a hora na tela. Com isso,
  servidor desligado às 7h entrega o relatório quando ligar, em vez de pular o dia.
- **Dia sem notícia não gera e-mail.** Diário que chega sempre vira ruído que ninguém
  abre, e aí a conta vencida chega junto com o ruído. O registro é gravado assim mesmo,
  marcado "sem novidade", que não é falha: a tela mostra os três estados separados.
- **Erro de envio em português.** O que o Gmail devolve ("535 Username and Password not
  accepted") vira uma frase sobre senha de aplicativo. Toda tentativa fica registrada, para
  "não recebi o e-mail de ontem" ter resposta sem abrir a caixa de entrada.
- **A senha do e-mail é guardada cifrada** e nunca volta para a tela nem entra na
  auditoria. No Gmail ela não é a senha da conta: é uma senha de aplicativo, de 16 letras.
  Só o perfil Administrador gerência vê a tela.
- **O e-mail foi feito para o celular**: duas colunas por tabela, no máximo 12 linhas por
  lista, e uma versão em texto puro junto. Quatro colunas não cabem em 390px, e e-mail que
  rola de lado não é lido.
- **Tela de entrada com versão, servidor e IP**, logo abaixo do campo de senha. Respondem
  a mesma pergunta antes de alguém digitar a senha: "estou na máquina certa, na versão
  certa?". O IP é o mesmo que a auditoria grava em cada ação.
- Correções de acabamento que apareceram no caminho: campo de e-mail e de hora nasciam
  estreitos no meio de campos largos (faltavam na regra de formulário do `sistema.css`); o
  desinstalador deixava para trás as tarefas de importação e de relatórios; e a lista de
  contas do e-mail contava duas vezes a conta que vence hoje, porque o filtro "prestes a
  vencer" do financeiro já inclui o dia.

Detalhe em `docs/alertas-por-email.md`. 752 testes.

## 1.21.0 — 08/10/2026

A descrição técnica do sistema virou tela, dentro da Base de processos.

- **Ficha técnica do sistema** (`/sistema/processos/ficha-tecnica/`), com botão no alto da
  Base de processos. Ela diz de que o sistema é feito: a linguagem (**Python**), o
  framework (**Django LTS**), o **banco de dados (PostgreSQL)** com a versão, o servidor
  web, o motor que lê o backup do SET e as peças de apoio, cada uma com o que faz em uma
  linha. Embaixo, onde cada coisa fica no disco e como o sistema é atualizado.
- **O lugar não é por acaso.** A Base de processos existe para o que está na cabeça de uma
  pessoa não se perder, e quem um dia precisar manter este sistema sem ter participado de
  nada disto precisa exatamente dessa lista. O quadro passou a dizer isso em uma frase:
  vale para o trabalho da loja e vale para o próprio sistema.
- **Nenhum número é digitado à mão.** Cada versão é perguntada a quem sabe a resposta no
  momento em que a tela abre: o Python diz a sua, o banco responde pela conexão aberta, as
  bibliotecas dizem a que foi instalada. Versão escrita à mão envelheceria na primeira
  atualização, e ficha que mente é pior do que ficha nenhuma. O que não puder ser lido
  aparece escrito "não foi possível ler agora", nunca um palpite.
- **O instalador passou a gravar qual motor Firebird montou** (`CABANA_FIREBIRD_VERSAO` no
  `cabana.env`), porque carregar a DLL só para perguntar a versão é caro e é justamente o
  que falha quando algo está errado. A arquitetura (32 ou 64 bits) continua lida do próprio
  arquivo, que é o defeito que já travou a importação uma vez.
- **As quatro decisões que explicam o resto** ficam escritas na mesma tela, à mão de
  propósito: tudo mora dentro de uma pasta só, o Firebird aqui só lê a cópia, nenhuma tela
  depende da internet, e cada importação é uma foto que não se soma. Essas não se leem de
  lugar nenhum e não envelhecem sozinhas.

Detalhe em `docs/ficha-tecnica.md`. 666 testes.

## 1.20.2 — 08/10/2026

Os dois quadros do Dashboard que o Edson reclamou de novo, e uma verificação geral do
sistema inteiro atrás de falha, bug e erro de lógica.

- **A Curva ABC virou uma lista, igual às outras caixas da tela.** A faixa repartida da
  1.20.1 ele achou "confusa e difícil entendimento", e tinha razão: era desenho novo para
  aprender. Agora é **a mesma lista de barras** do "Dia da semana" e da "Forma de
  pagamento", das quais ele nunca reclamou. Uma linha por classe, com o nome em palavras
  em vez da letra solta — **A — sustentam a loja**, **B — ajudam**, **C — quase não
  vendem** —, quantos produtos são, que fatia do cadastro e do faturamento fazem, o que
  fazer com eles, e o valor em reais na ponta. O título do quadro deixou de ser "Curva
  ABC" e passou a ser **"Quais produtos sustentam a loja"**. Nada de texto dentro de
  barra: era de lá que vinham os dois problemas anteriores.
- **O gráfico estava mesmo truncado, e agora está explicado.** Medindo o print dele,
  nenhuma barra chegava ao topo do quadro: a maior, jul/26, parava em 74% da altura. O
  motivo é de escala. O gráfico se media pelo maior número **incluindo o do ano passado**,
  e o do ano passado era desenhado só como um risco tracejado — o maior valor de todos era
  mai/25, que não era barra nenhuma. Sobrava um quarto do quadro vazio em cima, sempre.
  Agora **cada mês tem duas barras lado a lado**: a cheia é este ano, a clara é o mesmo mês
  do ano passado, as duas na mesma escala, com a legenda escrita em cima do gráfico. Alguma
  sempre encosta no topo. Conferido em pixel no computador e no celular.
- **Verificação geral: 59 rotas, 29 telas, 3 perfis e 3 larguras de tela.** Varredura por
  programa, não tela por tela à mão: nenhum erro 500, nenhuma variável de tela em branco,
  nenhum erro de JavaScript, nenhuma barra horizontal no celular, nenhuma consulta ao dado
  do SET sem filtrar pela foto da importação, nenhum dinheiro em `float`. O método está em
  `docs/verificacao-geral.md`, para a próxima verificação não começar do zero. Quatro
  defeitos reais apareceram, e os dois primeiros **mudam número que ele já viu na tela**:
- **Saldo negativo do SET contava como dinheiro a menos no estoque.** A loja nunca fez
  contagem física e 1.456 produtos estão com saldo negativo. A soma `estoque × custo`
  levava esses negativos, e cada um encolhia o valor do estoque — R$ 126.812,28 a menos, no
  total. Saldo negativo é erro de cadastro, não prateleira devendo mercadoria: passou a
  contar como zero, e a tela diz quantos são. **"Parado na prateleira hoje" foi de
  R$ 615.032,91 para R$ 741.845,19**, e a cobertura do estoque de 10,3 para 12,4 meses. É o
  número certo, e o mesmo que o diagnóstico em planilha dava desde o começo.
- **"Parado sem vender" do Dashboard somava consumo próprio.** DIVERSOS e CONSUMO PROPRIO
  não são mercadoria de revenda, e por isso o Dashboard e o "O que fazer agora" mostravam
  valores diferentes para a mesma coisa. Agora as duas telas usam a mesma função de filtro.
  **De R$ 194.473,44 para R$ 227.005,64**, igual ao da tela de tarefas.
- **O faturamento do Dashboard e o da Visão geral não batiam, e nada explicava.** A Visão
  geral mostra R$ 1.576.325,86, que é o preço dos itens vendidos; o Dashboard mostra
  R$ 1.538.337,98, que é o que a venda fechou depois do desconto do balcão. Os dois estão
  certos — faltava a frase, e duas telas discordando em R$ 38 mil sem explicação é o que faz
  o dono do sistema desconfiar do resto. Cada cartão passou a dizer qual dos dois é.

Detalhe em `docs/verificacao-geral.md` e `docs/dashboard.md`. 655 testes.

## 1.20.1 — 08/10/2026

Três coisas que o Edson apontou: o gráfico mês a mês, a sessão que voltava aberta e a
Curva ABC.

- **O gráfico mês a mês estava mesmo torto, e por um motivo bobo**: a coluna do gráfico se
  chamava `.coluna`, o mesmo nome da coluna do quadro de processos, que tem fundo cinza e
  recheio de cartão. O navegador aplicava as duas regras, cada mês virava uma caixa cinza
  do tamanho do trilho e a barra parecia flutuando no meio do nada. Agora a coluna do
  gráfico tem nome próprio (`.coluna-mes`) e ninguém mais empresta estilo para ela.
- **O mês que ainda está correndo não é mais comparado com o mês inteiro do ano passado.**
  Era o segundo defeito do mesmo gráfico: no dia 7 de outubro, sete dias deste mês contra
  outubro inteiro do ano passado davam **-84%**, uma queda que não existe. A importação
  passou a trazer quanto o mesmo mês do ano passado tinha vendido **até o mesmo dia**, e é
  com esse pedaço que a comparação é feita. A barra do mês aberto é listrada e leva um
  "até dia 20" embaixo, para ninguém ler de igual para igual.
- **Sessão parada encerra sozinha, em trinta minutos.** Ele fechou o navegador, abriu de
  novo e voltou logado, e está certo em chamar isso de brecha. O cookie já era de sessão,
  mas o Chrome **restaura cookie de sessão** quando está em "continuar de onde parou" ou
  quando segue rodando em segundo plano — isso é decisão do navegador, e nada no site
  impede. O que resolve é o servidor recusar a sessão parada, e é o que passa a fazer:
  trinta minutos sem uso e a próxima tela pede senha de novo, com a explicação na tela de
  entrada. O limite de quatro horas logado continua valendo. Os dois tempos se mudam no
  `cabana.env`, em `CABANA_SESSAO_PARADA_MINUTOS` e `CABANA_SESSAO_MAXIMA_HORAS`.
- **A Curva ABC virou duas faixas repartidas.** A linha subindo num quadro sem números
  dizia alguma coisa para quem já sabe o que é curva ABC. No lugar dela: uma faixa com o
  cadastro repartido em A, B e C, e logo abaixo a mesma repartição do dinheiro. A
  desproporção entre as duas **é** a curva ABC e se vê de longe — **1.489 produtos (31,1%
  dos que venderam no ano) fazem 80,0% do faturamento**, e isso agora está escrito em uma
  frase acima do desenho.
- **O produto que cruza a linha dos 80% passou a ficar na classe A**, como é a convenção do
  varejo. Pela regra antiga, uma loja cujo maior produto já passasse dos 80% sozinho
  mostraria a classe A **vazia** na tela. Na Cabana muda um produto: 1.489 em vez de 1.488.

Detalhe em `docs/dashboard.md` e `docs/sessao-e-acesso.md`. 651 testes.

## 1.20.0 — 08/10/2026

Menu **Margem**, e o HTTPS dizendo por que não subiu.

- **Markup e margem de lucro, por produto e da loja inteira** (`/sistema/margem/`). O SET
  tem os dois lados da conta: o custo e o preço no cadastro do produto, e o custo que o
  produto tinha **no dia de cada venda**, gravado no item. Com isso a tela mostra o que a
  loja de fato ganhou em 12 meses — **54,5% de margem, 119,9% de markup, R$ 818.075,84 de
  lucro bruto** — e o que os preços de hoje dariam (58,3% de margem). Tem filtro por grupo,
  fornecedor e situação, ordem por margem, markup ou lucro, e o arquivo para o Excel com
  todos os 11.274 produtos.
- **O "% de lucro" do SET é markup, não margem.** O campo `PLUCRO` do cadastro confere com
  a conta do markup em 10.759 dos 10.764 produtos que têm os três campos preenchidos. A
  tela mostra os dois números com o nome certo, lado a lado, porque confundir os dois é o
  erro que faz dar desconto comendo o lucro inteiro.
- **O que o cadastro de preços está pedindo para arrumar**: 127 produtos com preço abaixo
  do custo (R$ 1.284,50 de prejuízo no que está na prateleira), 149 com preço igual ao
  custo, 164 com preço e sem custo, e 5 com o "% de lucro" do SET parado num preço antigo.
  Cada aviso abre a lista. A correção é no SET; o sistema só aponta.
- **Por que a porta segura não subiu, escrito na tela.** O túnel HTTPS sobe numa linha de
  trabalho separada, então a falha dele nunca chegava a quem inicia o sistema: ia só para o
  log. Agora o motivo é gravado em `dados\certificado\https-ultima-falha.txt` e aparece num
  cartão na tela do Certificado, com a data da tentativa; some sozinho quando a porta sobe.
- **O autodiagnóstico testa também o endereço da rede**, e não só o 127.0.0.1: assim dá
  para separar "o túnel não subiu" de "subiu mas não atende em 192.168.3.254". Quando os
  dois respondem, a tela diz em uma linha o que ainda pode faltar — a regra
  *Cabana Sistema HTTPS* no firewall e o certificado instalado no aparelho.
- **Sugestões desceu para a fileira de apoio**, ao lado de Sugestões da equipe. Era isso ou
  a fileira de cima passar a ocupar duas linhas com a entrada nova.

Detalhe em `docs/margem-e-markup.md` e `docs/certificado-ssl.md`. 640 testes.

## 1.19.1 — 08/10/2026

Correção das duas coisas que o Edson viu logo depois de instalar a 1.19.0.

- **O menu Caixa abriu vazio.** A importação que roda no fim da atualização viu que o
  backup do SET era o mesmo da noite anterior e pulou, como sempre fez. Só que o backup é
  metade da pergunta; a outra metade é o que o programa sabe ler dele. A foto que estava
  no banco tinha sido tirada pela 1.18.0, que não lia caixa nenhum — então a tela nova
  abriu sem dados e ia continuar assim até o SET gerar um backup diferente. Agora a regra
  também olha a versão: **versão nova relê o mesmo backup uma vez**, e o log diz por quê.
  Vale para qualquer tela futura que leia algo novo do SET.
- **O download do certificado dava "Página não encontrada".** A causa é a mesma coisa que
  vinha derrubando o HTTPS desde que ele existe: o certificado estava configurado para
  nascer em `C:\cabana-sistema\config\certificado`, e a conta que roda o sistema só tem
  **leitura** na pasta `config`. Ela nunca conseguiu criar o arquivo. Como quem tenta criar
  é o `servir.py`, que engole a falha de propósito para não derrubar o site, o erro ia só
  para o log: a porta segura não subia e o download não tinha o que entregar, sem nada
  escrito em lugar nenhum. Quatro mudanças:
  - o certificado passa a morar em `C:\cabana-sistema\dados\certificado`, onde essa conta
    escreve, e o instalador corrige sozinho quem está apontando para a pasta antiga;
  - a tela do Certificado **cria o certificado na hora** se ele não existir, em vez de
    mandar voltar depois;
  - quando mesmo assim não der, a tela mostra o motivo exato em vez de um 404 mudo, e o
    autodiagnóstico diz "o certificado do servidor não existe" em vez de só "ninguém
    atende na porta";
  - a atualização passa a rodar `conferir_certificado` e escrever na tela se o certificado
    foi criado e até quando vale, do lado do `conferir_banco`.
  - Além disso, se a pasta configurada não aceitar escrita, o sistema cai sozinho numa que
    aceite, para o HTTPS subir mesmo numa instalação antiga.

## 1.19.0 — 08/10/2026

- **Menu Caixa.** Pedido do Edson: "caixas aberto e fechados, valores, hora abertura, hora
  fechamento, dia, operador". A tela traz os turnos de caixa como o SET registrou — 950 turnos
  da loja no backup de 20/09/2026 —, com filtro de período, de operador e de situação (abertos,
  fechados ou os dois). Em cima, quatro números do recorte: quanto entrou pelo caixa, quantos
  turnos e em quantos dias, quanto saiu em sangria e em contas pagas pelo próprio caixa, e
  quantos turnos **não fecham pela conta**. Esse último é o que a tela acrescenta ao SET: o
  sistema refaz a conta de cada turno (saldo inicial, mais o que entrou, menos o que saiu) e
  compara com o saldo final gravado. Em 950 turnos, 7 não batem — o maior é o caixa 54, de
  15/04/2024, aberto pelo ADMIN, que fechou zerado quando a conta dava R$ 20.933,62
  negativos; depois dele vêm R$ 834,80 em 22/08/2025 e R$ 490,35 em 22/04/2026.
  Clicando no número do caixa abre o turno: o que entrou por forma de pagamento, a conferência
  linha por linha e a lista de retiradas, pagamentos e entradas, que é onde se descobre por que
  um caixa não fechou. Caixa esquecido aberto (mais de 24 horas) aparece em destaque no alto da
  tela, seja qual for o período escolhido, porque enquanto ele não é fechado no SET a venda do
  dia seguinte entra no turno errado. Vê quem administra e quem é administrativo; o vendedor não
  vê. O sistema só lê: abrir e fechar caixa continua sendo no SET. Detalhe em `docs/caixa.md`.
- **O HTTPS agora se explica.** O Edson disse "SSL ainda não funcionou" com a tela aberta em
  `http://192.168.3.254:8095`. O HTTPS nunca esteve nesse endereço — ele mora na porta 8443 — e,
  se o túnel não tivesse subido, o sistema também não diria nada: a falha só ia para o log.
  Duas coisas silenciosas que juntas viram "não funcionou". Agora quem entra pelo endereço sem
  cadeado vê uma faixa com o endereço seguro equivalente, clicável, e a tela do Certificado faz
  o teste de verdade: abre uma conexão TLS na porta segura, do próprio servidor, e diz se está
  funcionando, se ninguém está atendendo ali ou se o certificado está corrompido — com o que
  fazer em cada caso, em português.

## 1.18.0 — 08/10/2026

- **Dashboard.** Menu novo, o segundo da fileira de cima. Reúne num lugar só o que o varejo olha:
  faturamento, número de vendas, ticket médio e desconto dado, cada um com a seta comparando com o
  período anterior de igual tamanho; margem bruta, cobertura do estoque em meses, ruptura e dinheiro
  parado; faturamento mês a mês com o mesmo mês do ano passado marcado por um risco; **curva ABC**
  dos produtos; participação por grupo; campeões de faturamento e campeões de margem, que são listas
  diferentes de propósito; e dia da semana, forma de pagamento e hora do dia. Filtros de período,
  grupo e fornecedor. Os gráficos são desenhados pelo próprio sistema, sem depender da internet.
  Com os números de hoje: cobertura de 10,3 meses de estoque, margem de 54,5%, e 1.488 produtos
  (31% do cadastro) fazendo 80% do faturamento.
  Uma coisa a tela diz em voz alta: o SET registra a venda inteira e não o item vendido, então
  filtrar por grupo ou por fornecedor não mexe no faturamento, no ticket, no dia da semana nem na
  forma de pagamento. Esses blocos são sempre a loja toda.
- **Conferência da sincronização.** O Edson desconfiou que os números estavam somando a cada
  sincronização. Não somam: cada importação guarda a sua própria foto dos dados do SET e as telas
  leem só a mais nova. Para ele poder conferir sozinho a qualquer momento, a tela de Importações
  passou a mostrar as duas últimas importações lado a lado, número por número, com a diferença
  calculada. Lendo o mesmo backup duas vezes, tudo tem que dar igual — e a tela diz isso em verde
  quando dá. Se algum número algum dia dobrar, a tela avisa em vermelho. Foi checado com três
  importações seguidas do mesmo backup: produtos, vendas, lançamentos, compras, clientes, fichas e
  faturamento deram exatamente iguais nas três.
- **Campo de código de barras na consulta.** Na consulta de produtos entrou um campo só para digitar
  à mão o número da etiqueta da prateleira. A procura é pelo número exato, com ou sem os zeros da
  frente, e traz só o produto daquela etiqueta — diferente da busca de cima, que procura por parte
  do nome. Código que não existe explica o que conferir em vez de só dizer "nada encontrado".
- **Certificado SSL resolvido de verdade.** Até aqui o certificado era assinado por ele mesmo, e por
  isso o aviso do navegador voltava em cada aparelho novo e a cada renovação, para sempre. Agora o
  servidor tem uma **autoridade própria**: um arquivo que se instala uma vez em cada celular,
  tablet ou computador, pela tela nova em Certificado. Instalado, o aviso não volta mais, nem
  quando o certificado do servidor é renovado. A tela tem o download e o passo a passo de Android,
  iPhone (inclusive o passo das Configurações de Confiança, que quase todo mundo esquece) e Windows,
  com a impressão digital para conferir na hora de instalar. O certificado do servidor passou a
  valer 395 dias e se renova sozinho, porque acima de 398 dias os navegadores e acima de 825 a
  Apple recusam. A chave da autoridade nunca sai do servidor.
  Na primeira subida depois desta atualização o certificado do servidor é trocado, então o aviso
  aparece uma última vez em cada aparelho antes de a autoridade ser instalada.

## 1.17.0 — 07/10/2026

- **Lista de compra: o que comprar antes de faltar.** Tela nova. Até agora o sistema avisava do
  produto zerado, ou seja, depois de a loja já ter perdido a venda. Agora a conta é feita antes:
  um produto entra na lista quando o que tem na loja, mais o que já está a caminho, cai abaixo do
  **ponto de pedido** — o quanto ele vende por dia multiplicado pelo prazo do fornecedor, com uma
  semana de folga. Quando a loja cadastrou um **mínimo no SET** (são 2.807 produtos), o ponto de
  pedido nunca fica abaixo dele. A mercadoria com compra "Pendente" no SET é descontada, senão a
  lista mandaria comprar de novo o que já vem vindo. A lista sai agrupada por fornecedor, porque
  compra se faz por fornecedor, e dá para baixar em arquivo para abrir no Excel ou levar impressa.
- **O sistema diz por onde começar.** No topo da lista vêm os cinco fornecedores que tapam o maior
  buraco dentro do que ainda cabe no mês. Hoje, com os números da loja, são R$ 29.678 de pedido
  dentro dos R$ 53.845 que ainda cabem em outubro — a lista inteira daria R$ 184 mil, que é mais
  do que a loja pode gastar no mês. **E cada fornecedor sugerido vem com o contrapeso**: quanto da
  mercadoria dele já está parada na prateleira sem vender nada no ano. Na Campineira, por exemplo,
  a lista pede R$ 2.043 e avisa que já há R$ 7.127 parados dela.
- **"O que fazer agora" na tela de abertura.** O sistema passou a montar sozinho a lista de tarefas
  do dia, em ordem de urgência, cada uma com o número que a justifica e o botão que a resolve:
  conta vencida, pedido a fechar, produto abaixo do mínimo, mercadoria parada, sugestão da equipe
  sem resposta, prazo de fornecedor faltando, estoque negativo para contar. A tarefa some sozinha
  quando o motivo deixa de existir, e quem não tem acesso à tela não vê a tarefa.
- **Ticket médio na tela principal.** Entrou como um dos números grandes da abertura e ganhou um
  bloco com as duas leituras que ele já rendeu: qual dia mais fatura (e quanto o fim de semana
  representa) e qual forma de pagamento deixa o maior ticket. A tela cheia com filtros continua
  onde estava.

## 1.16.0 — 07/10/2026

- **Atalho na tela inicial do celular.** O sistema ganhou ícone próprio e abre em tela cheia, sem
  barra de endereço, como um aplicativo. No Android: abrir `https://192.168.3.254:8443/sistema/` no
  Chrome, menu de três pontos, "Instalar aplicativo" ou "Adicionar à tela inicial". No iPhone: abrir
  no Safari, botão de compartilhar, "Adicionar à Tela de Início". Não passa pela Play Store nem pela
  App Store, não tem conta de desenvolvedor para manter e não há um segundo programa para atualizar:
  é o mesmo sistema, com a cara de aplicativo. Tocar e manter o ícone abre atalho direto para
  Consulta de produto, Inventário e Antes de comprar. O visual (estilos e leitor de código) fica
  guardado no aparelho para a tela abrir rápido no wi-fi da loja; **número da loja nunca fica
  guardado**, porque saldo velho na tela seria pior do que tela nenhuma. A cada atualização do
  sistema o que estava guardado é apagado sozinho.
- **Ticket médio de venda, com filtros.** Tela nova: quanto o cliente gasta por compra, por período
  (7 dias, 30, 90 e 12 meses), por forma de pagamento, por vendedor e por dia da semana, mais a
  quebra mês a mês, o desconto médio e a maior venda. Para isso a importação passou a guardar venda
  a venda, com hora e forma de pagamento — antes guardava só a soma do mês. O recorte com menos de
  20 vendas vem marcado, porque dois ou três clientes mudam a média inteira. Duas coisas que o dado
  mostrou: **76% do faturamento sai no sábado e no domingo**, e o SET deixa o vendedor em branco em
  cerca de 7 de cada 10 vendas, então a comparação por vendedor só passa a valer se a loja começar
  a lançar a venda no nome de quem vendeu. A tela avisa isso em cima da lista. Nada de dado pessoal
  de cliente entra: a tabela de vendas do SET tem nome e CPF do comprador, e nenhum dos dois é lido.
- **Formulário de sugestão de compra da equipe.** Quem está na loja escreve o que viu — cliente
  pediu e não tinha, acabou na prateleira, vai faltar no fim de semana — com data, hora e nome de
  quem escreveu. A gerência responde na mesma tela, dizendo se entrou na lista de compra, se já foi
  comprada ou se não vamos comprar, e o histórico fica. É a informação que hoje se perde na conversa
  de balcão. Diferente da tela de Sugestões, que é o sistema calculando sobre o número do SET.
- **Leitor de código de barras e QR próprio.** A leitura pela câmera deixou de depender do recurso
  do navegador, que o Safari do iPhone não tem: o leitor agora vem dentro do sistema e lê EAN-13,
  EAN-8, UPC, Code 128, Code 39 e QR. Junto veio uma correção que valia para tudo: o leitor devolve
  um EAN-13 começado em zero como número de 12 dígitos, sem o zero da frente, e **todo código que o
  SET gerou começa em zero** — a busca passou a aceitar as duas formas.
- **Foto da prateleira na contagem.** Na tela da câmera, depois de registrar a contagem, dá para
  tirar uma foto do que ficou pendente ou duvidoso. A foto fica junto do item contado, com a hora, e
  só abre para quem entrou no sistema.

## 1.15.0 — 07/10/2026

- **O sistema abre no painel.** Entrar leva direto à Visão geral, em vez da página de atalhos:
  quem abre o sistema quer ver como a loja está. Quem não tem o painel (o perfil de vendedor) cai
  na tela de consulta, que é a dele.
- **Menu em dois níveis.** Em cima, em primeiro e com a cor da marca, as telas da decisão do dia:
  Visão geral, Antes de comprar, Sugestões, Consulta, Inventário e Financeiro. Embaixo, em caixa
  alta menor e cinza, as de consulta e administração: Painel, Compras, Fornecedores, Clientes,
  Base de processos, Importações, Usuários e Auditoria. Quem decide o que é de cada nível é um
  arquivo só (`apps/core/menu.py`), que também manda nas setas de "anterior" e "próxima".
- **A transferência de conhecimento agora mora na Base de processos.** A tela abre dizendo quanto
  do que a loja sabe já está escrito e validado, numa barra, com quantos processos de criticidade
  alta ainda faltam — que são os que param a loja se a pessoa faltar.
- **A versão saiu do rodapé.** Ela fica só no topo, que é onde se confere se a atualização entrou.
  Na tela de entrada, que não tem topo, ela continua aparecendo.
- **Contagem de inventário pelo celular, com a câmera.** Tela nova em Inventário: mire a câmera do
  celular ou do tablet na etiqueta de código de barras, confira as unidades e registre. A tela não
  recarrega entre uma leitura e outra, senão a câmera desligaria a cada produto. Funciona pelo
  wi-fi da loja, sem VPN. Navegador que não lê código de barras, ou câmera não autorizada, não
  travam nada: a digitação do código continua ali e dá no mesmo.
- **Porta segura (HTTPS) no servidor.** O navegador só libera a câmera em endereço seguro, então o
  sistema passou a responder também em `https://192.168.3.254:8443/sistema/`, com certificado feito
  pelo próprio servidor e renovado sozinho. Na primeira vez em cada aparelho o navegador avisa que
  a conexão não é privada: é só tocar em Avançado e Continuar. O acesso normal pela 8095 continua
  igual, e se o HTTPS não subir o sistema segue respondendo em HTTP.
- **Acabamento geral das telas.** Título em serifa, fio de latão sob o título de cada cartão,
  cabeçalho de página separado por um fio, fundo de papel e rodapé discreto. Vale para todas as
  páginas de uma vez, porque sai dos mesmos tokens de cor e fonte. Nenhuma fonte vem da internet.
- **Correção:** o botão Filtrar virava uma bola nas telas de busca desde a 1.14.0, porque dois
  blocos de estilo diferentes usavam o mesmo nome `filtros`.

## 1.14.0 — 07/10/2026

- **Compras, uma a uma.** Tela nova em Compras: a última compra de cada fornecedor, com quantos
  dias faz, e a lista das compras do SET com o detalhe de cada uma (fornecedor, comprador, nota,
  data do pedido, data da entrega, quanto demorou e item por item). Compra com situação Pendente
  no SET aparece marcada como mercadoria a caminho, que não é compra feita.
- **Filtros nas contas a pagar.** Atrasados, do dia, prestes a vencer (sete dias), a vencer e
  programação futura, cada um mostrando quantas contas pega e quanto dinheiro soma, antes de você
  clicar.
- **Auditoria com o endereço de rede.** Cada linha agora mostra de que endereço a ação partiu, e
  o topo da tela diz com que usuário e de que endereço você está conectado agora. A tabela mostra
  dez linhas e o resto desce na rolagem, com o cabeçalho fixo.
- **Sessão encerrada em quatro horas.** Quem fica logado mais que isso cai na tela de entrada e
  precisa entrar de novo. O computador fica no balcão e a conta não pode ficar aberta sozinha a
  tarde toda. O limite é contado da entrada, não do último clique, e dá para mudar no cabana.env
  (CABANA_SESSAO_MAXIMA_HORAS).
- **Leitor de código de barras.** A caixa de busca da consulta aceita o código de barras do SET:
  basta deixar o cursor nela e passar o leitor, que ele digita e manda procurar sozinho. Na cópia
  do banco, 11.268 dos 11.274 produtos têm código de barras cadastrado no SET.
- **O código de barras desenhado ao lado do produto.** Na consulta, cada produto mostra o próprio
  código desenhado, do mesmo jeito que sai na etiqueta, para conferir a olho ou para ler da tela
  quando a etiqueta do produto está rasgada. O desenho é feito pelo próprio sistema, sem internet,
  e só aparece quando o número é um EAN-13 de verdade: código torto não vira desenho, porque
  desenho errado faria o leitor ler outra coisa.
- **Inventário.** Módulo novo: abre-se uma contagem (um setor de cada vez), passa-se o leitor na
  prateleira e o sistema compara com o saldo do SET na hora, somando quando o mesmo produto é
  contado em dois lugares. No fim sai a lista do que está diferente, da maior diferença em dinheiro
  para a menor, e dá para baixar em texto para abrir numa planilha. Nada é escrito no SET: o ajuste
  do saldo é digitado lá por alguém da loja, porque é lá que o estoque vale. O SET tem essa tela e
  ela nunca foi usada — as tabelas de conferência estão vazias.
- **Autopreenchimento nas buscas de produto.** Com duas letras já aparece a lista de produtos que
  casam, com código e grupo, e dá para escolher com as setas ou com o dedo. Vale na consulta do
  balcão e na contagem do inventário. A lista sai do próprio sistema, sem internet.
- **Sugestões.** Tela nova com cinco listas tiradas dos números da loja, cada uma com a regra
  escrita por cima: repor agora (zerou e continua vendendo), parar de comprar (entrou no ano e não
  vendeu nada), pôr para girar (parado na prateleira, com o preço mínimo que ainda cobre o custo),
  empurrar na venda (o que vende e tem margem) e conversar com o fornecedor (de quem entrou muito e
  saiu pouco).
- **Cadastro de usuário completo.** Nome, sobrenome, e-mail e CPF. O CPF é conferido pelos dígitos
  na hora de salvar, não se repete entre usuários e não entra na trilha de auditoria.
- Correção de visual: rótulos de formulário usavam uma cor que não existia na paleta e saíam mais
  escuros do que deviam, em várias telas.

## 1.13.0 — 07/10/2026

- **O logotipo da loja virou o ícone do navegador.** O arquivo oficial entrou no sistema recortado
  em círculo, com fundo transparente, e é o mesmo símbolo que aparece no topo de todas as telas, na
  tela de entrada e na aba do navegador (.ico para o navegador no computador e PNG de 180px para o
  atalho de celular e tablet). O ícone desenhado à mão da 1.12.0 saiu.
- **Usuários e privilégios.** Tela nova em Usuários, só para a gerência, com três perfis:
  - *Administrador gerência*: tudo, inclusive importar, criar usuário e ver a auditoria.
  - *Operador administrativo*: lançamentos, contas a pagar e a receber, fornecedores, clientes e
    consulta de produtos. Não cria usuário, não roda importação e não abre a auditoria.
  - *Operador vendedor*: só a tela de Consulta, com descrição, código, grupo, estoque, fornecedor,
    prazo de entrega e data da última venda. Nenhum valor de custo, de margem ou de compra.
- Edson, Henriett e Moizes já nascem como Administrador gerência na atualização, sem senha: a tela
  mostra "ainda sem senha, não consegue entrar" até que a gerência defina a senha de cada um ali
  mesmo. Nenhuma senha provisória circula. Desligar alguém tira o acesso sem apagar o histórico, e
  ninguém consegue desligar a si próprio.
- Os grupos antigos (Gerência, Compras, Estoque, Consulta e auditoria, Operadores) viram os três
  perfis novos na própria atualização, e quem estava neles é transferido.
- **Ficha cadastral do fornecedor.** Clicar no nome na tela de Fornecedores abre a ficha: razão
  social, nome fantasia, CNPJ ou CPF, inscrição estadual, telefones, e-mail, site, contato,
  endereço completo, situação e observação — tudo lido do cadastro do SET, mais o que a loja compra
  dele produto a produto. O que vem do SET se corrige no SET; na importação seguinte o sistema pega
  o valor novo.
- **Que documento o fornecedor emite.** Campo novo na ficha, com três respostas: nota fiscal
  completa, nota fiscal parcial ou só recibo/romaneio. Não vem do SET, é a gerência que informa, e
  fica registrado na auditoria com quem anotou. É o que decide o que a loja consegue creditar na
  compra.

## 1.12.0 — 07/10/2026

- **Acentuação corrigida de vez.** No servidor da loja, "São Paulo" aparecia como "SÃ£o Paulo" na
  tela de clientes. A causa: a leitura do banco era feita sempre em cp1252, mas nem tudo o que o
  SET grava está em cp1252 — parte do cadastro está em UTF-8, e os mesmos bytes lidos pela tabela
  errada viram aquela sopa de letras. Agora a leitura tenta UTF-8 primeiro e só cai para cp1252
  quando os bytes não formam UTF-8 válido, que é o certo para quem lê o banco com charset NONE.
  Texto em cp1252 com acento praticamente nunca é UTF-8 válido por acaso, então as duas formas
  convivem sem se atrapalhar. O descarte de byte inválido da 1.7.1 continua valendo.
- Os nomes corrigidos entram na próxima importação, que a própria atualização executa no fim.
- **A ficha do fornecedor acompanha a correção.** O prazo de entrega e as estrelas ficam guardados
  pelo nome do fornecedor; se o nome mudasse na importação e a ficha não, o que a gerência
  preencheu sumiria da tela. A atualização corrige os nomes já salvos antes de importar e, quando
  encontra a mesma ficha duas vezes (uma com o nome torto e outra com o certo), fica com a certa.
  O mesmo vale para o texto digitado nos pagamentos previstos.
- **Ícone na aba do navegador.** O mesmo símbolo CJ do topo do sistema, em degradê de brasa para
  madeira, nos três formatos que os navegadores pedem: .ico para todos, SVG para quem aceita (fica
  nítido em qualquer tamanho) e PNG de 180px para atalho em celular e tablet. Tudo servido pelo
  próprio sistema, porque o servidor da loja não acessa a internet. A tela de entrada também leva
  o ícone, já que é a primeira aba que se abre.

## 1.11.0 — 07/10/2026

- **Tela "Antes de comprar"**, para abrir com o vendedor na frente, antes de fechar o pedido. É a
  única tela do sistema que serve para decidir, e não para conferir depois.
- **Limite de compra do mês.** Uma barra só, grande: quanto já foi comprado no mês contra o
  limite. O limite tem uma regra que qualquer pessoa refaz na calculadora: em 12 meses saíram da
  prateleira R$ 717.597,65 em mercadoria avaliada pelo custo; dividido por 12, é o que a loja
  repõe num mês médio, R$ 59.799,80. Verde até 80% do limite, amarelo até 100%, vermelho acima. E
  está escrito na tela que estar abaixo do limite não é motivo para comprar: o limite diz até
  onde não passar, não quanto gastar.
- **A comparação do ano inteiro**, embaixo do limite: quanto entrou em compra contra quanto saiu
  da prateleira em 12 meses. Na cópia atual saiu mais do que entrou, então a tela diz com todas as
  letras que o problema não é o tamanho da compra e sim a escolha do que comprar, e aponta onde.
- **"Posso comprar este produto?"** Digite o nome ou o código e o sistema responde em letra
  grande e colorida: **pode comprar**, **não precisa agora** ou **não compre**, sempre com os
  números que levaram à resposta (o que está na prateleira, quantos dias isso cobre, o que vendeu
  e o que foi comprado em 12 meses, última compra e última venda). Produto que não vendeu nenhuma
  unidade no ano e está zerado recebe "não compre por conta própria, só repor se for pedido de
  cliente", em vez de ficar sem resposta. Saldo negativo no SET aparece marcado, para ninguém
  decidir por um número que a loja ainda não conferiu na prateleira.
- **"O que a compra do ano virou"**, por fornecedor: quanto a loja comprou, quanto disso já saiu
  em venda e quanto continua na prateleira, tudo avaliado pelo custo, com os piores primeiro. A
  última coluna é mercadoria que entrou e não vendeu nenhuma unidade em 12 meses: R$ 102.376,02
  no total, com VIME LENZI (R$ 10.465,00) e CERAMICA ARTISTICA STARBELLA (R$ 7.638,68) na frente.
  Essa coluna é a conversa a ter com cada fornecedor.
- A tela entra no menu entre "Visão geral" e "Painel", tem tour por F1 em quatro passos e foi
  conferida em monitor, tablet e celular.

## 1.10.0 — 07/10/2026

- **Tela "Visão geral".** Uma página só, de abertura, feita para quem não vai mexer no sistema:
  quatro números grandes no topo (vendido em 12 meses, comprado em 12 meses, parado na prateleira
  hoje e já comprometido do caixa), cada um com uma linha em letra miúda dizendo o que o número
  quer dizer e pintado de verde, amarelo ou vermelho conforme o caso. Na cópia atual ela abre com
  R$ 1.576.325,86 vendidos, R$ 519.248,39 comprados (32,9% do faturamento), R$ 615.032,91 parados
  em estoque e R$ 99.561,37 já comprometidos, com 49 contas vencidas.
- **Compra contra venda, mês a mês**, no mesmo gráfico de barras do painel, para mostrar de relance
  se a loja comprou mais do que vendeu em cada mês.
- **De onde vem o faturamento**, num gráfico de rosca por grupo de produto (Madeira 18,6%, Tapete
  Couro 16,2%, Cerâmica 9,4% e assim por diante), com a legenda ao lado.
- **Os 10 produtos que mais vendem e os 10 que menos vendem**, lado a lado, pela receita dos
  últimos 12 meses. A lista dos que menos vendem considera só produto que vendeu alguma coisa; o
  que não vendeu nenhuma unidade no ano inteiro é contado à parte, porque é outro problema (são
  6.483 hoje).
- **Reputação de fornecedor com estrelinhas.** Na tela de Fornecedores, cada fornecedor recebe de 1
  a 5 estrelas e uma relação com a loja: **parceiro**, **flexível** ou **eventual**. A nota é
  clicada direto na linha, junto com o prazo de entrega, e fica registrada na auditoria com o valor
  antigo e o novo. Nada disso vem do SET, é avaliação da gerência.
- **Fornecedores na visão geral**: a tabela mostra os maiores fornecedores do ano com as estrelas e
  a etiqueta de relação, e diz quantos ainda estão sem avaliação, com atalho para avaliar.
- A tela tem tour por F1 em quatro passos, como as outras, e foi conferida em monitor, tablet e
  celular.

## 1.9.0 — 07/10/2026

- **Financeiro, lendo o que já existe no SET.** Descoberto na cópia do banco que o SET já guarda
  contas a pagar, contas a receber e plano de contas: são 7.478 contas a pagar, 44.229 a receber e
  77 classificações. Então nada disso é digitado de novo. A importação passa a trazer esses
  lançamentos junto com os produtos (40.307 na cópia atual) e quatro telas novas mostram o
  resultado.
- **Contas a pagar**: o que está em aberto, o que já venceu e quanto sai do caixa nos próximos 7,
  15, 30 e 90 dias. É o contrapeso do painel de compras: antes de autorizar uma compra grande dá
  para ver quanto já está comprometido.
- **Despesas**: quanto entrou e quanto saiu em cada mês, com o mês em que faltou dinheiro escrito
  em vermelho, e para onde o dinheiro foi nos últimos 12 meses pela classificação do próprio SET.
- **Contas a receber**: o que ainda está para entrar e quanto entrou por mês. A loja vende quase
  tudo à vista, então o que fica a receber é pouco e a tela diz isso.
- **Pagamentos a fornecedores**: quanto já foi pago a cada fornecedor, os últimos pagamentos
  baixados no SET e o registro de **pagamento previsto**, para a projeção de caixa contar com o
  que a loja já combinou e ainda não foi lançado no SET. O previsto sai da projeção quando é
  marcado como lançado, para não contar duas vezes.
- **Módulo de clientes**, com o que cada um comprou. Guarda só nome, cidade, estado, data de
  cadastro e as compras: CPF, RG, endereço, telefone e dados de família ficam no SET, porque são
  dados pessoais e não há motivo para copiá-los (LGPD).
- Achado do dado do SET: quase toda venda da loja é lançada em CONSUMIDOR FINAL, o cliente
  genérico do balcão (43.397 das 43.578 vendas com cliente). O cadastro tem 238 clientes e poucos
  compraram no último ano. A tela separa o balcão do cadastro para o número não enganar.
- **Lembrete do dia novo**: conta vencida no SET, levando direto para contas a pagar.
- O financeiro só aparece para quem tem a permissão de ver finanças, e registrar pagamento
  previsto é uma permissão à parte, da gerência.

## 1.8.0 — 06/10/2026

- **Painel resumido e painel completo.** O painel abre agora com o essencial: o aviso de quando são
  os dados, os três números do topo, o indicador mais firme (comprou mais do que vendeu), reposição
  e venda em risco, a lista dos melhores produtos para comprar e o gráfico de compra e venda mês a
  mês. Um botão leva ao painel completo, que continua com todos os indicadores, todas as listas e os
  avisos sobre contagem de estoque e prazo.
- **Módulo de fornecedores**, com o prazo médio de entrega informado por fornecedor. É o parâmetro
  que faltava: o SET grava na compra a data da nota, não a do pedido, então o prazo medido sai zero
  em 195 das 328 compras e a sugestão de compra chegava tarde. O prazo informado aqui vale mais que
  o medido e entra direto na conta de quando comprar. A lista vem ordenada pelo que mais pesou em
  compras nos últimos 12 meses, para começar pelos que mais mudam a sugestão.
- **Produtos comprados recentemente** e **produtos comprados há muitos anos** (sem compra há dois
  anos ou mais), as duas listas no painel completo, com a data da última compra e da última venda.
- **Sugestão dos melhores produtos para comprar agora.** Entre os que chegaram ao ponto de reposição,
  o sistema ordena pela margem que o produto deu em 12 meses (preço de venda menos custo, vezes o que
  saiu), para a compra render mais por real gasto.
- **Setas para trocar de tela** no pé de cada página, na ordem em que as telas se usam, e cada seta
  diz o nome da tela para onde vai.
- **Responsivo em tablet e celular.** O topo passou a ter duas linhas (marca, versão e usuário em
  cima, menu embaixo), os cartões viram uma coluna só no celular e as tabelas largas rolam de lado
  dentro do próprio quadro, sem arrastar a página junto. Conferido em 1600px, 1024px e 390px.
- **Lembretes do dia**, em aviso que abre uma vez por dia no primeiro acesso: idade dos dados,
  produtos vendendo sem estoque, reposição sugerida e fornecedores sem prazo. Cada lembrete leva
  direto para a tela do assunto.
- **Tour guiado abre sozinho na primeira visita** a cada tela, e segue disponível pelo F1. Antes
  dependia de o usuário saber que existia.

## 1.7.1 — 06/10/2026

- **Correção da leitura do banco.** A importação chegou a abrir a cópia e a ler os produtos, mas
  parou com `'charmap' codec can't decode byte 0x81`: o SET grava o texto em cp1252 e há descrição
  com byte que não existe nessa tabela. Agora a leitura usa um cp1252 com um ajuste só, descartar o
  byte inválido, e o log diz quantos foram descartados. Os acentos continuam certos (conferido na
  cópia real: 1.677 produtos com acento, incluindo "TAÇA MÉDIA" e aspas do Windows).
- **Tela de entrada refeita.** Sem menu e sem usuário, o topo escuro não tinha o que mostrar: ele
  virou o fundo da página, a marca subiu para cima do cartão e o cartão ficou centrado na tela, com
  os campos e o botão na largura toda. Conferido em 1600px e em celular.
- **Versão no menu superior**, ao lado do usuário, levando para a tela de versões. Antes só aparecia
  no pé da tela.

## 1.7.0 — 06/10/2026

- **Tela "Versões do sistema"**, aberta pelo número de versão no pé de qualquer tela. Mostra a versão
  instalada agora, a lista das atualizações já aplicadas neste servidor (quando entrou, qual versão,
  qual arquivo de atualização e se concluiu) e o resumo do que mudou em cada versão.
- O `instalar.ps1` passa a registrar cada atualização aplicada em `logs\atualizacoes.tsv`, e o
  `atualizar.ps1` informa o nome do zip usado. Antes o histórico só existia no log da instalação,
  no servidor.
- **Alinhamento das telas.** A tarja colorida da esquerda dos cartões era uma borda mais grossa que a
  dos outros cartões, então o texto de cada cartão começava numa coluna diferente e a tela ficava
  torta. Agora a tarja é desenhada por dentro e todo cartão tem o mesmo recuo.
- O topo escuro, o aviso do usuário e o aviso da data dos dados passam a ter o conteúdo na mesma
  coluna do miolo da página: a marca deixa de ficar colada na borda enquanto o título ficava bem
  mais para dentro.
- Comando `manage.py conferir_firebird`, que o instalador roda junto com o `conferir_banco`: ele
  confere se o motor Firebird existe, se os bits batem com os do sistema, se as peças ao lado
  (engine13, mensagens, acentuação) estão lá e se o Windows consegue carregá-lo, e escreve em
  português o que está faltando. Antes o único sinal era um erro do Windows sem explicação, visto
  só quando a importação já tinha falhado.

## 1.6.3 — 06/10/2026

- **Correção da leitura do backup.** A importação achava e copiava o backup, mas parava ao
  abrir a cópia com `[WinError 193] %1 não é um aplicativo Win32 válido`. Causa: o motor
  Firebird montado no servidor vinha da instalação do SET, que é de 32 bits, e o Python do
  sistema é de 64 bits; o Windows recusa carregar um dentro do outro.
- O instalador passa a conferir a arquitetura no cabeçalho de cada `fbclient.dll` antes de
  aceitá-lo: descarta o de 32 bits que já estava montado (guarda a pasta antiga com data),
  só aproveita um Firebird do servidor se for de 64 bits e, quando não há nenhum, usa o
  `Firebird-4.0.6.3221-0-x64.zip` que agora viaja dentro do pacote (sem internet no
  servidor); se faltar, tenta baixar do site oficial.
- A versão 4.0 é a certa: a cópia do banco do SET é ODS 13, que é o formato do Firebird 4.
- A leitura também confere os bits antes de tentar abrir a cópia, e o painel explica esse erro
  em linguagem de loja, com o comando da atualização.
- Nada muda no SET: o motor fica só dentro de `C:\cabana-sistema\firebird`, embutido, sem
  serviço e sem porta.

## 1.6.2 — 06/10/2026

- **Correção do erro no painel e na importação.** As colunas `etapa` e `progresso` foram
  acrescentadas ao `0001_initial` depois que ele já tinha rodado no servidor. O Django guarda a
  migração pelo nome, considerava a migração aplicada e nunca criava as colunas, então o painel
  dava erro 500 e a importação parava com `column "etapa" does not exist`. Uma migração nova
  cria as colunas quando faltam e não faz nada em banco novo.
- Comando `manage.py conferir_banco`, que compara as colunas do banco com o que o programa
  espera. O instalador roda depois de migrar, então uma diferença assim aparece na instalação,
  e não quando a gerência abre a tela.
- Lição aplicada ao projeto: migração já aplicada no servidor não se edita; a mudança vai numa
  migração nova.

## 1.6.1 — 06/10/2026

- **Correção da atualização.** Na 1.4.0 o nome do pacote mudou de
  `cabana-sistema-pacote-...zip` para `cabana-sistema-...zip`, e o `atualizar.ps1` do servidor
  procura justamente por `cabana-sistema-pacote-*`. Resultado: ele não via os pacotes novos,
  reinstalava em silêncio o pacote antigo e dizia "Concluído". Nada das versões 1.4.0, 1.5.0 e
  1.6.0 chegou ao servidor. O nome voltou a ter `pacote-`, e o script passa a aceitar qualquer
  zip que comece com `cabana-sistema`, a dizer qual pacote e qual versão aplicou e a avisar
  quando ignora um zip da pasta.
- No fim da instalação, o instalador chama as telas principais e avisa se alguma responder
  erro 500, em vez de terminar dizendo que está tudo certo.

## 1.6.0 — 06/10/2026

- Visual refeito em todas as telas: topo escuro com a marca e o menu em destaque, cartões com
  sombra, números grandes em cartão próprio (valor em estoque, produtos, dias com venda), selo no
  indicador que não depende da contagem, tabelas com cabeçalho destacado e números alinhados à
  direita. Paleta quente (madeira e brasa), ainda provisória até chegar a identidade oficial.
- Compra e venda mês a mês viraram gráfico de barras: verde para venda, laranja para compra, com
  o mês em que a compra passou a venda marcado.
- O backup do SET pode vir compactado: o sistema abre o `.zip`, pega o `.FDB` ou `.FBK` de dentro
  e lê a cópia. É o formato que a Cabana gera (Set-Cabana-FULL.zip).
- `--arquivo` e `CABANA_SET_BACKUP` aceitam a pasta, não só o arquivo: antes, apontar para a pasta
  pelo comando dava "não encontrei o arquivo de origem".
- Erros novos com explicação em linguagem simples: zip sem banco dentro e zip incompleto.

## 1.5.0 — 06/10/2026

- Revisão do módulo de importação com a cópia real do banco. Correções:
  - Compra com situação `Pendente` no SET (pedido ainda não recebido) deixa de contar como
    compra feita e passa a entrar como mercadoria a caminho, descontada do que falta comprar.
    Com os dados de 20/09/2026: 142 produtos com pedido em aberto, "comprou mais do que vendeu"
    passou de R$ 189.041,16 para R$ 187.333,96 e a sugestão de compra caiu de 1.208 para
    1.163 produtos.
  - O prazo de entrega passa a ser medido só nas compras já recebidas.
  - O log de cada importação passa a contar os itens de compra e de venda sem cabeçalho no SET
    (95 e 14), que o sistema ignora, para a diferença não parecer erro de importação.
- O painel avisa quantos produtos têm pedido de compra em aberto e explica que, em 195 das 328
  compras, o SET registra a entrega no mesmo dia do pedido, o que encurta o prazo calculado.
- Depois de instalar ou atualizar, o sistema já roda a importação (a mesma da madrugada) e
  mostra o resultado no próprio PowerShell. `-SemImportar` pula essa primeira importação.
- As mensagens informativas do Django deixam de sair pela saída de erro, que o PowerShell
  mostrava em vermelho como se fossem falha da instalação.
- O horário da importação só é regravado quando informado no comando; ajuste feito à mão em
  `config\cabana.env` passa a ser respeitado.

## 1.4.0 — 06/10/2026

- Cada importação passa a gravar o próprio log, passo a passo com hora: qual
  backup foi escolhido, o tamanho e a data do arquivo, cada etapa da leitura,
  os números apurados e, quando falha, em que ponto parou. O log aparece na
  tela de Importações e pode ser baixado em texto.
- O mesmo log vai para `logs\importacao.log` no servidor, escrito pela tarefa
  automática, com rotação acima de 5 MB.
- Versão do sistema visível no pé de todas as telas e registrada em cada
  importação, para saber qual pacote produziu cada número.
- A tela de Importações explica a sincronização diária: horário da tarefa e
  pasta de onde sai o backup mais recente.
- O horário da importação passa a ficar em `CABANA_IMPORTACAO_HORA`
  (`config\cabana.env`), e a tarefa agendada é registrada por ele.

## 1.3.0 — 05/10/2026

- Barra de progresso com a etapa e a porcentagem durante a importação.
- Aviso de conclusão em verde e de falha em vermelho, com o erro escrito em
  linguagem simples e a lista numerada do que fazer; a mensagem técnica fica
  guardada à parte.
- Ajuda por F1 com tour guiado em todas as telas, funcionando sem internet.

## 1.2.0 — 05/10/2026

- A importação passa a procurar sozinha o backup mais recente de
  `C:\backup-Set\Cabana\Set-Cabana`, incluindo subpastas, conferindo a data do
  arquivo.
- Tarefa diária de importação registrada no Windows.

## 1.1.0 — 05/10/2026

- Painel de compras e estoque com os seis indicadores, lista de produtos por
  indicador e a comparação de compra e venda mês a mês.
- Aviso de atualização dos dados em todas as telas: amarelo com 2 a 3 dias de
  atraso, vermelho a partir de 4.
- Histórico de importações com o botão "Importar agora".
- Leitura da cópia do backup do SET num Firebird próprio, sem tocar no banco em
  uso.

## 1.0.0 — 04/10/2026

- Primeira instalação no servidor da loja: contas, base de processos, auditoria
  em registro que não se apaga, backup do próprio banco e instalador com
  atualização e higienização.
