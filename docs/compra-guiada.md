# Compra guiada (1.45.0)

Pedido dele em 02/11/2026: *"no menu compras criar um sub menu compra guiada / fazer formato
tipo apresentação, pop up, só que com perguntas fechadas ou abertas para informar tipo ou
quantidade para formatar a sugestão de compra, elaborar perguntas que façam uma leitura de
todo o estoque, venda, produto que mais vende para formatar um pedido de compra para o
fornecedor assertivo. Hoje o formato está longe de está intuitivo e fácil de operar, preciso
que empenho máximo nesse recurso, a funcionaria que trabalhava com essa parte saiu da empresa
e não deixou nenhuma informação registrada."*

O passo a passo de quem compra está em `manual/compra-guiada.md`. Aqui fica como funciona.

## A ideia em três frases

1. **A conta é a da Lista de compra**, só que de um fornecedor e com as respostas da pessoa no
   lugar dos números fixos. Nada de regra nova de quantidade: com a próxima compra "na semana
   que vem", a compra guiada dá exatamente a Lista de compra daquele fornecedor (há teste).
2. **Cada resposta mostra a consequência** antes de ser escolhida: quantos produtos, quanto
   custa e quanto tempo o pedido segura a loja. A pessoa escolhe olhando o efeito.
3. **As respostas ficam guardadas.** Cada compra guiada concluída leva um resumo de como foi
   decidida ("próxima compra em 30 dias; prazo de 15 dias; venda de base: o ano inteiro...")
   e aparece no registro da abertura e na pergunta da próxima compra do mesmo fornecedor. É o
   que a funcionária que saiu não deixou.

## As perguntas

| Passo | Endereço | Pergunta | O que muda na conta |
|---|---|---|---|
| 1 | `/sistema/compras/guiada/` | De qual fornecedor? | A leitura da loja e os fornecedores com mais venda parada por falta de produto |
| 2 | `.../prazo/` | Quanto tempo ele leva para entregar? | Só aparece se a ficha não tem prazo. A resposta vai para a ficha (quem pode mexer em fornecedor) e passa a valer também na Lista de compra |
| 3 | `.../proxima-compra/` | Quando você volta a comprar dele? | `Parametros.antecipar_dias`: o pedido segura a loja até a PRÓXIMA compra chegar |
| 4 | `.../tipos/` | Que tipos (grupos do SET) entram, e o quê deles? | Tudo o que vai faltar / só o que já falta ou está no alerta / só os carros-chefe |
| 5 | `.../venda/` | Em que venda o sistema se baseia? | O ano com a estação do ano passado (o padrão) ou 6 meses, 3 meses, 30 dias |
| 6-10 | `.../produto-1/` a `produto-5/` | Quantas unidades de cada um dos 5 que mais vendem? | Sugestão, metade, dobro, não comprar ou outro número. Guarda a PALAVRA: "metade" acompanha a conta se outra resposta mudar |
| 11 | `.../encomendas/` | Algum cliente encomendou? A equipe pediu? | Soma por cima da conta; a sugestão da equipe marcada é respondida quando o pedido sai |
| 12 | `.../orcamento/` | Até quanto o pedido pode chegar? | O que sobra no teto do mês (já tirados os pedidos daqui que não chegaram), um valor, ou sem limite. Corta pelo fim da fila; escolha e encomenda não se cortam |
| 13 | `.../revisao/` | Confira e gere | Duas tabelas editáveis: **Em falta e acabando** (o que a conta pede) e **Os outros produtos** do fornecedor (desde a 1.47.0, em zero); recado ao fornecedor; Gerar o pedido |

O número de perguntas de produto é `QUANTOS_PRINCIPAIS` (5); a pergunta do prazo some quando
a ficha já tem prazo. Endereço de pergunta que deixou de existir (o fornecedor tem só 3
produtos e alguém abre o `produto-4`) leva à primeira que falta.

## Onde mora

- `apps/compras/guiada.py`: a conta (`montar` devolve a `Proposta` com as `Linha`s), as
  leituras (`ler_a_loja`, `historico_do_fornecedor`, `teto_do_mes`), as opções de cada
  pergunta com a consequência, `salvar_resposta` e `gerar_pedido`.
- `apps/compras/views_guiada.py`: uma tela por pergunta. O estado mora no servidor
  (`CompraGuiada.respostas`), então a tela funciona sem JavaScript, o Voltar do navegador não
  perde nada e dá para parar e continuar outro dia.
- `templates/compras/guiada/`: `_moldura.html` (o cartão de apresentação, a barra de
  andamento e o pé com o pedido de agora), uma página por pergunta, `abertura.html` e
  `pronto.html`.
