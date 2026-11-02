# Sessão: quanto tempo alguém fica logado (1.20.1)

## O que o Edson relatou

Em 08/10/2026: "revisar sessao aberta da area logada do sistema, agora qdo eu fecho e
abro, reabre de onde estava, isso posso considerar uma brecha de segurança". Ele está
certo. O computador do sistema fica no balcão da loja e todo mundo passa por ali.

## Por que o cookie de sessão não bastava

`SESSION_EXPIRE_AT_BROWSER_CLOSE = True` existe desde a primeira entrega, então o cookie
do sistema já é um cookie de sessão: em tese ele morre quando o navegador fecha.

Só que quem decide isso é o navegador, não o site. O Chrome **restaura cookies de
sessão** em três situações comuns, e todas acontecem na loja:

- quando está configurado em "Continuar de onde você parou" (restaura as abas e os
  cookies de sessão junto);
- quando continua rodando em segundo plano depois de a janela fechar (ícone na bandeja);
- quando a janela é fechada e reaberta rápido, pela restauração de sessão.

Não existe configuração do lado do site que impeça isso. Qualquer tentativa de resolver
no navegador (cookie com validade curta, JavaScript no `beforeunload`, `sessionStorage`)
é contornável e nenhuma delas vale como trava de acesso.

## O que resolve: duas travas no servidor

As duas estão em `apps/contas/sessao.py`, no middleware `LimiteDeSessaoMiddleware`, e
valem com o navegador aberto ou fechado, porque quem recusa a sessão é o servidor.

| Trava | Padrão | Conta a partir de | Variável no `cabana.env` |
| --- | --- | --- | --- |
| Tempo logado | 4 horas | da entrada | `CABANA_SESSAO_MAXIMA_HORAS` |
| Tempo parado | 30 minutos | do último acesso a uma tela | `CABANA_SESSAO_PARADA_MINUTOS` |

Estourado qualquer um dos dois, a próxima tela leva para a entrada com a explicação do
motivo. A sessão guarda duas marcas: `entrou_em` (gravada no login) e `visto_em`
(regravada no máximo uma vez por minuto, pelo `PASSO_DO_RELOGIO`, para não escrever no
banco a cada clique).

## Detalhes que custaram para acertar

- **Sessão sem as marcas não derruba ninguém.** Quem já estava logado quando a
  atualização sobe não tem `entrou_em`: o middleware marca a entrada naquele momento em
  vez de expulsar a pessoa no meio do trabalho. Sem `visto_em`, a entrada serve de
  último uso.
- **Trabalhar não derruba, parar derruba.** Cada requisição de alguém logado atualiza o
  `visto_em`; quem está usando o sistema nunca cai pela trava de parada, só pela das
  quatro horas.
- **O motivo aparece na tela de entrada**, em linguagem de loja, e não um "sessão
  expirada" seco: quem está no balcão precisa entender que não é defeito.

## Data para o acesso acabar (1.42.0)

Pedido dele em 31/10/2026, com a Cássia entrando no lugar da Bárbara: *"ficara no lugar da
barbara ate dia 12/11/2026"*. Até a 1.41.0 a única saída era alguém abrir a tela de usuários
no dia certo e clicar em Encerrar. Era também o "registrar delegações temporárias, bloquear
desligados e invalidar sessões" do briefing de 05/10/2026, que ficou sem a parte da data.

- **A data mora na conta** (`VinculoIdentidade.acesso_ate`, "último dia de acesso") e se
  marca na ficha da pessoa, em "Situação do acesso" (desde a 1.44.0; até ali era um quadro
  da tela de usuários), ou já na criação da conta. É inclusiva: "até 12/11" entra no dia 12
  inteiro.
- **A última pessoa que administra não se desliga pela data** (1.44.0): a auditoria registra
  `acesso.prazo_nao_cumprido` a cada dia, e a gerência resolve dando o acesso a outra pessoa
  (`controle-de-acesso.md`).
- **No dia seguinte a conta se desliga sozinha**, com o mesmo efeito do Encerrar: conta
  desligada, sessões abertas derrubadas, e a auditoria registra o motivo "Acesso combinado
  até 12/11/2026" com o serviço "data marcada para o acesso acabar".
- **Quem cumpre a data é um middleware** (`apps/contas/prazo.py`), não uma tarefa agendada
  nova: ele roda na primeira requisição de cada dia, de quem quer que seja, inclusive na
  tentativa de entrar da própria pessoa, antes de a senha ser conferida. Não há janela em
  que a conta vencida ainda entra, e não há mais um agendamento no servidor para instalar e
  vigiar. Uma vez por dia por processo: a conferência é uma consulta só.
- **Data que já passou é recusada** (ela desligaria a conta na hora sem ninguém ter pedido);
  para encerrar hoje, existe o Encerrar, com o motivo. Ninguém marca data no próprio acesso,
  pela mesma regra que impede desligar a si mesmo.
- **Liberar de novo tira a data** que acabou com o acesso; quem liberou marca outra, se for
  o caso. Senão a conta voltaria a se desligar no minuto seguinte.

## Trocar a própria senha (1.42.0)

A tela de usuários dizia "peça para ela trocar na primeira entrada" desde a 1.4.0, e não
havia onde trocar: a senha que a gerência escolhia valia para sempre. Agora o **nome no alto
da tela** abre "Trocar a minha senha" (`/sistema/senha/`), para todos os perfis, o vendedor
inclusive.

- Pede a **senha de agora**: quem acha o computador do balcão aberto não troca a senha de
  ninguém.
- As regras são as mesmas da senha que a gerência define (`AUTH_PASSWORD_VALIDATORS`: 12
  caracteres, nada parecido com o nome, nada só de números, nada das mais comuns), escritas
  em português de loja na própria tela.
