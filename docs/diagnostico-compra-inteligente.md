# Diagnóstico: otimização inteligente de compras e estoque

Pedido do Edson em 20/10/2026 (prompt "OTIMIZAÇÃO INTELIGENTE DE COMPRAS E ESTOQUE",
14 seções), com a instrução de abrir pelo diagnóstico: *"Antes de implementar,
apresente quais funcionalidades já atendem aos requisitos, quais precisam ser
ajustadas e quais ainda não existem"*.

Este arquivo é a ETAPA 1 (diagnóstico) e a ETAPA 2 (planejamento) do próprio prompt.
Foi escrito lendo o código, não de memória: cada afirmação aponta o arquivo e a linha.

Versão conferida: 1.35.1, commit `ce0915b`, 1.499 testes passando.

---

## Resumo em cinco linhas

1. **O cálculo que ele descreve na seção 4 já é exatamente o cálculo do sistema.** Ponto
   de reposição, estoque-alvo, posição de estoque, compra sugerida e arredondamento para
   unidade inteira estão em `apps/compras/calculos.py` desde a 1.4.0, com a fórmula dele
   letra por letra.
2. **Três dos cinco números que ele manda "diferenciar claramente" são calculados e não
   aparecem na tela.** Ponto de reposição, estoque de segurança e estoque-alvo existem em
   memória; a tela mostra o mínimo do SET no lugar do ponto de reposição.
3. **Duas lacunas reais encontradas**: a trilha de auditoria do ajuste manual existe, mas
   **não guarda a justificativa nem o número anterior** (ele pede as duas coisas na seção
   11), e a venda de 90 dias é importada e nunca usada na lista de compra (ele pede essa
   coluna na seção 6).
4. **O que de verdade não existe é a configuração por produto e por categoria** (seção 3),
   o lote mínimo e o múltiplo do fornecedor (seção 4), a análise XYZ (seção 5), o "adiar"
   (seção 6), o simulador (seção 10) e três dos oito alertas (seção 8).
5. **Atenção, e é a parte desconfortável**: o Edson está rodando a **1.29.0**. Metade do
   que ele pediu já está pronto e entregue nas versões 1.30.0 a 1.35.1, que ele nunca
   instalou. A tela Pedidos ao fornecedor, por exemplo, só existe da 1.31.0.

---

## Seção 3 — Classificação dos produtos

| Requisito | Situação | Onde |
|---|---|---|
| Mínimo por produto | **Ajustar** | Hoje o único mínimo é o `QTDEMIN` do SET (`ProdutoImportado.estoque_minimo_set`, `apps/importacao/models.py:131`), que entra como piso do ponto de pedido (`apps/compras/calculos.py:130-133`). Funciona, mas quem configura é o SET, não o sistema. |
| Mínimo por categoria | **Não existe** | O grupo do produto (`ProdutoImportado.grupo`) é só rótulo: nenhuma regra olha para ele. |
| Faixas iniciais (peça única 1, baixa procura 1-2, moderada 3-5, alta 6-12, sazonal) | **Não existe** | Precisa de tabela nova (`PoliticaDeEstoque`) com mínimo por produto e por categoria, e de uma tela para preencher. |
| Exceções justificadas | **Ajustar** | Existe em `AjusteDeCompra.observacao` (200 caracteres), mas só para a quantidade de UM pedido, não como política permanente. |
| Peça única / sem reposição, sem pedido automático | **Não existe** | Nada marca um produto como não reponível. A proteção que existe é indireta: peça única vende 1 e some, a demanda cai a zero e a conta não pede nada (`calculos.py:131`). Funciona por acidente, não por regra. |

**Risco da mudança:** alto. Mínimo configurável mexe no número que vai ao fornecedor.
Pede a comparação antes/depois que ele mesmo exige na ETAPA 5.

---

## Seção 4 — Cálculo inteligente de reposição

**Esta seção já está atendida, inteira.** `apps/compras/calculos.py`:

