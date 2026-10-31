# Por que o login ficou lento, e o que foi feito (1.34.0)

Pedido do Edson em 14/10/2026: *"login para acessar o sistema está um pouco lento"*.

## O que foi medido, antes de mexer

Medido de ponta a ponta, sobre a foto de verdade da loja (11.274 produtos), em
14/10/2026 e conferido de novo em 15/10/2026:

| Passo | Antes | Depois |
|---|---|---|
| `POST /sistema/entrar/` (conferir a senha) | 0,31 s | 0,31 s |
| `GET /sistema/painel/geral/` (a primeira tela) | **103 consultas**, 1,5 a 2,7 s | **38 consultas**, 0,1 a 0,3 s |
| O que a pessoa sente | ~2,5 s | ~0,5 s |

**A contagem de consultas é o número firme; o tempo varia com a carga da máquina.** Dois
segundos aqui podem ser quatro no servidor da loja ou um e meio, e medir de novo no mesmo
minuto dá outro número. A conta de 103 para 38 consultas não varia.

O login em si nunca foi o problema. O que pesava era a **primeira tela**, que é a Visão
geral — a tela que aparece logo depois de entrar. Quem digita a senha e espera dois
segundos e meio não tem como saber que a espera é da tela seguinte: para a pessoa, "o
login está lento".

## A causa

As três contas da abertura — o painel, a Visão geral e "O que fazer agora" — rodam sobre
os onze mil produtos da foto do SET e levam juntas cerca de 2,2 segundos. Elas ficam em
cache, e **a chave do cache carrega o número da importação**, de propósito: foto nova,
números novos; número velho seria pior que número lento.

Só que isso significa que **cada sincronização derruba o cache**. A tarefa das 08:30
apagava as contas, ia embora, e a conta de 2,2 s sobrava para a primeira pessoa que
abrisse o sistema. Três sincronizações por dia (08:30, 12:30, 19:30), três pessoas pagando
a conta — e sempre as mesmas três, porque são as três pessoas que abrem o sistema de
manhã, depois do almoço e no fim do dia.

A conta tem que ser feita de qualquer jeito. A escolha é só sobre **quem espera**: a tarefa
agendada, que já está rodando e não tem pressa, ou a pessoa, que acabou de digitar a senha.

## O que mudou

1. **O cache saiu da memória e foi para arquivo**, em `dados\cache`
   (`CABANA_CACHE` no `cabana.env`, gravado pelo instalador). Isto é o que torna o resto
   possível: quem importa é a tarefa `CabanaImportacao` e quem mostra a tela é o serviço
   `CabanaSistema`. São **dois processos**, e com o cache na memória de cada um a conta
   feita pela tarefa nunca chegaria ao serviço. A pasta fica fora do que a atualização
   troca, então a cópia sobrevive a um `atualizar.ps1` — e é por isso que a chave carrega
   também a **versão do sistema**: o que está guardado é o objeto Python pronto, e a forma
   dele muda de uma versão para outra.
2. **A importação adianta as contas** (`apps/painel/aquecer.py`), inclusive quando não há
   backup novo: aí a foto que continua valendo é a ANTERIOR, e é dela que a tela sai.
3. **A tarefa de hora em hora refaz a conta do dia** (`enviar_relatorios`, junto com o
   vigia do backup). A chave carrega o DIA, porque a Visão geral conta conta vencida e
   conta a vencer, e isso vira à meia-noite sem ninguém tocar em nada. Em 23 das 24 voltas
   isso custa uma leitura de arquivo.
4. **O teto do mês saiu do banco em vez da memória.** A lista de compra e a agenda da
   abertura chamavam a função que monta a tela "Antes de comprar" inteira — onze mil
   produtos para a memória, tabela de todos os fornecedores — para ler só o teto e jogar o
   resto fora. Agora é `limite.teto_de`, uma consulta de soma.
5. O túnel do HTTPS parou de esperar o pacote seguinte antes de repassar o que já tem
   (`TCP_NODELAY` em `apps/core/tunel_tls.py`), que custava até 40 ms por ida e volta.

## O que NÃO foi mexido, e por quê

**O embaralhamento da senha.** Custa 0,31 s porque são um milhão de voltas de
PBKDF2-SHA256, que é o padrão do Django 5.2. As alternativas foram medidas aqui:

| Jeito | Custo por login |
|---|---|
| PBKDF2 com 1.000.000 de voltas (o atual) | 0,31 s |
| PBKDF2 com 600.000 (o mínimo que a OWASP recomenda) | 0,19 s |
| scrypt (o primeiro da lista do Django) | 0,22 s |

Economizaria 0,12 s e trocaria o formato da senha de todo mundo — numa máquina que não dá
para acompanhar daqui, e em que senha que para de funcionar é a loja sem sistema. Não
vale: 0,12 s não é o que a pessoa está sentindo, e os 1,8 s que ela sentia estavam na tela.

## A primeira tela virou o Dashboard (1.43.0)

Desde a 1.43.0 quem é da gerência cai no **Dashboard** ao entrar, e não mais na Visão geral
(pedido de 31/10/2026). Pelo mesmo motivo de cima, ele entrou no que a importação e a tarefa
de hora em hora deixam pronto: o período padrão, sem filtro, fica guardado com a mesma chave
da Visão geral (`"dashboard:12m:" + chave(importacao)`). Medido na máquina de
desenvolvimento: **36 consultas e cerca de 0,13 s** guardado, contra 90 consultas e 1,3 s
com o cache limpo. O teste `test_aquecer_guarda_as_contas_da_abertura` confere que a
chave do Dashboard está entre as que a importação deixa prontas.

## Como conferir que continua valendo

A medida se refaz sozinha, com um `Client` do Django e o `CaptureQueriesContext` em volta
do `GET /sistema/painel/geral/`: uma vez com o cache limpo (é o que a primeira pessoa
pagava) e uma vez depois de `aquecer.aquecer_a_foto_de_hoje()` (é o que ela paga agora).

`apps/painel/tests/test_aquecer.py` trava as três partes: que a importação deixa a conta
pronta (do backup até a tela, com o Firebird trocado por um dublê), que a tarefa de hora em
hora refaz a conta do dia, e que **o cache de produção não é o de memória** — este último
existe para ninguém "simplificar" o cache de volta para dentro do processo, que é o defeito
original.
