# Relatórios, rotinas e canais

## As quatro rotinas

| Rotina | Quando | O que leva |
|---|---|---|
| `contas` | todo dia | vencidas, do dia e até 7 dias |
| `vendas` | todo dia | a relação do dia: produto, custo, lucro, margem |
| `estoque` | toda semana | prateleira, parado, travado, empurrar |
| `compra` | toda semana | o que comprar, por fornecedor, dentro do teto |

Definidas em `apps/alertas/models.py` (`Rotina`, `DIARIAS`, `SEMANAIS`) e montadas em
`apps/alertas/relatorios.py` (`MONTADORES`).

## A forma de um relatório

```python
Relatorio(
    rotina="vendas",
    assunto="Vendas do dia",
    manchete="...",      # a frase que decide se a pessoa abre o resto
    resumo="...",        # vai para o registro de envios
    data_corte=...,      # de quando é o número
    blocos=[Bloco(...)], # título, frase e, às vezes, tabela de DUAS colunas
    tem_noticia=True,    # sem notícia, não manda
    aviso="...",         # dado velho muda o que o e-mail significa
    caminho="/sistema/painel/vendas-do-dia/",  # o Telegram vira endereço inteiro
)
```

**Nenhuma conta é refeita no relatório.** Cada um chama a função que a tela chama. Se o
número do e-mail divergir do da tela, o sistema perde a confiança inteira.

## Sem notícia não manda

`tem_noticia` diz se há algo que mude o que a pessoa faz hoje. Dia sem conta vencida, sem
conta do dia e sem conta da semana não gera e-mail — mas gera REGISTRO, com
`sem_noticia=True`, para "não recebi o e-mail de ontem" ter resposta. O botão "mandar
agora" passa `forcar=True`, porque quem aperta quer ver a mensagem.

## Os dois canais

| | E-mail | Telegram |
|---|---|---|
| Módulo | `apps/alertas/envio.py` | `apps/alertas/telegram.py` |
| Configuração | `ConfiguracaoDeEmail` (pk=1) | `ConfiguracaoDeTelegram` (pk=1) |
| Interruptor | `ativo` | `ativo` |
| Conteúdo | relatório inteiro, HTML + texto | manchete e 3 linhas por bloco |
| Segredo | senha da caixa, cifrada | token do robô, cifrado |

São **independentes**: o Telegram sai com o e-mail desligado e vice-versa. Cada canal tem
a sua pendência do dia (`EnvioDeRelatorio.canal`), senão um aviso de Telegram entregue
faria o sistema achar que o e-mail já saiu.

- E-mail: a porta decide o modo (465 = SSL, 587 = TLS), e o erro do SMTP vira frase de
  loja em `envio.TRADUCOES`.
- Telegram: um POST com `urllib` para `api.telegram.org`, sem biblioteca nova, texto puro
  (sem Markdown: nome de produto tem `*` e `_` à vontade), e o erro vira frase de loja em
  `telegram.TRADUCOES`. O robô não escreve para quem nunca falou com ele, e é por isso
  que a tela tem "Descobrir a conversa" (`getUpdates`) em vez de pedir um número.

## O relógio é do Windows, o horário é da tela

A tarefa agendada acorda **de hora em hora** e pergunta ao sistema o que já passou da
hora e ainda não saiu (`apps/alertas/agenda.py`). De graça vêm três coisas: servidor
desligado às 7h entrega quando ligar, mudança de horário na tela vale no mesmo dia, e
falha pode ser tentada de novo — no máximo `TENTATIVAS_POR_DIA = 3`, porque insistir de
hora em hora é como a caixa de e-mail da loja é bloqueada.

```
python manage.py enviar_relatorios --rotina devido
python manage.py enviar_relatorios --rotina vendas --forcar --mesmo-desligado
```

O comando sai com código 0 mesmo quando o envio falha: tarefa "com erro" no Windows não
avisa ninguém, e quem precisa saber é a tela de alertas, em português.

## Exportação para o Excel

Ponto e vírgula e BOM (`"﻿"`), que é como o Excel em português abre sem perguntar
nada. Número com vírgula decimal. A tela mostra os maiores; o arquivo leva tudo
(`limite=0`).
