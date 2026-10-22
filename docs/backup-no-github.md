# Backup do código no GitHub

Guarda uma cópia do **código do sistema** fora do servidor da loja, num repositório do
GitHub, e sobe sozinho no fim de cada atualização. Tela: **Apoio > Backup**
(`/sistema/backup/`), só para o perfil Administrador gerência.

## O que vai e o que não vai

Vai o programa: `.py`, `.html`, `.css`, `.js`, `.md`, `.ps1`, `.sh`, `.txt`, `.json`,
`.cfg`, `.sql`, `VERSAO`, `requirements.txt` — o que está dentro da pasta `app`.

**Não vai nada de dado.** O banco de dados não sobe, e nem poderia: ele tem nome de
cliente vindo do SET, extrato bancário conferido e nota fiscal de fornecedor. Os anexos
(`dados\anexos`) e os arquivos gerados (`static` coletado) também ficam fora. Pastas
inteiras de fora: `.git`, `var`, `__pycache__`, `node_modules`, `media`, `staticfiles`,
`backups`, `dados`, `logs`.

A escolha é por **inclusão**, não por exclusão: um arquivo que ninguém listou fica de
fora: esquecer uma inclusão deixa de salvar um arquivo, esquecer uma exclusão vaza um.
Por cima disso, `envio._proibidas()` descobre em tempo de execução onde estão
`MEDIA_ROOT` e `STATIC_ROOT` e poda as duas, mesmo que o servidor as tenha posto em
outro lugar.

Limites: 2 MB por arquivo e 60 MB no total. Passando disso o envio para e explica — é
sinal de que entrou no backup algo que não é código.

O backup do **banco** continua sendo o local, `scripts\backup.ps1`, todo dia às 23:30 em
`C:\cabana-sistema\backups` (14 dias). São dois backups com papéis diferentes: o do
GitHub devolve o sistema, o local devolve os dados.

## Dois caminhos até o GitHub (1.33.1)

O código chega ao repositório por dois caminhos independentes, e é bom saber qual é qual
antes de olhar a tela:

| | De onde sai | O que cobre | O que exige |
|---|---|---|---|
| **Do projeto** | Do lugar onde o sistema é escrito | Toda versão entregue | Nada. Já acontece |
| **Do servidor** | De `C:\cabana-sistema\app` | O que mudar NO SERVIDOR | O token na tela Backup |

O primeiro é quem encheu o repositório em 14/10/2026 e é quem o mantém em dia a cada
entrega — sem token, sem clique, sem nada para a loja fazer. O segundo é o que esta
tela liga, e serve para o que o primeiro não alcança: arquivo mexido direto no servidor,
e a garantia de que o que está INSTALADO é o que está guardado.

Por isso a tela, sem token, diz que *este servidor* não está mandando nada — e não que
não existe cópia em lugar nenhum, que é o que ela dizia antes da 1.33.1 e que o sistema
não tem como saber.

## O repositório recém-criado (armadilha, 1.33.1)

Um repositório que acabou de ser criado não tem commit nenhum, e nesse estado o GitHub
responde **409 `Git Repository is empty.`** — e não 404 — quando se pergunta em que
commit está o ramo. Como esse é o estado de todo repositório na primeira vez, o 409 caía
justamente no PRIMEIRO envio, que é o único que todo mundo faz. O recado mandava tentar
de novo, e tentar de novo dava no mesmo.

Conferido contra a API de verdade em 14/10/2026, no repositório do Edson:

```
GET /repos/e-fonseca/sistema/git/ref/heads/main
409 {"message": "Git Repository is empty."}
```

Hoje a **leitura** entende os dois jeitos de o GitHub dizer "ainda não há nada aqui"
(404 e 409-vazio). A **escrita** funciona normalmente em repositório vazio — blob,
árvore, commit e ramo, nessa ordem —, então um 409 vindo de uma escrita continua sendo
erro de verdade: é o ramo ter se mexido no meio do envio.

Fica a lição para o dublê de teste: ele devolvia `None` para ramo que não existe, que é
o que o código *esperava*, e por isso o teste do repositório vazio passava enquanto o
caso real quebrava. Os testes de `ORepositorioVazioTest` montam a resposta HTTP como ela
chega, sem dublê.

## Como ligar (uma vez)