| Requisito dele | Onde está |
|---|---|
| Ponto = venda média diária × prazo + estoque de segurança | `_quanto_comprar`, linha 127-128 |
| Venda média diária = vendido ÷ dias considerados | `calcular`, linha 149 — e o divisor é dia de **porta aberta**, não dia de calendário |
| Prazo de entrega do fornecedor | `Fornecedor.prazo_dias` informado, senão o prazo medido das compras do SET, senão 15 dias assumido e a linha avisa (`lista_de_compra.py:288-296`) |
| Estoque de segurança | `dias_seguranca = 7` dias de demanda (`Parametros`, linha 41) |
| Estoque disponível = utilizável menos reservas | `posicao`, linha 165 |
| Posição de estoque = disponível + pedidos confirmados não recebidos | `posicao`, linha 165, com `recebimentos_pendentes` |
| Estoque-alvo = demanda no prazo + intervalo entre revisões + segurança | linha 129 |
| Compra = máximo entre zero e (alvo − posição) | linhas 134-136 |
| Arredondar para unidade inteira | `_arredondar_compra`, linha 112-117 (`ROUND_CEILING`) |
| Lotes mínimos e múltiplos | **Os campos existem** (`Item.lote_minimo`, `Item.multiplo`) e o arredondamento já os respeita — **mas ninguém os preenche.** Faltam no cadastro do fornecedor. |
| Evitar pedido duplicado | `_mesmo_pedido_de_hoje` (`apps/pedidos/servicos.py`) recusa o mesmo pedido no mesmo dia; e `pedido_em_aberto` do SET já entra na posição |
| Nunca confundir físico com disponível, nunca descontar reserva duas vezes | A reserva é descontada uma vez, em `posicao`; o campo se chama `reservas_nao_deduzidas` exatamente porque o estoque do SET já desconta algumas |

**Além do que ele pediu:** o saldo negativo do SET conta como zero na compra
(`calculos.py:160-170`). São 1.023 produtos com saldo abaixo de zero porque a loja nunca
fez contagem física; sem essa regra a lista inflava R$ 89 mil. Isso não está no prompt
dele e é o ajuste que mais muda o que vai ao fornecedor.

**Pendência de exibição, não de conta:** ele manda "diferenciar claramente" cinco
números. O sistema calcula os cinco e a tela mostra dois (o que tem e quanto comprar);
o ponto de reposição aparece como "Mínimo", que é outra coisa — é o mínimo do SET
(`templates/compras/lista_de_compra.html:210`). **Resolvido na 1.36.0:** os cinco saem
escritos na linha de detalhe.

### A fórmula da imagem, conferida linha a linha (20/10/2026)

Ele mandou a fórmula em imagem junto do pedido da compra inteligente:

```
SC = max(0, ⌈VMD × (PE + IR) + ES − EP⌉)       EP = disponível + pedidos pendentes
```

É a conta de `calculos.py`, letra por letra: `VMD` é `demanda`, `PE + IR` é
`prazo_dias + horizonte_revisao_dias`, `ES` é `dias_seguranca × demanda`, `EP` é
`posicao`, e o teto para cima é `ROUND_CEILING`. O disponível já desconta reservas, como
a imagem exige.

**A única diferença** é um freio que a fórmula dela não tem: o sistema só compra quando a
posição de estoque chega ao **ponto de reposição** (`posicao <= ponto`). Sem ele, todo
produto cuja posição esteja um décimo abaixo do alvo entra na lista com 1 unidade.

Medido na foto de 20/09/2026, a loja inteira:

| | Linhas | Unidades | Custo |
|---|---|---|---|
| Como o sistema faz hoje (com o freio) | 2.237 | 3.400 | **R$ 95.184,54** |
| A fórmula dela, sem o freio | 2.248 | 3.412 | **R$ 95.307,15** |
| Diferença | +11 | +12 | **+R$ 122,61** (0,13%) |

As 11 linhas a mais são todas de 1 unidade, de produto cujo estoque já cobre o prazo do
fornecedor — FORMA 30CM PEDRA SABÃO, por exemplo: posição 1,000, ponto 0,93, alvo 1,22.
Comprar ali não é errado, é só antecipar: a peça chega antes de fazer falta e fica
parada o prazo inteiro. **O freio ficou**, e esta tabela está aqui porque a ETAPA 5 do
prompt exige a comparação antes de trocar qualquer regra. Tirar o freio é um botão de
uma linha, e espera a palavra dele.

---

## Seção 5 — Análise do histórico de vendas