- **As outras sessões caem** (o celular, outro computador); a de agora continua
  (`update_session_auth_hash`). A auditoria registra `acesso.senha_trocada`, nunca a senha.

## Esqueci a minha senha (1.43.0)

Pedido dele em 31/10/2026: *"adotar recurso de recuperar senha por e-mail cadastrado via
confirmação de código, senão tiver cadastro informe que não é possível, procure o
administrador do sistema."* Até a 1.42.0, senha esquecida era a gerência definir outra na
tela de usuários: o pedido tira esse passo da mão dela.

**O caminho** (tudo em `apps/contas/recuperacao.py`; as telas em `apps/contas/views.py`):

1. Na tela de entrada, **"Esqueci a minha senha"** (`/sistema/senha/esqueci/`). A pessoa
   digita o usuário ou o e-mail cadastrado.
2. Se a conta está ativa, tem senha e tem e-mail, sai para esse e-mail um **código de seis
   números**, que vale **15 minutos**, uma vez só, com **5 tentativas**. A tela seguinte
   (`/sistema/senha/esqueci/codigo/`) diz para onde foi, com o meio do endereço escondido
   (`ed•••@gmail.com`).
3. Com o código certo e uma senha que passe nas regras de sempre, a senha nova vale na hora:
   as sessões abertas caem, o bloqueio de senhas erradas (django-axes) sai junto, a
   auditoria registra `acesso.senha_recuperada` e **um segundo e-mail avisa da troca**, para
   quem não pediu ficar sabendo.

**Sem e-mail cadastrado**, a tela responde exatamente o pedido: *"Não é possível recuperar a
senha por aqui: esse usuário não tem e-mail cadastrado ou não está com o acesso liberado.
Procure o administrador do sistema."*

### As decisões de segurança

- **A mesma frase para tudo que não dá**: usuário que não existe, sem e-mail, desligado ou
  ainda sem senha. Frases diferentes contariam a quem tenta adivinhar quais usuários existem.
- **O código não fica guardado**: no banco vai só a assinatura dele (HMAC com a chave do
  sistema e a conta), e na auditoria nem isso. Quem lê o banco não troca a senha de ninguém.
- **Limites**: um código novo anula o anterior; pedir de novo em menos de um minuto não manda
  outro e-mail (quem clica duas vezes achando que não chegou não anula o código que está
  chegando); no máximo **5 códigos por conta por hora** e **10 pedidos por hora do mesmo
  computador**, contados pela auditoria (`acesso.codigo_pedido`, que registra todo pedido,
  o que deu e o que não deu, com o IP).
- **O código e a senha vão juntos**, e a senha fraca não gasta o código: dá para corrigir a
  senha sem pedir outro.
- **As duas telas não abrem o menu nem passam pelo login**, e não ficam no cache do
  navegador (`never_cache`). A segunda só abre para quem passou pela primeira na mesma
  sessão.

### Onde o e-mail se cadastra

- **A própria pessoa**, em "Trocar a minha senha" (o nome no alto da tela), no quadro
  "E-mail para recuperar a senha". Pede a senha de agora, como a troca de senha.
- **A gerência**, na ficha da pessoa, em "Senha e e-mail" (desde a 1.44.0; até ali era um
  quadro da tela de usuários). A lista de usuários marca quem está "sem e-mail: não recupera
  a senha sozinho".
- As duas mudanças vão para a auditoria (`acesso.email_definido`), com o meio do endereço
  escondido.

### Por onde o código sai

Pelo mesmo envio da tela Alertas (`apps/alertas/envio.enviar_avulso`): servidor, usuário e
senha da caixa `naoresponder@`. Basta isso; a lista de destinatários e o "mandar os
relatórios" não contam, porque o código vai ao e-mail de quem pediu. **Sem a senha da caixa
colada na tela Alertas, a recuperação responde que o envio de e-mail do sistema ainda não
está configurado** e manda procurar o administrador.

## A senha de novo e as sessões abertas (1.44.0)

Do prompt de controle de acesso (02/11/2026): "reautenticação para operações administrativas
sensíveis", "rotação de sessão na elevação de privilégio" e "sessões ativas e revogação".

- **A área de acessos pede a senha outra vez** (Usuários, a ficha de cada pessoa e Perfis e
  permissões), em `apps/contas/confirmacao.py`. Vale 15 minutos contados do último clique
  na área; ao confirmar, a sessão troca de chave (`cycle_key`), e cinco senhas erradas
  seguidas encerram a sessão. A mudança enviada depois que a janela fechou não é aplicada:
  a tela pede a senha e a pessoa refaz. Quem não administra recebe o 403 direto.
- **A sessão guarda, no login, o endereço e o navegador** (`marcar_aparelho`): "Chrome no
  Android", "Edge no Windows". A ficha da pessoa lista as sessões vivas (as que já passaram
  das quatro horas ou dos trinta minutos parada não aparecem: a próxima tela delas já cai)
  com o aparelho, de onde (rede da loja, VPN ou endereço seguro), a entrada e o último uso.
- **Encerrar uma sessão confere que ela é da pessoa da ficha**: a chave vem da tela, e sem
  essa conferência quem trocasse o número no endereço derrubaria a sessão de outra pessoa.
  A sessão em que a própria gerência está não se encerra pela ficha (para isso existe o
  Sair); na própria ficha, "Sair dos outros aparelhos" encerra todas menos a de agora.
- **Pelo endereço seguro (8443)** a ficha mostra "endereço seguro (https)" e não o IP: o túnel
  do HTTPS entrega a conexão ao sistema como se viesse do próprio servidor.
- Bloquear, encerrar o acesso e definir senha nova derrubam todas as sessões da pessoa, como
  já faziam o desligamento e a troca de senha.
