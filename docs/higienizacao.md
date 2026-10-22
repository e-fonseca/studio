# Higienização: o que o sistema limpa sozinho

O sistema guarda uma foto inteira dos dados do SET a cada sincronização e, desde a
1.25.0, sincroniza três vezes por dia. Isso é de propósito — é o que faz a conta de
"sincronizar substitui, não soma" ([sincronizacao-nao-soma.md](sincronizacao-nao-soma.md))
— mas significa que o disco e o banco crescem sozinhos todo dia. A higienização é
o que tira o que já não serve.

## Os comandos

No PowerShell, como administrador, no servidor da loja:

```
# ver o que tem para limpar, sem limpar nada
powershell -ExecutionPolicy Bypass -File C:\cabana-sistema\scripts\higienizar.ps1 -Conferir

# limpar agora
powershell -ExecutionPolicy Bypass -File C:\cabana-sistema\scripts\higienizar.ps1

# atualizar o sistema; anda junto com os de cima, a pedido do Edson (19/10/2026)
powershell -ExecutionPolicy Bypass -File C:\instalacao\atualizar.ps1
```

**Os dois comandos nunca aparecem sozinhos.** Quem abre o PowerShell no servidor
costuma fazer as duas coisas na mesma visita, e procurar o outro comando em outro
lugar da página custa tempo de quem está no servidor. Vale para a tela Ficha técnica,
para o `LEIA-ME.txt` do pacote e para qualquer lugar novo que mostre um dos dois.

Roda sozinha todo dia às 03:40, pela tarefa `\Cabana\CabanaHigienizacao`: depois da
sincronização da madrugada, depois do backup das 23:30 e antes de a loja abrir.
O registro de cada limpeza fica em `logs\higienizacao.log`.

Direto no Django, se for preciso (dentro de `C:\cabana-sistema\app`):

```
..\python\python.exe manage.py higienizar           # só confere
..\python\python.exe manage.py higienizar --fazer   # limpa
```

## O que sai

| O que | Regra | Por quê |
| --- | --- | --- |
| Cópia do banco do SET (`dados\copia-set`) | sai inteira | A importação copia o backup para ler num Firebird próprio e nunca reaproveita a cópia: a sincronização seguinte copia de novo. Depois de ler, é um banco do SET de centenas de MB parado no disco — **com nome e CPF de cliente dentro**. É a primeira tarefa da lista por causa disso, e não pelo espaço. |
| Fotos dos dados do SET | ficam as 10 últimas sincronizações (`IMPORTACAO_MANTER`) | Produtos, contas, clientes, fornecedores, compras, vendas e **turnos do caixa**. |
| Sessões vencidas | o prazo já passou | Uma por entrada no sistema; ninguém as apagava. |
| Registro de acesso | 90 dias | Quem entrou e quem errou a senha. O bloqueio por senha errada fica: mora em outra tabela, a que o sistema consulta para saber quem está bloqueado agora. |
| Envios de relatório | 90 dias | Um registro por e-mail e por mensagem de Telegram. A tela de Alertas mostra os últimos e a agenda só olha o dia e a semana correntes. |
| Sincronizações sem dados | 90 dias, e **nunca** as 60 que a tela mostra | Tentativa sem backup novo ou que falhou. Com três por dia, virou a linha que mais aparece no histórico. |
| Anexos órfãos | arquivo sem registro | Apagar o anexo na tela tira a linha do banco e deixa o arquivo; é assim que o Django funciona. |

No fim, um `VACUUM (ANALYZE)`. Sem `FULL` de propósito: `FULL` tranca a tabela
inteira e o sistema tem que ficar no ar enquanto a limpeza roda.

## O que não sai nunca

Auditoria, ficha de fornecedor, pagamento previsto, inventário e contagem, extrato
bancário conferido, usuários, processos e os backups do próprio sistema
(`C:\cabana-sistema\backups`, que já guardam 14 dias e se limpam no `backup.ps1`).

A regra: **sai só o que o sistema sabe refazer sozinho na próxima sincronização.**
O que uma pessoa digitou fica.

E, como em todo o resto: nada aqui encosta no SET. A higienização não abre o
`DADOS-SET.FDB`, não fala com o Firebird do SET e não escreve em `C:\Set Sistemas`.

## O arquivo do banco não encolhe

Apagar linha no PostgreSQL não devolve espaço na hora: o lugar fica marcado como
livre e é reaproveitado na gravação seguinte. O `VACUUM` é o que faz essa marcação
acontecer agora. Por isso o comando mostra o tamanho do banco e diz isso em uma
linha, em vez de mostrar "antes" e "depois" — depois de um `VACUUM` o arquivo chega
a ficar alguns MB **maior**, porque ele grava as contas novas, e quem lê "182 MB
antes, 183 MB depois" conclui que a limpeza não funcionou. Funcionou.

## O bug que deu origem a isto

`limpar_antigas` (em `apps/importacao/servicos.py`) apagava as fotos antigas de
produto, conta, cliente, fornecedor, compra e venda — e esquecia o caixa. Os turnos
têm `importacao` como as outras fotos, 950 por sincronização, cada um com os seus
movimentos: ninguém os apagava nunca. Com três sincronizações por dia seriam
uns 15 mil registros por dia, para sempre.

A correção foi tirar a lista de modelos de dentro da função que apaga e pôr em
`fotos_fora_do_limite`, que a limpeza automática e o `higienizar` usam juntas. A
lista agora é uma só; não dá mais para uma andar sem a outra. O teste que prende
isso é `apps/core/tests/test_higiene.py::FotosDoCaixaTest`.

## A pasta que NÃO entra na higienização: `dados\cache`

Desde a 1.34.0 as contas da tela de abertura ficam guardadas em `dados\cache`
(`CABANA_CACHE`), e não na memória do processo — ver
[login-rapido.md](login-rapido.md). Essa pasta **se limita sozinha** e por isso não tem
tarefa aqui:

- cada entrada vence em 36 horas;
- o Django conta os arquivos antes de gravar e, ao chegar em 300, apaga um terço deles;
- são três entradas por foto por dia, com três sincronizações ao dia: cerca de nove
  arquivos, e o teto de 300 demora um mês para ser alcançado.

Apagar essa pasta à mão não quebra nada: a próxima sincronização, ou a tarefa de hora em
hora, refaz as contas. O que acontece é só a próxima pessoa a entrar esperar os ~2 s uma
vez, que é o defeito que a 1.34.0 consertou.

Na 1.34.0 o mesmo erro de origem desta página apareceu de novo, do outro lado: o `except`
da importação, que desfaz a foto de quem parou no meio, apagava produto, conta, cliente e
caixa — e esquecia compra, venda, ficha de fornecedor e venda mês a mês. Agora ele usa
`_apagar_a_foto`, que percorre a MESMA lista de `_modelos_da_foto`. São três usos de uma
lista só: a limpeza automática, o `higienizar` e o desfazer.
