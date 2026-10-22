# Verificação geral do sistema (1.20.2, 08/10/2026)

O Edson pediu, junto com os dois ajustes do Dashboard: "em seguida, fazer uma verificação
geral em todo o sistema para buscar falhas, bugs, erro de lógica, mitigar todos e
corrigi-los". Este arquivo registra **como** o sistema foi varrido e **o que** foi achado,
para a próxima verificação não começar do zero.

O sistema tem 18 telas de menu, 59 rotas e três perfis de acesso. Olhar tela por tela à
mão não prova nada: a varredura foi feita por programa, e os programas ficaram em
`/tmp` por serem descartáveis — o que vale guardar é o método e o resultado.

## Segunda verificação (1.24.1, 11/10/2026): a varredura virou teste

O Edson pediu "uma revisão para prevenir erros ou futuras inconsistências". A resposta
mais útil não foi varrer de novo à mão: foi descobrir **por que a varredura de 1.20.2
não serviu**.

Ela dizia, na tabela acima, "59 rotas × 3 perfis, nenhum vazamento". Estava errada. A
tela `/sistema/versoes/` pedia só login, e o histórico de mudanças que ela mostra cita
os números que cada versão consertou: R$ 1.576.325,86 de faturamento, R$ 818.075,84 de
lucro bruto, 54,5% de margem, R$ 741.845,19 parados na prateleira, as diferenças de
caixa. O `Operador vendedor`, que por decisão do Edson só pode ver a consulta de balcão,
abria tudo isso digitando o endereço. O furo existia desde que a tela nasceu.

Uma conferência feita à mão, uma vez, envelhece no dia seguinte: toda versão acrescenta
tela, e ninguém refaz a varredura inteira. A 1.24.0 sozinha acrescentou seis rotas, e
hoje são 155.

Por isso a varredura deixou de ser um programa descartável em `/tmp` e virou
`apps/contas/tests/test_rotas_por_perfil.py`, que roda junto com todos os outros testes.
A lista de rotas **não se digita lá**: é lida do próprio Django, com `get_resolver()`.
Tela nova entra na conferência no dia em que nasce, sem ninguém lembrar de nada.

O que ele garante, a cada execução:

| Garantia | O que falha se alguém esquecer |
| --- | --- |
| O vendedor só abre a consulta de balcão | tela nova de dinheiro sem `permission_required` |
| A consulta de balcão continua abrindo para ele | permissão apertada demais por engano |
| Nenhuma rota responde 500, em nenhum perfil | erro de programação em tela pouco visitada |
| Quem não entrou não abre nada | tela nova sem `login_required` |
| O histórico de versões é tela de dinheiro | a correção de 11/10/2026 sendo desfeita |

O que ele não cobre, de propósito: `/sistema/admin/`, que é o admin do próprio Django e
exige `is_staff` — nenhuma tela do sistema concede isso, só um superusuário criado à mão
no servidor. E rota com argumento é chamada com um número que não existe: o que se
confere nela é a recusa, não o conteúdo.

### O resto da revisão

As outras varreduras foram refeitas e passaram:

- **Foto da importação**: toda consulta a dado do SET filtra por `importacao`. As nove
  que o programa apontou são `bulk_create` (escrita) ou consulta já presa a um objeto
  de uma foto só.
- **Variável de template inexistente**: um achado, o mesmo falso de 1.20.2
  (`fornecedores:ficha` sem fornecedor escolhido).
- **Apelido de soma com nome de campo**: nenhum caso real. O programa aponta onze, mas
  o defeito só existe quando o apelido é usado por uma soma **posterior do mesmo
  `annotate`**, e isso não acontece em lugar nenhum. O `despesas_por_grupo`, que parece
  o pior caso (`valor=Sum("valor_pago")` num modelo que tem campo `valor`), foi conferido
  com teste: devolve a soma, não o campo.
- **Migração faltando**: `makemigrations --check` não detecta mudança nenhuma.
- **`check --deploy`**: só o aviso de HSTS, intencional — o sistema é servido na rede da
  loja, e HSTS fixaria HTTPS no navegador de todo mundo.
