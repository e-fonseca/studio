# Tempo e venda: o que o clima faz com a loja física

Entrou na 1.28.0, a pedido do Edson: *"as mudanças climáticas têm impacto no nosso
negócio na loja física, portanto queremos que grave de alguma forma no sistema a
condição climática do dia para fazer uma avaliação mais analítica dos impactos
condição climáticas com o nosso negócio."*

Está em `apps/tempo/`. Guarda a condição de cada dia ao lado do que a loja vendeu
naquele dia.

Na **1.29.0** ele mudou de lugar, a pedido dele: *"remover do menu TEMPO E VENDA,
virar recurso dentro de visão geral, configurar api de previsão do tempo automática,
armazenar informações diárias e usar como indicador."* Então:

- **O indicador mora na Visão geral** (`apps/tempo/indicador.py`, quadro "O tempo e
  a venda"). É a única coisa daquela tela que olha para frente.
- **A tela `/sistema/tempo/` saiu do menu** e continua inteira, para anotar o dia,
  ver dia a dia e dizer onde fica a loja. Abre pelo link do quadro.
- **A configuração virou o nome da cidade.** As coordenadas o sistema descobre.
- **A busca passou a trazer a previsão** dos próximos dias, além do dia fechado.

## A conta é sempre dentro do mesmo tipo de dia

Esta é a decisão que define o módulo. A loja faz **76,4% do faturamento no fim de
semana** ([vender-mais-fora-do-fim-de-semana.md](vender-mais-fora-do-fim-de-semana.md)):
um domingo vale treze segundas. Comparar "média dos dias de chuva" com "média dos
dias de sol" misturando tudo mediria o dia da semana e devolveria um número que
parece análise e não é — bastaria chover em dois domingos para o clima "custar"
dez mil reais por dia.

Então `apps/tempo/analise.py` separa **fim de semana e feriado** de **meio de
semana**, e dentro de cada grupo compara chuva contra sem chuva. Feriado conta
como fim de semana porque é quando a loja tem público, e foi assim que o Edson
descreveu o negócio.

## O que conta como chuva

`TempoDoDia.choveu`: se alguém escreveu a condição, a condição manda (chuva, chuva
forte, tempestade). Sem condição escrita, vale o volume, e **garoa não conta**:
o corte é 1 mm. Um dia com 0,4 mm não é um dia de chuva para quem está decidindo
abrir a loja.

## Dois caminhos para o dado entrar, e quem ganha

**À mão, na tela.** Um campo por dia, com a lista dos dias que ainda estão sem
registro — uma lista curta de datas é respondível, um calendário em branco não.
Quem está na loja viu o que a previsão não vê: "choveu só de madrugada", "teve
festa na praça", "rua interditada". Isso vai no campo de observação.

**Sozinho, de madrugada.** A tarefa `\Cabana\CabanaTempo` roda todo dia às 06:10
(`scripts\tempo.ps1`, registro em `logs\tempo.log`) e busca os últimos dias e a
previsão da semana no Open-Meteo — serviço aberto, sem cadastro, sem mensalidade e
sem chave. Precisa saber onde fica a loja, e para isso basta o nome da cidade.

**O escrito à mão nunca é sobrescrito pela busca.** `servicos.guardar_dias()`
conta esses dias à parte ("respeitados") e passa adiante. A previsão é a média de
um quadrado de alguns quilômetros; a pessoa do balcão é a testemunha.

## A cidade basta: por que a configuração mudou (1.29.0)

Até a 1.28.0 ligar a busca exigia **latitude e longitude digitadas à mão**, pegas no
Google Maps com o botão direito no endereço da loja. Era pedir a quem não é técnico
dois números de seis casas decimais para a função começar a existir — e por isso ela
nunca começou: a busca ficou desligada desde a entrega.

Agora o campo é **o nome da cidade**. `apps/tempo/lugar.py` pergunta as coordenadas
ao serviço de geografia do próprio Open-Meteo (aberto, sem chave, da mesma casa que
dá a previsão), e isso acontece em dois momentos:

- ao **salvar** a tela, que faz o caminho inteiro de uma vez — descobre o lugar,
  busca o tempo e escreve numa frase o que achou;
- na **busca de todo dia**, quando as coordenadas estiverem em branco, para quem
  escreveu a cidade às 08:00 não esperar as 06:10 do dia seguinte.

Duas cautelas, porque nome de cidade se repete no Brasil:

1. **Escolhe a de maior população** entre as do país. "Sorocaba" é a de São Paulo,
   não o distrito homônimo de Canelinha.
2. **Escreve na tela o que entendeu** ("Sorocaba, São Paulo, Brasil") e guarda em
   `ConfiguracaoDoTempo.lugar_encontrado`. Sem isso, a cidade homônima de outro
   estado entraria calada e a chuva de lá entraria na conta do movimento daqui.

A latitude e a longitude continuam à vista e dá para corrigi-las à mão, que é o caso
da loja longe do centro da cidade. Trocar a cidade **esquece** as coordenadas
antigas, senão o sistema seguiria buscando o tempo do lugar anterior, calado.

A busca também passou a nascer **ligada** (`ativo=True`, e a migração 0002 liga a
linha que já existe no servidor). Enquanto a cidade estiver em branco, a tarefa da
madrugada não faz nada, termina em paz — `FaltaOLugar` existe só para isso, para o
Windows não marcar a tarefa como quebrada por causa de um campo vazio — e a tela diz
o que falta.

## Previsão é previsão, e não entra em conta nenhuma

A mesma chamada traz o dia fechado e os próximos dias, e os dois servem a coisas
diferentes:

- **Dia fechado é medição.** É dele que sai a conta de quanto a chuva custa.
- **Dia à frente é previsão.** Serve para a loja se preparar: o fim de semana é
  quando ela fatura, e saber na quinta que vai chover no sábado é o que dá tempo de
  fazer alguma coisa.

O dia previsto fica marcado em `TempoDoDia.previsao`, e **hoje nasce marcado também**
— às 06:10 da manhã a chuva da tarde ainda é palpite. `apps/tempo/analise.py`
descarta os marcados, então média de palpite nunca entra na medida. A busca do dia
seguinte devolve o mesmo dia já fechado e a marca cai sozinha; quem anota na tela
também apaga a marca, porque viu o dia pela janela.

Dia previsto **continua** na lista do que falta anotar: a previsão da véspera não
dispensa alguém de dizer como o dia foi.

## O indicador da Visão geral

`apps/tempo/indicador.py`. Lidera com o que vem — **o próximo fim de semana** — e põe
ao lado o que a loja já pagou por isso. Três cuidados:

- **Só o próximo fim de semana.** Numa janela de sete dias que começa num domingo
  cabem dois; somar os dois diria "chuva no fim de semana" por causa de um sábado a
  seis dias de distância, e a loja não se prepara para isso hoje.
- **Chuva de terça não pinta o quadro de vermelho.** O que muda o faturamento é o
  fim de semana.
- **Não conclui com três dias.** Abaixo do mínimo, o quadro diz o que está previsto e
  admite que ainda não sabe quanto custa.

## A única parte do sistema que sai para a internet

E é tarefa de servidor, nunca tela: nada do que alguém está olhando espera
resposta de fora. Se a busca falhar, `ConfiguracaoDoTempo.ultimo_erro` guarda o
motivo para aparecer na tela no dia seguinte — em vez de morrer num log que
ninguém abre — e o resto do sistema não sente nada. A decisão de projeto "nenhuma
tela depende da internet" ([ficha-tecnica.md](ficha-tecnica.md)) continua valendo
inteira, e o tempo pode ser todo anotado à mão se a loja nunca ligar a busca.

## A tela avisa quando ainda não dá para concluir

`DIAS_PARA_CONCLUIR = 8`. Abaixo de oito dias de chuva **e** oito sem chuva dentro
do grupo, a média é curiosidade, não medida, e a tela escreve isso em vez de
deixar alguém decidir compra por ela. É o mesmo cuidado do ticket médio, que avisa
quando o recorte tem poucas vendas.

Dia com venda e sem tempo anotado fica **fora** da média e é contado à parte, para
a tela poder dizer em quantos dias a conta se apoia.

## Para que isto serve na prática

Duas perguntas que hoje não têm resposta e em alguns meses terão:

1. **Quanto um fim de semana de chuva custa.** É o número que justifica (ou não)
   reforçar o estoque antes de um feriado de sol, e o que explica um mês fraco sem
   culpar a compra.
2. **Quando agir sobre o meio de semana.** Fim de semana perdido por chuva deixa a
   mercadoria na prateleira e a semana inteira vazia na frente — é o momento exato
   de acionar o que estiver montado para o meio de semana.

## Arquivos

| Arquivo | O que faz |
|---|---|
| `models.py` | `TempoDoDia` (um dia) e `ConfiguracaoDoTempo` (onde fica a loja, se busca sozinho) |
| `fonte.py` | fala com o Open-Meteo, traduz o código da Organização Meteorológica Mundial e marca o que é previsão |
| `lugar.py` | descobre a latitude e a longitude pelo nome da cidade (1.29.0) |
| `servicos.py` | grava, respeitando o que foi escrito à mão; descobre o lugar; guarda o erro da busca |
| `analise.py` | a comparação por tipo de dia e a tabela dia a dia, sem os dias previstos |
| `indicador.py` | o quadro da Visão geral: o próximo fim de semana e o que a chuva custa (1.29.0) |
| `management/commands/buscar_tempo.py` | o comando que a tarefa do Windows chama |