- `static/js/guiada.js`: só conforto. Teclas 1 a 9 escolhem a resposta, a conta da "Outra
  quantidade" aparece enquanto se digita, a conferência soma enquanto se digita, Enter na
  tabela desce para a linha de baixo, e só vai ao servidor a linha que mudou (um fornecedor
  grande tem 250 linhas e o Django recusa mais de 1.000 campos).
- `CompraGuiada` (migração `compras.0007_compra_guiada`): fornecedor, situação (em
  andamento, concluída, deixada de lado), respostas em JSON, quem, quando, a data dos dados,
  o número do pedido, o valor e o resumo.

## Todos os produtos do fornecedor (desde a 1.47.0)

Pedido dele (04/11/2026): *"em compra guiada, exibir todos os produtos de cada fornecedor,
priorizar os produtos em falta E acabando e em seguida todos os demais."* A conferência
passou a ter duas tabelas:

1. **Em falta e acabando**: o pedido que a conta monta, como antes (a mesma conta da Lista
   de compra, do que mais faz falta para o que menos faz).
2. **Os outros produtos de <fornecedor>** (`guiada.os_demais`): o resto do cadastro do SET
   deste fornecedor (só mercadoria), em zero, nesta ordem: o que a conta pede mas ficou fora
   pelos tipos ou pelo "o que entra"; o que vendeu no ano, do que mais faturou para o que
   menos; o parado (não vendeu e tem saldo); o que não vendeu nem tem saldo. Cada linha diz
   por que está ali ("o que tem dá até a próxima compra", "parado: não vendeu no ano").

Escrever um número nos outros põe o produto no pedido (`respostas["outros"]`, guardado à
parte das respostas da conta): ele continua no lugar dele na segunda tabela, marcado "posto
por você", e vai na folha e no pedido como os outros. Zerar devolve. Guardado à parte para
uma resposta antiga (um "dobro" de quando o produto era da conta) não voltar por baixo do
número digitado. A escolha e a encomenda não se cortam no orçamento, e o número posto à mão
também não. Com mais de doze outros, aparece a busca por nome ou código, sem acento; com mais
de oito na primeira tabela, o título dela leva o atalho para os outros. STARBELLA, na cópia
do SET de setembro: 244 na conta e 406 outros.

## Decisões

- **A compra é de quem começou.** Outra pessoa recebe 404 na compra dos outros. Começar de
  novo o mesmo fornecedor continua a que estava aberta, em vez de abrir outra.
- **Gerar o pedido usa o caminho de Pedidos** (`pedidos.servicos.registrar_pedido`): quem tem
  `pedidos.registrar_pedido` gera; o da Líder de loja e o do perfil Compras nascem esperando a
  gerência, com a folha marcada. Quem só monta (Operador administrativo) baixa a folha com o
  aviso de que ainda não vale e entrega a quem pode gerar.
- **Gerar duas vezes não faz dois pedidos**: `gerar_pedido` trava a linha da compra
  (`select_for_update`) e devolve `None` se ela já virou pedido.
- **O Enter não gera pedido.** Na conferência, o primeiro botão do formulário é um "salvar"
  escondido; na abertura, os botões "Comprar de" têm formulário próprio. O Enter aperta o
  primeiro botão do formulário, e antes disso um Enter na quantidade gerava o pedido (e um
  Enter no "Outro fornecedor" começava a compra do carro-chefe de cima).
- **O que dura mais de um ano pergunta antes.** A conferência avisa quando a conta põe no
  pedido produto que dura mais de um ano na prateleira e oferece tirar com um clique. Quase
  sempre é o estoque mínimo cadastrado no SET (2.807 produtos têm um) maior do que o produto
  vende: a conta respeita o mínimo, e o mínimo vira dinheiro parado.
- **O orçamento conta a escolha e a encomenda uma vez só.** Até o fim da construção, a
  encomenda por cima de um produto com sugestão gastava a sugestão duas vezes no limite
  (`_o_que_nao_se_corta`).
- **Campo apagado na conferência é zero**, como a tela mostra na hora.
- **Prazo "Não sei" não inventa prazo**: a conta segue com o prazo estimado e nada vai para a
  ficha.
- **Sem internet, sem biblioteca**: cartão, barra e animação são CSS (`guiada-*` no
  `sistema.css`); a animação de entrada some com "reduzir movimento".

## Testes

`apps/compras/tests/test_compra_guiada.py`: a conta igual à da Lista, cada resposta mudando o
pedido, o corte do orçamento, o teto do mês, as perguntas, o pedido da gerência, da Líder e de
quem só monta, as telas pelo navegador de teste (o caminho inteiro até o pedido, o Enter, as
encomendas, a conferência, o que dura mais de um ano) e, desde a 1.47.0, os outros produtos do
fornecedor (`OsOutrosProdutosDoFornecedor`: a ordem, o número posto à mão no pedido, o zero
que devolve, a resposta antiga que não volta).
