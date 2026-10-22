# Roteiro de coleta dos processos da Bárbara

Objetivo: que outra pessoa consiga executar cada rotina usando só o que foi escrito,
antes do último dia do aviso prévio. Datas reais e duração dependem da gestão.

## Como organizar

- **Sessões curtas**: 45 minutos, no máximo duas por dia, um processo (ou dois pequenos) por sessão.
- **Ordem**: primeiro os de criticidade alta e os que só ela faz; contatos de fornecedores logo no começo.
- **Quem participa**: a Bárbara, quem vai documentar (Compras ou Estoque) e, quando possível,
  o futuro titular ou substituto do processo.
- **Onde registrar**: direto no sistema, em *Base de processos*, no cartão do processo.
- **Proposta de calendário** (ajustar à data real de saída):
  - Semana 1: abertura e fechamento, registro de vendas, recebimento e conferência, contatos de fornecedores.
  - Semana 2: cadastro de produtos e códigos, formação de preços, compras e pedidos, prazos de reposição, relatórios do SET.
  - Semana 3: inventário, estoque e pedidos do site, contas e conciliações, trocas, devoluções e cancelamentos.
  - Semana 4: consignação, quebras e perdas, descontos, variações artesanais, sazonalidade, exceções.
  - Em paralelo a partir da semana 2: testes por outra pessoa e validação pela gestão.
  - Última semana do aviso: só testes, correções e transferência de responsabilidades.

## Roteiro de cada sessão

1. **Abrir o cartão** do processo e conferir título, área e criticidade.
2. **Pedir para ela mostrar fazendo** (de preferência na rotina real), em vez de só contar.
3. Perguntar e registrar nos campos do procedimento:
   - Para que serve? O que dá errado se não for feito? → *Objetivo*
   - O que faz você começar? Em que horário ou situação? → *Gatilho*, *Frequência*
   - O que precisa estar pronto antes (acessos, papéis, materiais)? → *Pré-requisitos* (sem senhas)
   - Passo a passo, em que tela, qual botão → *Passos*, *Tela de origem*
   - Que papéis ou arquivos entram e saem? → *Documentos de entrada e de saída*
   - Como você confere que deu certo? → *Conferências*, *Evidência de conclusão*
   - O que costuma dar errado? O que fazer quando acontece? → *Exceções*
   - Precisa de autorização de alguém? → *Aprovação necessária*
   - Um exemplo real, sem dados de clientes → *Exemplos anonimizados*
4. **Separar as afirmações** no bloco “O que foi dito, observado e aprovado”:
   - *Declaração*: o que a Bárbara disse (“sempre confiro o lacre”).
   - *Observação prática*: o que foi visto acontecendo (“na entrega de hoje, o lacre não foi conferido”).
   - *Regra aprovada*: só a gerência registra, depois de decidir.
5. **Anexar** modelos de planilha, telas (sem dados pessoais) e fotos de etiquetas ou etapas físicas.
   Fotos ou gravações com pessoas só com autorização registrada.
6. **Definir titular e substituto** do processo depois da saída.
7. **Salvar a versão** e marcar a próxima sessão.

## Teste por outra pessoa

1. A pessoa que vai assumir abre o cartão no celular ou computador e executa o processo real
   (ou em ambiente seguro, quando houver risco), **sem pedir ajuda** a quem já fazia.
2. Registra em *Registrar meu teste*: resultado, se usou só a documentação e as dificuldades.
3. Se não conseguiu, o processo volta para documentação automaticamente; ajusta-se o texto e testa-se de novo.
4. Com um teste aprovado, a gerência valida.

## Perguntas específicas por área

- **Abertura e fechamento**: horários, conferência de caixa, troco, sangria, quem fica com as chaves (sem códigos de alarme no sistema).
- **Cadastro e códigos**: como nasce um código, padrão de nome, unidade, o que fazer com peça única ou variação de cor/tamanho artesanal, como evitar código duplicado.
- **Preços e descontos**: fórmula de preço (markup? arredondamento?), quem autoriza desconto e até quanto.
- **Vendas, trocas, devoluções e cancelamentos**: prazos, o que volta para o estoque, como fica no SET.
- **Recebimento**: conferência contra pedido, divergência, mercadoria sem nota, artesão sem CNPJ.
- **Inventário, quebras e perdas**: frequência, contagem parcial ou completa, quem aprova ajuste.
- **Consignação**: quem são os consignantes, como se controla e acerta.
- **Compras e fornecedores**: lista de contatos (telefone, canal preferido), prazos reais, lotes mínimos, quem é confiável, sazonalidade de compra. **Conferir que nenhum contato depende do celular ou e-mail pessoal da Bárbara.**
- **Contas e conciliações**: o que ela confere, onde, com que frequência.
- **Relatórios do SET**: quais usa, como exporta, em que formato, que horas os dados ficam completos. Pedir uma amostra de cada.
- **Site**: como o estoque do site é atualizado hoje, quem mexe no Bling e na Nuvemshop, problemas de venda sem estoque.
- **Exceções**: “o que só você sabe resolver?”

## Transferência de responsabilidades e acessos

- Antes da saída: listar acessos que ela tem (SET, Bling, Nuvemshop, e-mails, grupos de WhatsApp,
  fornecedores) e quem assume cada um. Não registrar senhas no sistema.
- No último dia: a gerência roda `desligar_usuario` (ou desativa no SSO), troca senhas compartilhadas
  existentes e transfere contas de fornecedores para canais da empresa.