| Requisito | Situação | Onde |
|---|---|---|
| Vendas de 12 meses | **Atende** | `vendas_12m`, base da demanda |
| Vendas de 90 dias | **Ajustar** | `ProdutoImportado.vendas_90d` é importado e **nunca chega à lista de compra**. O filtro de janela oferece 30, 90 e 180 dias (`apps/compras/janela.py`), mas a coluna com o número de 90 dias não existe. |
| Dias sem venda / velocidade de saída | **Atende** | `cobertura_dias`, `ultima_venda`, e a frase do movimento ("vendeu 9 desde então, e já saiu tudo", `apps/compras/movimento.py`) |
| Variações sazonais | **Atende, e passa do pedido** | `apps/compras/estacao.py`: o mesmo período do ano passado entra na quantidade sugerida, com quatro freios contra amostra pequena |
| Classificação ABC | **Ajustar** | `calculos.curva_abc` existe (linha 352) e **nenhuma tela a usa**: é código morto. A tela Dashboard calcula ABC por receita por conta própria (`apps/painel/dashboard.py:463-486`). A classe ABC não chega na lista de compra, que é onde ele quer usá-la. |
| Regularidade da demanda (XYZ) | **Não existe** | Nenhum cálculo de variabilidade. Precisa do mês a mês, que já é importado (`VendaMensalDoProduto`). |
| Tendência de crescimento ou redução | **Não existe** na sugestão | A tela de comparação de períodos mostra (`apps/compras/comparacao.py`), mas não entra no quanto comprar |
| Dias úteis contra fim de semana | **Não existe** na sugestão | O Dashboard mostra venda por dia da semana; a demanda diária é plana |
| Sem venda em 12 meses não gera reposição | **Atende** | Demanda zero devolve compra zero (`calculos.py:121-122`), e o candidato nem entra na lista sem venda e sem mínimo (`lista_de_compra.py:328`) |
| Baixa confiança para item novo | **Atende** | `confianca` alta/média/baixa, com `dias_minimos_historico = 28` |
| Baixa saída com estoque: promover em vez de comprar | **Não existe** | O sistema identifica (`Situacao.SEM_GIRO`, R$ 227 mil que não venderam uma unidade no ano) e não oferece ação nenhuma |

---

## Seção 6 — Inteligência de compras (a tabela de 13 informações)

| Informação pedida | Está na tela? |
|---|---|
| Produto e código | Sim |
| Categoria | Sim, na linha de detalhe (`{{ item.grupo }}`) |
| Estoque atual | Sim ("Tem") |
| Vendas em 90 dias | **Não** |
| Prazo do fornecedor | Sim, no bloco e na coluna |
| Estoque de segurança | **Não** (calculado, não exibido) |
| Ponto de reposição | **Não** (calculado; a coluna "Mínimo" é o mínimo do SET) |
| Quantidade sugerida | Sim, em campo editável, com "sugestão do sistema: 43" embaixo |
| Custo unitário | Sim |
| Custo total | Sim ("Custo da compra") |
| Prioridade | Sim (tarja "Já faltando" / "Abaixo do mínimo" / "Vai faltar") |
| Motivo | Sim, por linha, com a conta do movimento |
| Atualização dos dados | Sim, a data de corte no topo, com amarelo em 2-3 dias e vermelho em 4+ |

**Ações do usuário:**

| Ação | Situação |
|---|---|
| Aceitar | **Atende** — não mexer na linha é aceitar |
| Alterar a quantidade | **Atende** — campo editável desde a 1.28.0 (`apps/compras/ajustes.py`) |
| Rejeitar | **Atende** por convenção: digitar 0 significa "não comprar agora" |
| **Adiar a compra** | **Não existe** como estado próprio. Hoje adiar e rejeitar são o mesmo zero, e o zero não tem prazo de volta. |
| Registrar justificativa | **Ajustar** — o campo existe (`AjusteDeCompra.observacao`) e é **opcional**; ele pede que fique registrado |

**Lacuna encontrada na auditoria do ajuste:** a trilha existe — a tela registra
`compras.quantidade_ajustada` (`apps/compras/views.py`) — mas guardava a **sugestão do
sistema** e o número novo, e não **o número que estava escolhido antes** nem **a
justificativa**. A pergunta que se faz três meses depois é "quem mudou de 10 para 6, e
por quê", e essa a trilha não respondia. O ajuste é sobrescrito a cada edição
(`update_or_create`), então o valor anterior se perdia de vez.

---

## Seção 7 — Priorização e orçamento

