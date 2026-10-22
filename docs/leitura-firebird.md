# Leitura do banco do SET (Firebird) sem impacto

Autorização do Edson em 05/10/2026: ler ou consultar o banco Firebird do SET se for possível
sem impacto; senão, só relatórios.

## Resposta curta

Dá para fazer sem impacto **lendo uma cópia**, nunca o banco em uso. O sistema novo
restaura em uma pasta própria a cópia de segurança que o SET já gera (pasta `BKPS`) e lê
essa cópia com um Firebird separado, embutido no sistema novo. O banco `DADOS-SET.FDB`, o serviço
do Firebird do SET e a porta 3050 continuam intocados.

O custo é a defasagem: os dados ficam tão atualizados quanto a última cópia (se a cópia for
diária, os dados são de ontem). Para compras e diagnóstico, isso basta.

## Por que não ler o banco em uso

| Risco de ler o `DADOS-SET.FDB` direto | Efeito na loja |
|---|---|
| Consultas pesadas disputam CPU e disco com o SET num servidor de 4 núcleos | SET lento no caixa |
| No Firebird, uma leitura longa segura a limpeza de versões antigas dos registros | O banco cresce e o SET fica lento com o tempo, mesmo depois da leitura acabar |
| Exige criar usuário no Firebird do SET (mudança na configuração dele) | Atualização do SET pode desfazer ou conflitar |
| Abrir o arquivo diretamente, sem passar pelo servidor | Pode corromper o banco. **Nunca fazer** |

## Como funciona a leitura da cópia