O repositório já vem preenchido desde a 1.32.0: `e-fonseca/sistema`, que foi o que o
Edson indicou em 14/10/2026 (*"fazer conexão com o diretório sistema, destinado para
este projeto no github"*). É o mesmo princípio da tela Alertas, que já abre com o SMTP
da Hostinger: o que fica para a pessoa é só o segredo. Trocar o endereço na tela
sobrescreve o que veio de fábrica, e a constante é `models.REPOSITORIO_PADRAO`.

1. Conferir, na tela Backup, que o repositório é o certo e que ele existe e é
   **privado** no GitHub.
2. Clicar no link da própria tela, que vai direto para
   <https://github.com/settings/personal-access-tokens/new>, e gerar um token com acesso
   só a esse repositório e permissão **Contents: Read and write**. No prazo, quanto mais
   longo melhor: desde a 1.33.0 o sistema avisa antes de vencer.
3. Na tela Backup, colar o token e gravar. **Acabou.**

Desde a 1.33.1 não existe passo 4. Gravar o token liga o envio automático (a marca já
nasce marcada, em `forms`) e manda a primeira cópia na hora (`views._ligar_de_vez`), com
o resultado na própria tela. Antes, o token entrava e a tela ficava dizendo que estava
tudo preenchido e que nada tinha subido, esperando alguém achar o botão *Enviar agora* —
que continua lá, para reenviar quando se quiser.

Só a PRIMEIRA cópia sai do gravar. Trocar o token de um backup que já funciona não
reenvia o sistema inteiro: a atualização seguinte manda o que mudar.

O token é a única parte que o sistema não pode preencher sozinho: ele é a credencial da
conta do GitHub dele, e um token colado aqui por outra mão valeria tanto para gravar
quanto para ler. Tudo o que vinha DEPOIS dele o sistema faz.

O endereço aceita as quatro formas: `dono/repositorio`,
`https://github.com/dono/repositorio`, com `.git` no fim e `git@github.com:dono/repo.git`.

O token é guardado **cifrado** (`apps/alertas/cifra.py`, a mesma cifra da senha do e-mail
e do token do Telegram), nunca volta para a tela e nunca entra na auditoria — a auditoria
registra apenas que existe um token guardado. Ele viaja só no cabeçalho
`Authorization` da chamada, nunca em linha de comando, onde apareceria na lista de
processos do Windows.

## Como sobe

Sem git instalado no servidor: o envio fala direto com a **API do GitHub**
(`apps/backup/github.py`, só com a biblioteca padrão do Python). Para cada arquivo o
sistema calcula o mesmo SHA-1 que o git calcularia (`blob <tamanho>\0<conteúdo>`), compara
com o que já está no repositório e manda só o que mudou; depois cria uma árvore sobre a
anterior (`base_tree`), um commit e move o ramo. Primeiro envio manda tudo; os seguintes,
só a diferença.

A mensagem do commit sai pronta: `Cabana 1.31.0 — 14/10/2026 19:40 (servidor CABANA-PC)`.

## Quando sobe

- **No fim de cada atualização**, dentro do `atualizar.ps1`, depois de o instalador
  terminar bem (`manage.py enviar_backup`). Se o envio falhar, a atualização **não** falha:
  o sistema já está no ar, e o motivo fica na tela Backup.
- **A qualquer hora**, pelo botão Enviar agora.
- **Sozinho, quando a última cópia passa de uma semana** (1.33.0). Quem dispara é a tarefa
  de alertas, que já acorda de hora em hora — ver o vigia, mais abaixo.

Na linha de comando, de dentro de `C:\cabana-sistema\app`:

    ..\python\python.exe manage.py enviar_backup            # respeita o ligado/desligado
    ..\python\python.exe manage.py enviar_backup --forcar    # manda mesmo desligado

Sai com código 0 quando não está configurado ou está desligado (não é erro, é a loja não
ter pedido) e 1 só quando o envio deu erro de verdade.

## O que a tela mostra

Quantos arquivos iriam no envio, o endereço do repositório, o que falta preencher, e do
último envio: quando foi, se deu certo, o começo do commit e quantos arquivos mudaram.
Cada envio também fica na auditoria (`backup.enviado` ou `backup.envio_falhou`).

Erro de GitHub chega traduzido: token recusado (401), sem permissão de escrita no
repositório (403), ramo que andou no meio do caminho (409) e repositório inexistente.

Desde a 1.33.0 o **estado** vem primeiro na tela, antes da explicação: quem abre esta tela
quer saber se a cópia de fora do servidor existe hoje, não como ela funciona.

## O vigia (1.33.0)

Entrou a pedido do Edson em 14/10/2026: *"Acessar de forma automática o github, sem ação
humana, método automatizado"*, dentro do foco que ele deu ao projeto, *"tentar automatizar
tudo para que possamos escalonar a produtividade da empresa"*.

**O que não dá para automatizar, e por quê.** O GitHub exige uma autorização dada por uma
pessoa em qualquer caminho — token, aplicativo (GitHub App), chave de implantação, fluxo de
dispositivo. Isso é proposital: é o que impede um programa de escrever na conta de alguém
sozinho. Não há jeito de o sistema se autorizar, e prometer o contrário seria mentira. O
que o vigia faz (`apps/backup/vigia.py`) é tirar da pessoa tudo o que sobra depois disso.

**Reenvia sozinho.** Se a última cópia que CHEGOU ao GitHub tem mais de sete dias, o
sistema tenta de novo por conta própria, na tarefa de alertas que já acorda de hora em
hora. Isso cobre a atualização que falhou no meio, o minuto sem internet, e o caso mais
comum: o mês sem atualização nenhuma. Quando nada mudou, o envio compara os resumos e não
manda arquivo nenhum, então reenviar é barato. Uma tentativa por dia, no máximo — o GitHub
trata insistência como abuso.

Para isso o modelo passou a guardar `ultimo_sucesso_em` separado de `ultimo_envio_em`
(migração 0003): com um token vencido, a última tentativa é de hoje e a última cópia é de
três meses atrás, e é a segunda data que diz se a loja está coberta.

**Avisa antes de vencer.** O GitHub manda
`github-authentication-token-expiration` em toda resposta autenticada com token de escopo
fino. O sistema lê esse cabeçalho uma vez por dia e guarda a data; a dez dias do
vencimento começa a pedir token novo. A leitura distingue *"o GitHub disse que este token
não vence"* de *"não consegui perguntar"*: sem essa diferença, um minuto sem rede apagaria
a validade conhecida e o aviso desapareceria calado.

**Fala por e-mail e Telegram.** Virou uma rotina diária de alertas (`Rotina.BACKUP`), e ela
é **calada quando está tudo bem** — relatório que chega todo dia dizendo "está tudo certo"
é relatório que ninguém abre. Ela tem notícia em cinco casos: nunca foi configurado, está
configurado e desligado, o token venceu, o token vence em até dez dias, e a última cópia
passou de uma semana.

O vigia nunca levanta erro: ele mora no caminho da tarefa de alertas, e derrubá-la por
causa do GitHub deixaria a loja sem os relatórios.