- **Os três conferidores da skill** (`.claude/skills/cabana-reporting-system/scripts/`):
  passam. Eles ganharam uma correção de recado: com o banco fora do ar despejavam
  quarenta linhas de Python, e agora dizem em português que o banco não respondeu e o
  que conferir.


## As seis varreduras

| Varredura | O que procura | Resultado |
| --- | --- | --- |
| Rotas × perfis | erro 500, ou tela de dinheiro aberta ao vendedor | 59 rotas × 3 perfis, nenhum 500, nenhum vazamento |
| Variável de template inexistente | `{{ nome_errado }}`, que o Django mostra em branco | 49 telas, nenhuma |
| Navegador (Playwright) | erro de JavaScript, requisição falhada, barra horizontal | 29 telas × 3 larguras (1600, 1024 e 390px), nada |
| `manage.py check --deploy` | configuração insegura | só o aviso de HSTS, que é intencional |
| Foto da importação | consulta ao dado do SET sem filtrar por `importacao` | invariante mantida em todo o código |
| Dinheiro em `float` | arredondamento de centavo | nenhum: tudo `Decimal` |

Duas observações sobre o método, porque custaram tempo:

- **Variável que não existe não dá erro no Django**, sai em branco na tela. Para achar,
  roda-se a varredura com `string_if_invalid` configurado para gritar — é um settings
  separado, não serve em produção. O único achado foi falso: `fornecedores:ficha` aberta
  sem `?nome=` não tem fornecedor para mostrar, e é esse o comportamento.
- **O teste automatizado não vê CSS**. Barra horizontal no celular, texto cortado, barra
  flutuando fora do trilho: isso só aparece medindo a página renderizada. Daí o
  Playwright nas três larguras, que foi o que pegou os dois defeitos do gráfico.

## Os quatro defeitos achados

Os dois primeiros mudam número que o Edson já viu na tela, então estão explicados em
`docs/dashboard.md` com os valores de antes e de depois.

1. **Saldo negativo do SET contava como dinheiro a menos no estoque.** 1.456 produtos
   estão com saldo negativo porque a loja nunca fez contagem física. A soma
   `estoque × custo` levava esses negativos, encolhendo o valor do estoque em
   R$ 126.812,28. Saldo negativo é erro de cadastro, não prateleira devendo mercadoria:
   agora conta como zero, nas duas telas que somam estoque, e a tela diz quantos são.
   Estoque: **R$ 615.032,91 → R$ 741.845,19**. Cobertura: **10,3 → 12,4 meses**.
2. **"Parado sem vender" do Dashboard misturava consumo próprio.** DIVERSOS e CONSUMO
   PROPRIO não são mercadoria de revenda, e por isso o Dashboard e "O que fazer agora"
   mostravam valores diferentes para a mesma coisa. O filtro passou a ser a mesma função
   nas duas telas (`so_mercadoria`). Parado: **R$ 194.473,44 → R$ 227.005,64**.
3. **O faturamento do Dashboard e o da Visão geral não batiam, e nada explicava.** A
   Visão geral mostra **R$ 1.576.325,86**, que é o preço dos itens vendidos; o Dashboard
   mostra **R$ 1.538.337,98**, que é o que a venda fechou depois do desconto do balcão. Os
   dois números estão certos — faltava a frase, e duas telas discordando em R$ 38 mil sem
   explicação é o tipo de coisa que faz o dono do sistema desconfiar de tudo. Agora cada
   cartão diz qual dos dois é, e o da Visão geral traz os dois.
4. **A tela de fornecedor sem `?nome=`** era o falso positivo acima: confirmada como
   comportamento, sem mudança.

## O que a varredura NÃO cobre

Dito aqui para ninguém ler este arquivo como "o sistema está sem defeito":

- **Regra de negócio errada passa.** Se o teto mensal de compra estivesse na conta errada,
  as seis varreduras passariam. O que protege isso são os testes de `apps/compras` e a
  conferência contra o diagnóstico em planilha.
- **O Windows do servidor não é varrido aqui.** PowerShell, serviço, túnel TLS e tarefa
  agendada só se provam no servidor da loja.
- **Dado que ainda não apareceu.** A importação lê o backup do dia; mês que vem pode
  trazer um registro que derrube uma conta que hoje passa.
