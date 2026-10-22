# Alertas e notificações (1.22.0; caixa da loja na 1.23.1; Telegram na 1.24.0)

Tela em `/sistema/alertas/`, código em `apps/alertas/`.

## O pedido

Em 08/10/2026 o Edson pediu: *"quero que envie os relatório de alertas e notificações por
e-mail. e-mail administrativo: cabanadojacaranda@gmail.com. contas a pagar vencidas e
prestes a vencer e do dia — rotina diária. relatórios de estoque — rotina semanal.
relatórios de sugestão de compra de produtos importantes — rotina semanal."*

Em 10/10/2026 ele definiu por onde sai: *"origem saída:
naoresponder@cabanadojacaranda.com.br, destino: cabanadojacaranda@gmail.com"*. É uma caixa
do próprio domínio da loja, hospedada na Hostinger.

Em 11/10/2026 ele pediu o quarto relatório e o segundo caminho: *"quero junto ao e-mail
também seja enviado notificação pelo telegram"* e *"uma relação de todos os produtos
vendidos do dia"*.

São quatro relatórios, duas frequências e dois caminhos. A tela de Alertas é onde se liga
cada um, se confere o que já saiu e se manda um de propósito.

## O que vai em cada e-mail

| Relatório | Quando | O que leva |
| --- | --- | --- |
| Contas a pagar | todo dia | o que já venceu, o que vence hoje e o que vence em até 7 dias |
| Vendas do dia | todo dia | a relação do dia: produto, custo, lucro e margem ([vendas-do-dia.md](vendas-do-dia.md)) |
| Estoque da loja | toda semana | quanto está na prateleira, o que não gira, o que precisa sair pela venda |
| Sugestão de compra | toda semana | o começo da lista de compra, por fornecedor, dentro do teto do mês |
| Backup no GitHub | todo dia, **só quando há problema** | token vencendo, cópia velha ou backup desligado ([backup-no-github.md](backup-no-github.md)) |

## Quatro decisões que o recurso carrega

### 1. Nenhuma conta é refeita no e-mail

Cada relatório chama a **mesma função que a tela chama**: `financeiro.servicos` para as
contas, `painel.visao_geral` e `compras.sugestoes` para o estoque, `compras.lista_de_compra`
(montar **e** priorizar, como a tela faz) para a compra, `painel.vendas_do_dia` para a
relação do dia. Regra copiada é regra que diverge,
e já divergiu uma vez — o "parado" do Dashboard contra o das Sugestões, corrigido na
1.20.2. Número do e-mail diferente do número da tela derruba a confiança no sistema
inteiro, não só naquele número.

### 2. O relógio é do Windows, mas o horário é da tela

A tarefa agendada `\Cabana\CabanaRelatorios` roda **de hora em hora** e pergunta ao
sistema o que já passou da hora e ainda não saiu (`apps/alertas/agenda.py`). Ela não sabe
o horário de nada.

São 24 gatilhos diários, um por hora cheia, e não um gatilho com repetição: "repetir para
sempre" vira `[TimeSpan]::MaxValue`, que sai no XML como `P9999999999DT23H59M59S`, e o
agendador do servidor da loja recusa como valor fora do intervalo — foi assim que a
instalação da 1.22.0 parou. Hora cheia é valor que o Windows sempre aceita.

Registrar a tarefa nos horários gravados no banco funcionaria no dia da instalação e
passaria a mentir na primeira vez que alguém mudasse a hora na tela, sem nada avisando.
De graça vêm três coisas:

- servidor desligado às 7h entrega o relatório quando ligar, em vez de pular o dia;
- mudar o horário na tela vale no mesmo dia, sem reinstalar nada;
- falha de envio pode ser tentada de novo, no máximo 3 vezes por dia (`TENTATIVAS_POR_DIA`)
  — insistir de hora em hora é a melhor forma de a caixa de e-mail da loja ser bloqueada.