| Requisito | Situação | Onde |
|---|---|---|
| Teto mensal de compra | **Atende** | `apps/compras/limite.py`: 12 meses de custo vendido ÷ 12, com barra e níveis bom/atenção/ruim |
| Compras dentro do orçamento | **Atende** | `ListaDeCompra.cabe_no_mes` |
| Compras acima do orçamento | **Atende** | `ListaDeCompra.estourou_o_mes` / `resto` |
| Risco de falta primeiro | **Atende** | `Urgencia.PESO` ordena faltando, abaixo do mínimo, vai faltar |
| Histórico de vendas na ordem | **Atende** | dentro de cada tarja, ordena por receita de 12 meses |
| Tempo de reposição na ordem | **Atende** | o prazo já está dentro do ponto de pedido |
| Organização por fornecedor | **Atende** | blocos de até 15 por fornecedor, com corte por fornecedor |
| Importância comercial | **Ajustar** | é a classe ABC, que existe e não chega aqui |
| Custo e margem quando disponíveis | **Ajustar** | o custo entra; a margem (`markup_set`, `preco_venda`) não entra na ordem |
| Pedidos confirmados de clientes | **Ajustar** | a tela Sugestões da equipe tem o motivo "cliente pediu" (`SugestaoDeCompra.Motivo.CLIENTE_PEDIU`) e isso **não** chega à lista de compra |
| Não aprovar nem emitir automaticamente | **Atende** | nada grava pedido sem clique de gente |
| Não ultrapassar o orçamento sem autorização | **Atende** | o sistema avisa e não trava; quem decide é o gestor |

---

## Seção 8 — Alertas e rotina operacional

Hoje existem cinco rotinas (`apps/alertas/models.py:28`): contas a pagar e vendas do dia
(diárias), estoque e sugestão de compra (semanais), e o vigia do backup. Saem por e-mail
e por Telegram.

| Alerta pedido | Situação |
|---|---|
| Estoque próximo de acabar | **Atende** — dentro do relatório semanal de compra |
| Produto abaixo do ponto de reposição | **Atende** — é o próprio relatório de compra |
| Mercadoria com estoque excessivo | **Atende** — relatório semanal de estoque |
| Produto sem vendas há muito tempo | **Atende** — relatório de estoque, parte sem giro |
| Relatório de estoque desatualizado | **Atende** — a data de corte velha vai escrita no topo de todo e-mail (`relatorios._aviso_dos_dados`) |
| **Produto de alta procura sem estoque** | **Não existe** como alerta próprio |
| **Atraso de fornecedor** | **Não existe** — o pedido guarda o prazo combinado (`Pedido.prazo_dias`) e ninguém compara com a data de hoje |
| **Compra sugerida acima do orçamento** | **Não existe** como alerta (está na tela, não no e-mail) |
| Rotina de segunda e quinta | **Ajustar** — hoje o semanal tem **um** dia só (`ConfiguracaoDeEmail.dia_semanal`). Dois dias pedem um campo novo. |

---

## Seção 9 — Integração com o SET

| Requisito | Situação |
|---|---|
| Preservar a importação existente | **Atende** — nada muda nela |
| Validar os arquivos | **Atende** — o zip é conferido e a importação falha com mensagem em linguagem simples |
| Identificar pelo código correto | **Atende** — tudo liga por `codigo` do SET, nunca por chave estrangeira para a foto |
| Evitar duplicações | **Atende** — a foto é refeita inteira a cada importação |
| Registrar a data da última atualização | **Atende** — `Importacao.data_corte`, exibida em toda tela que decide |
| Sinalizar dados incompletos | **Atende** — `Resultado.avisos` e `confianca` |
| Preservar o histórico das importações | **Atende** — cada `Importacao` fica, com log, etapa e progresso |
| Não sobrescrever movimentações locais | **Atende** — pedido, inventário, ficha do fornecedor e ajuste são dados nossos, sem campo `importacao` |
| Dados velhos = recomendação provisória | **Atende** — `dias_dados_vencidos = 10` marca o resultado, e o painel pinta amarelo em 2-3 dias e vermelho em 4+, com botão "Importar agora" |
| **Tratar divergências de cadastro** | **Ajustar** — produto que troca de código no SET aparece como produto novo, sem histórico, e nada avisa |

---

## Seção 10 — Interface

