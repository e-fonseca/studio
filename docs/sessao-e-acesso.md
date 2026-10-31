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
  marca no quadro "Acesso com data para acabar" da tela de usuários (um formulário só, e não
  um por linha: a tabela já tem três ações por pessoa), ou já na criação da conta. É
  inclusiva: "até 12/11" entra no dia 12 inteiro.
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