### 3. Relatório sem notícia não é mandado

`tem_noticia` diz se há algo que mude o que a pessoa faz hoje. Num dia sem conta vencida,
sem conta do dia e sem conta da semana, o e-mail não sai: diário que chega sempre vira
ruído que ninguém abre, e aí a conta vencida de verdade chega junto com o ruído.

O registro é gravado assim mesmo, marcado **sem novidade** — que não é falha, e a tela
mostra os três estados separados: *entregue*, *sem novidade*, *não saiu*. O botão "Mandar
agora" é o único caso em que o sistema manda um relatório vazio: quem apertou quer ver o
e-mail.

### 4. Toda tentativa fica registrada

"Não recebi o e-mail de ontem" precisa de resposta sem abrir a caixa de entrada. O
`EnvioDeRelatorio` guarda quando, para quem, o que o relatório dizia, e o erro **em
português** quando houve. `apps/alertas/envio.py` traduz o que o SMTP devolve: `(535,
b'5.7.8 Username and Password not accepted')` vira uma frase sobre a senha da caixa que
envia. O que não for reconhecido vai cru — erro desconhecido escondido é pior do que erro
feio.

## Por onde sai (1.23.1)

| Campo | Valor | De onde veio |
| --- | --- | --- |
| Servidor de saída | `smtp.hostinger.com` | painel da Hostinger |
| Porta | 465 | idem |
| Conexão segura | ligada (SSL, por ser a 465) | idem |
| Usuário / quem envia | `naoresponder@cabanadojacaranda.com.br` | Edson, 10/10/2026 |
| Para quem mandar | `cabanadojacaranda@gmail.com` | Edson, 08 e 10/10/2026 |

Tudo isso já vem preenchido na tela, como padrão do modelo e pela migração
`alertas/0002_caixa_da_loja`, que completa a linha de configuração que ninguém chegou a
mexer. É campo de tela: trocar de provedor um dia é digitar outro servidor, sem mexer em
código.

**A porta decide o modo da conexão**, e não um campo a mais na tela: a 465 fala TLS desde
o primeiro byte (SSL), a 587 abre em claro e sobe com STARTTLS. Trocar um pelo outro não
dá erro de senha, dá conexão travada ou derrubada, que é bem mais difícil de entender
olhando a tela. Por isso `ConfiguracaoDeEmail.porta_de_ssl` e o erro traduzido para
`wrong version number`.

## A senha

É a senha da caixa que envia, a mesma de quem entra no webmail dela. (Se um dia o envio
for por uma conta do Gmail, aí sim precisa ser uma *senha de aplicativo*, de 16 letras,
gerada na Conta do Google com a verificação em duas etapas ligada — o erro traduzido
continua dizendo isso.)

Ela é guardada cifrada (`apps/alertas/cifra.py`, Fernet com chave derivada da
`SECRET_KEY`). Honestidade sobre o que isso é: **não** protege contra quem já tem o
servidor, porque a `SECRET_KEY` mora no `cabana.env` ao lado do banco. Protege contra quem
abre a tabela num cliente de banco, recebe um backup do PostgreSQL ou lê um dump num pen
drive — e senha de e-mail é a chave para redefinir senha de todo o resto. O formulário
nunca mostra a senha de volta, e ela não entra na auditoria: o que fica registrado é se
existe uma.

## Quem pode mexer

Só o perfil **Administrador gerência**, pela permissão `alertas.configurar_email`. O
Operador administrativo e o Operador vendedor não veem a tela nem o item no menu.

## O que sai da loja

O e-mail de contas a pagar leva o nome de quem a loja deve — que é o conteúdo do
relatório, e sem ele ele não serve para nada. Isso significa que esses nomes saem do
servidor da loja e passam pela Hostinger até a caixa configurada. É dado da própria loja,
indo para o endereço administrativo dela; vale saber que é assim.

Nenhum relatório leva dado de cliente.

## O e-mail em si