| Requisito | Situação |
|---|---|
| Identidade visual e padrão da intranet | **Atende** |
| Cores consistentes para prioridade | **Atende** — tarja por urgência, âmbar para quantidade que cobre mais de um ano |
| Tabelas e filtros simples | **Atende** — filtro por fornecedor, urgência e janela de média |
| Explicações curtas e motivo da recomendação | **Atende** — frase por linha |
| Layout responsivo | **Atende** — no celular cada linha vira cartão, com o campo Comprar por último |
| Ajuda contextual | **Atende** — F1 com tour por tela |
| **Simulador de prazo e estoque de segurança** | **Não existe** |

---

## Seção 11 — Segurança e controle

| Requisito | Situação |
|---|---|
| Autenticação e permissões da intranet | **Atende** — três perfis, permissão por tela |
| Controle de acesso por perfil | **Atende** — o vendedor vê uma tela só, sem custo nem margem |
| Auditoria de alteração de fornecedor | **Atende** — `fornecedor.ficha_alterada` |
| Auditoria do pedido | **Atende** — `pedido.registrado`, `pedido.anexo_enviado`, `pedido.situacao_alterada` |
| **Auditoria do ajuste manual** | **Ajustar** — `compras.quantidade_ajustada` existe; faltavam a justificativa e o número anterior |
| **Auditoria de sugestão aceita ou recusada** | **Não existe** — depende do "adiar"/"rejeitar" com estado próprio |
| Auditoria de alteração de mínimo | **Não existe** — não há mínimo próprio para alterar ainda |
| Auditoria de mudança no orçamento | **Atende por construção** — o teto sai do histórico do SET, ninguém digita |
| Não expor senha em log | **Atende** — senha e token cifrados, token só no cabeçalho `Authorization`, nunca na auditoria |
| Migrações seguras e backup antes | **Atende** — `atualizar.ps1` faz cópia antes de migrar |

---

## O plano, em três caixas

### Caixa 1 — Baixo risco, faço sem perguntar (ele autorizou isso no prompt)

1. **Pedidos ao fornecedor: editar o pedido** enquanto estiver aberto (quantidade, tirar
   linha, prazo, observação). Pedido direto dele hoje.
2. **Pedidos ao fornecedor: cancelar com motivo obrigatório.** `Situacao.CANCELADO` já
   existe no modelo e não tem tela nem motivo. Pedido direto dele hoje.
3. **Gerar de novo a folha do pedido guardado**, na tela do pedido. Pedido direto dele hoje.
4. **Completar a auditoria do ajuste manual** com a justificativa e o número anterior
   (seção 11).
5. **Vendas de 90 dias na lista de compra** — dado já importado, coluna que ele pediu.
6. **Mostrar os cinco números que a seção 4 manda diferenciar**: ponto de reposição,
   estoque de segurança e estoque-alvo passam a aparecer, sem empilhar colunas (ver o
   aviso abaixo).

### Caixa 2 — Alto impacto, só com a autorização dele

1. Política de estoque configurável **por produto e por categoria** (seção 3) — muda o
   número que vai ao fornecedor.
2. **Lote mínimo e múltiplo** no cadastro do fornecedor (seção 4) — o cálculo já respeita.
3. **Classe ABC na lista de compra** e na ordem de prioridade (seções 5 e 7).
4. **Análise XYZ** de regularidade (seção 5).
5. **Adiar** como estado próprio, com data de volta, e justificativa obrigatória ao
   alterar ou rejeitar (seção 6).
6. **Simulador** de prazo e estoque de segurança, sem tocar no dado oficial (seção 10).
7. **Três alertas novos** e a rotina de segunda e quinta (seção 8).
8. **Produto sem reposição** (peça única) marcado, fora da lista de compra (seção 3).

Qualquer um destes vem com a comparação antes/depois que a ETAPA 5 exige: a lista de
compra calculada pela regra antiga e pela nova, lado a lado, em reais, antes de trocar.

### Caixa 3 — O aviso que precisa ser dito

A seção 6 pede **treze informações por linha**. Em 19/10/2026, cinco dias atrás, ele
escreveu: *"o sistema está trazendo muitas informações, deixando os gestores confusos"*,
e a 1.35.0 foi feita para tirar informação do caminho de quem decide.

As duas instruções se contradizem. O caminho que atende as duas: a tabela continua
enxuta, com o que decide a compra, e os números de apoio (segurança, alvo, 90 dias,
ABC) aparecem na **linha de detalhe de cada produto**, que já existe e já carrega o
motivo. Treze colunas no celular viram rolagem lateral, e rolagem lateral já escondeu
a coluna que decide duas vezes neste projeto.

