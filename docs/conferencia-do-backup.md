# Conferência do backup e importação forçada (1.23.0)

Pedido do Edson em 10/10/2026: um botão para forçar a atualização do sistema com o último
backup e, antes de importar, conferir o tamanho do arquivo, para avaliar a integridade, e
a data, para ter certeza de que é mesmo o backup mais recente — com muito cuidado para não
somar informação, sempre sincronizar.

Onde isso aparece: tela **Importações** (`/sistema/importacao/`), no quadro do topo.

## O que a conferência olha

Só o que dá para saber de fora do arquivo, sem abrir o banco e sem tocar no SET: o nome, o
tamanho e a data de gravação. Fica em `apps/importacao/conferencia.py` e roda em dois
momentos — na tela, antes de alguém clicar, e dentro da importação, de novo, porque entre
olhar a tela e clicar o arquivo pode ter mudado.

| O que confere | Quando reclama | O que acontece |
| --- | --- | --- |
| Tamanho mínimo | abaixo de 1 MB (`IMPORTACAO_BACKUP_MINIMO_BYTES`, nas configurações) | **quebrado**: não importa, nem forçando |
| Encolheu desde a última importação | 30% ou mais | **impedido**: a importação normal para; forçar lê assim mesmo |
| Encolheu desde a última importação | de 5% a 30% | ressalva, importa |
| Data do arquivo | 2 dias ou mais | ressalva, importa |
| Data do arquivo | mais antigo que o já importado | ressalva, importa |
| Qual arquivo da pasta | o mais novo está vazio | ressalva: avisa que vai ler o anterior |
| Mesmo arquivo da anterior | igual em nome, data e tamanho | nota: sem forçar, termina como Sem backup novo |

Os limites estão no topo de `conferencia.py` e a razão de cada um está escrita lá. O do
tamanho mínimo é folgado de propósito: o backup da Cabana tem centenas de MB, então um
arquivo de alguns KB só pode ser gravação interrompida.

## Os dois botões

- **Importar agora**: o caminho normal. Lê o backup mais recente; se for o mesmo da
  importação anterior, termina como *Sem backup novo* e nada muda na tela.
- **Forçar atualização com o último backup**: lê esse mesmo arquivo de novo e refaz os
  números a partir dele. Serve para quando se quer ter certeza de que a tela mostra o que
  está no backup de hoje, e para passar por cima de uma desconfiança da conferência que a
  gerência saiba explicar (o banco do SET encolheu de verdade, por exemplo).

Forçar **não** passa por cima de arquivo quebrado. Forçar manda ler, e ler um arquivo pela
metade trocaria número bom por número pela metade. Nesse caso o botão nem aparece.

Quem clica é quem tem a permissão de importar (`importacao.executar_importacao`): a
gerência. Pela linha de comando é `manage.py importar_set --forcar`, que a tarefa
automática nunca usa — ela roda sem forçar, de propósito, porque forçar todo dia leria o
mesmo backup à toa.

## Forçar não soma

É a parte que o Edson pediu com mais ênfase. Forçar não tem caminho próprio de gravação:
é a mesma importação de sempre, com a mesma foto por importação descrita em
[sincronizacao-nao-soma.md](sincronizacao-nao-soma.md). Cada importação grava linhas
novas, ligadas a ela pelo campo `importacao`, e as telas leem só a última concluída. Reler
o mesmo backup tem que dar exatamente os mesmos números.

A prova fica na própria tela: logo abaixo do quadro da conferência está a comparação das
duas últimas importações, e uma importação forçada do mesmo arquivo é o caso em que ela
tem que ficar toda verde, com "as duas importações leram o mesmo arquivo de backup e todos
os números deram iguais". O teste
`test_forcar_a_leitura_do_mesmo_backup_tambem_nao_soma`, em
`apps/importacao/tests/test_comparacao.py`, trava isso.

## O que fica registrado

Cada importação guarda no seu log a conferência inteira, inclusive quando passa: qual
arquivo, de que tamanho, de que data, e cada coisa que o sistema estranhou. No histórico,
a importação feita pelo botão aparece marcada como **forçada**, que é o que explica duas
importações seguidas do mesmo arquivo. Quando a conferência não deixa importar, a falha
fica registrada com o motivo e a tela mostra o passo a passo de como resolver
(`apps/importacao/diagnostico.py`).