HTML com estilo em atributo `style=` e tabela no lugar de grade: cliente de e-mail (o
Gmail à frente) descarta `<style>` e classe, e a mensagem chegaria crua. Vai junto uma
versão em texto puro, porque e-mail que chega vazio num celular antigo é o mesmo que não
chegar.

As tabelas têm **duas colunas** — o que a linha é, e quanto custa — porque quatro não
cabem em 390px de celular, e e-mail que rola de lado não é lido. Cada lista entra com no
máximo 12 linhas (`LINHAS_NO_EMAIL`) e diz quantas ficaram de fora.

O botão **Ver prévia** abre o e-mail como ele vai chegar, sem mandar nada.

## Como ligar

1. Abrir **Alertas** no sistema: servidor, porta, quem envia e para quem mandar já vêm
   preenchidos com os da loja. Só falta a senha de `naoresponder@cabanadojacaranda.com.br`.
2. Usar **Enviar e-mail de teste** e conferir a caixa de entrada — e também o spam, que é
   onde a primeira mensagem costuma cair.
3. Marcar **mandar os relatórios** e salvar.

## No servidor

- Tarefa `\Cabana\CabanaRelatorios`, 24 gatilhos diários (um por hora cheia), rodando
  `scripts\relatorios.ps1`.
- Log em `C:\cabana-sistema\logs\relatorios.log`, só com o que houve (hora sem nada devido
  não escreve linha).
- À mão, para conferir: `python manage.py enviar_relatorios --rotina diaria --forcar`.


## O Telegram (1.24.0)

> *"quero junto ao e-mail também seja enviado notificação pelo telegram"* — Edson,
> 11/10/2026.

O e-mail leva o relatório inteiro, com as tabelas. O Telegram chega no bolso em segundos
e leva o que faz parar e olhar: a manchete, os números e as três primeiras linhas de cada
bloco, com o endereço do sistema no fim.

### Como ligar, uma vez só

1. No Telegram, procurar **@BotFather**, mandar `/newbot` e dar um nome ao robô. Ele
   responde com um **token**.
2. Colar o token na tela de Alertas e salvar. Ele fica gravado cifrado, como a senha do
   e-mail, e o sistema nunca o mostra de volta.
3. Mandar qualquer mensagem para o robô no Telegram e clicar em **Descobrir a conversa**.
   O robô não consegue escrever para quem nunca falou com ele primeiro, e o número do chat
   não aparece em lugar nenhum visível do aplicativo — por isso o botão existe.
4. Marcar **mandar aviso no Telegram** e usar o botão de teste.

Para o aviso ir a mais de uma pessoa: criar um grupo, pôr o robô dentro e descobrir a
conversa do grupo do mesmo jeito.

### Como ele é feito

- `apps/alertas/telegram.py`: um POST para `api.telegram.org` com `urllib`, sem biblioteca
  nova — o servidor da loja atualiza por zip e não tem internet garantida.
- **Texto puro, sem Markdown.** Nome de produto da loja tem `*`, `_` e `(` à vontade, e
  qualquer formatação obrigaria a escapar caractere a caractere, com risco de a mensagem
  chegar quebrada ou pela metade.
- O erro vira frase de loja, como no e-mail: token não reconhecido, conversa não
  encontrada, robô bloqueado, sem internet, relógio do Windows errado.
- A mensagem é cortada em 3.500 caracteres antes de o Telegram cortar em 4.096: cortada
  por ele, ela perde o fim, que é onde está o link.

### Os dois caminhos são independentes

Cada um tem o seu interruptor e a sua pendência do dia (`EnvioDeRelatorio.canal`). O
Telegram sai com o e-mail desligado e vice-versa — o aviso no celular não pode depender da
senha de uma caixa de e-mail. O relatório é montado uma vez e serve aos dois: algumas
dessas contas passam por onze mil produtos.

Na tela de **Últimos envios**, cada linha diz por onde saiu e para quem.
