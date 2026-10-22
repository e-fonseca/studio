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