1. **Fonte:** o arquivo mais recente da pasta `C:\Set Sistemas\BKPS`, só lido, nunca movido nem apagado.
   Copiado fora do horário da loja para `C:\cabana-sistema\espelho\` com prioridade baixa de disco.
2. **Restauração:** `gbak` do Firebird **embutido do sistema novo** (mesma versão 4.0.x, instalado na
   pasta do sistema novo, sem serviço e sem porta) cria um banco espelho separado.
3. **Conferência:** o espelho é validado (`gfix -v`); se a cópia estiver incompleta, a carga é
   recusada e o sistema avisa, mantendo os dados anteriores.
4. **Leitura:** consultas somente leitura, em transações curtas, extraem produtos, estoque, vendas e
   compras para o PostgreSQL do sistema novo, como uma importação de relatório, com data de corte
   = horário da cópia.
5. **Conferência com o SET:** nas primeiras semanas, os totais do espelho são comparados com os
   relatórios do SET (estoque total, vendas do mês). Só depois o espelho vira fonte principal.
6. **Descarte:** o espelho é apagado depois da carga; guarda-se só o resultado e o hash da cópia usada.

Se a pasta `BKPS` só tiver cópias do arquivo `.FDB` feitas com o banco aberto (e não arquivos de
backup do `gbak`), elas podem estar inconsistentes. Nesse caso a alternativa é um `gbak` de leitura
agendado de madrugada, que lê o banco pelo servidor do SET como uma consulta só; isso é avaliado e
medido antes, com o Edson.

## Cuidados

- **Estrutura não documentada:** as tabelas do SET não têm documentação pública. O mapeamento é
  descoberto na cópia e conferido contra os relatórios; nomes parecidos não são aceitos como prova.
- **Atualizações do SET** (há um AtualizadorSet no servidor) podem mudar a estrutura. Cada carga
  confere as tabelas e colunas esperadas e para com aviso se algo mudou, em vez de importar errado.
- **Contrato com a SET Sistemas:** convém confirmar que o contrato não proíbe ler a cópia do
  próprio banco da Cabana. Os dados são da Cabana, mas o suporte deles pode se recusar a atender
  problemas que atribuam a isso.
- **Dados pessoais:** só se extrai o necessário (produtos, quantidades, valores, datas). Dados de
  clientes ficam de fora.
- **Senha do banco:** se for necessária, fica em variável protegida no servidor, nunca no código nem em mensagens.

## O que preciso para começar

1. Lista da pasta `C:\Set Sistemas\BKPS`: nomes, tamanhos e datas dos arquivos (só a lista, sem enviar os arquivos).
2. A hora em que o SET faz essa cópia e se ela roda todo dia.
3. Confirmação de que o contrato com a SET não proíbe a leitura da cópia.

A descoberta da estrutura das tabelas precisa rodar no servidor (este ambiente não alcança a VPN).
Ela é feita por um script de leitura sobre a cópia restaurada, que eu preparo e que roda numa pasta própria.

## Como ficou implementado (05/10/2026)

Decisão do Edson em 05/10/2026: a cópia do backup do dia é o plano A; a importação de relatórios
do SET fica como plano B (contingência).

O que roda no servidor:

1. Tarefa `\Cabana\CabanaImportacao`, **três vezes por dia** (padrão 08:30, 12:30 e
   19:30, pedido do Edson em 13/10/2026), executa `scripts\importar.ps1`, que chama
   `python manage.py importar_set --automatica`. São três gatilhos num mesmo agendamento,
   e os horários ficam em `CABANA_IMPORTACAO_HORAS`, separados por vírgula.
2. O sistema olha a pasta indicada em `CABANA_SET_BACKUP` (padrão
   `C:\backup-Set\Cabana\Set-Cabana`, informado pelo Edson em 05/10/2026), **inclusive as
   subpastas**, e escolhe o arquivo `.FDB` ou `.FBK` com a data mais nova; arquivo vazio é
   ignorado, porque é backup ainda sendo gravado ou que falhou. Copia esse arquivo para
   `dados\copia-set\set.fdb` e, sendo `.FBK`, restaura com o `gbak` próprio. **A origem é só
   lida**: o arquivo do SET não é movido, apagado nem aberto para escrita. A cópia não fica
   guardada: a higienização das 03:40 apaga `dados\copia-set` todo dia, porque é um banco
   do SET inteiro, com dado pessoal de cliente dentro, e a sincronização seguinte copia de
   novo do zero ([higienizacao.md](higienizacao.md)).
   Se o arquivo escolhido for o mesmo da importação anterior (mesmo caminho, mesma data, mesmo
   tamanho), a execução é registrada como "Sem backup novo" e os dados anteriores continuam
   valendo, em vez de reprocessar o mesmo conteúdo.
3. A leitura usa um **motor Firebird próprio** em `C:\cabana-sistema\firebird`, com
   `Providers = Engine13` no `firebird.conf`. Sem `Remote` e sem `Loopback`, esse motor não
   consegue falar com nenhum servidor Firebird: nem o do SET, nem a porta 3050.
   O instalador monta essa pasta a partir do `Firebird-4.0.6.3221-0-x64.zip` que vem dentro do
   pacote (ou de um Firebird 4 **de 64 bits** já presente no servidor, copiado sem alterar a
   origem). A versão 4.0 é a certa porque a cópia do banco do SET é ODS 13, o formato do
   Firebird 4. Os bits têm que casar com o Python do sistema, que é de 64: o Firebird que
   acompanha o SET é de 32 bits e, carregado no Python de 64, o Windows recusa com
   `[WinError 193] %1 não é um aplicativo Win32 válido`. O instalador confere a arquitetura no
   cabeçalho de cada `fbclient.dll` antes de aceitá-lo, e a leitura confere de novo antes de
   abrir a cópia.
4. Cada execução grava um registro em `Importações` (tela do sistema): resultado, data de corte,
   produtos lidos, duração e, quando falha, o motivo. Nenhuma importação pela metade entra no
   painel: ou conclui, ou os dados da anterior continuam valendo.
5. O painel mostra sempre a data dos dados. Até 1 dia de atraso é normal; de 2 a 3 dias aparece
   aviso amarelo; a partir de 4 dias, aviso vermelho em todas as telas, porque decidir compra com
   dado velho é pior que não decidir.

Ainda pendente para a importação automática funcionar:

- **Horário em que o backup do SET termina**, e quantas vezes por dia ele roda. A pasta já
  foi informada (`C:\backup-Set\Cabana\Set-Cabana`). Desde a 1.25.0 a importação roda às
  08:30, 12:30 e 19:30, mas ela só enxerga o que estiver no arquivo de backup: se o SET
  gerar um backup por noite, as três sincronizações acham o mesmo arquivo e terminam como
  **Sem backup novo**. É o item 10 de [perguntas-pendentes.md](perguntas-pendentes.md).
- A tarefa roda como SERVIÇO DE REDE. Essa conta precisa **ler** a pasta do backup. Se o backup
  for salvo em disco externo ou pasta de rede, a importação vai falhar por permissão e o painel
  mostra o motivo; nesse caso o caminho é copiar o backup para uma pasta local.
- Prazo de entrega por fornecedor: o histórico de compras do SET dá mediana zero para a maioria,
  então a sugestão de reposição usa prazo estimado. Com os prazos reais, a sugestão fica firme.
