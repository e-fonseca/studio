# Sistema auxiliar do Studio Industrial

Sistema web local de apoio à gestão do **Studio Industrial** (móveis industriais sob medida),
auxiliar ao SET Sistemas. Não substitui o ERP nem a emissão fiscal. Copiado por inteiro do
sistema auxiliar da Cabana do Jacarandá (`e-fonseca/sistema`, 1.48.0) em 05/11/2026; o que
é só do Studio está em [docs/studio.md](docs/studio.md).

Endereço: `https://192.168.3.254:8444/studio/` (e `http://192.168.3.254:8096/studio/` no
balcão), acessível pela rede da loja e pela VPN. Na intranet, menu **Gestão > Sistema aux SET**
do Studio.

## O que é só do Studio (2.0.0 e 2.1.0)

- **Leads** (SDR): o que falar hoje, o funil por etapa, cada conversa registrada e o botão que
  transforma o lead fechado em projeto.
- **Pedidos** sob medida e **oficinas parceiras**: o número do card do Trello, etapa, prazo,
  venda, o que o cliente já pagou, margem de lucro e os pagamentos à oficina calculados pela
  regra de cada uma (padrão, parcelas mensais com corte, ou tudo no cartão).
- **Planejamento** (2.1.0, regras do protótipo da Henriett): caixa dos próximos 30 dias, a
  pagar por cartão e oficina, a receber em Pix, fechamento por competência e caixa, saldo
  entre Studio e Cabana, pró-labore e alertas ([como funciona](docs/planejamento.md)).
- **Fluxo de caixa**: o que entrou, o que saiu e a projeção dos próximos seis meses, pelo
  financeiro do SET.
- **Sem compras e sem estoque no menu** (`STUDIO_ASSUNTOS_DESLIGADOS=compras,estoque`).
- **Integração com o Trello e o Kommo** pelo agente da casa do Edson, por uma API com chave
  própria, pela VPN ([como funciona](docs/integracao-agente.md)).

## O que veio da Cabana


- **Base de processos** para transferir o conhecimento da Bárbara: quadro Kanban com os
  estados *A levantar*, *Em documentação*, *Em teste por outra pessoa* e *Validado pela gestão*;
  procedimento com versões imutáveis; separação entre declaração, observação prática e regra
  aprovada; testes por outra pessoa; anexos com validação; busca e filtros.
- **Perfis e permissões** por ação, conferidos no servidor: Gerência, Compras, Estoque,
  Operadores, Consulta e auditoria.
- **Trilha de auditoria** somente inclusão (aplicação e gatilho no PostgreSQL), com ID de correlação.
- **Segurança básica**: CSRF, cookies HttpOnly/SameSite sob `/sistema`, bloqueio após 5 tentativas
  de login, anexos fora da pasta pública e baixados só com permissão, recusa de senha e CPF nos textos.
- **Tudo sob `/sistema`**: rotas, estáticos, cookies e redirecionamentos.
- **Diagnóstico de compras**: a partir de uma planilha montada com relatórios do SET, mostra
  dinheiro parado sem venda, excesso, compra acima do necessário, itens em falta e o que comprar,
  com o motivo de cada número ([como usar](docs/diagnostico-de-compras.md)).
- **Importação dos dados do SET**: toda noite o sistema copia o backup que o SET já gera -- em
  `.FDB`, `.FBK` ou `.zip` com um deles dentro -- e lê a cópia num Firebird próprio, registrando
  cada execução ([como funciona](docs/leitura-firebird.md)).
- **Painel de compras e estoque**: os mesmos números do diagnóstico na tela, com a data dos dados
  sempre visível e aviso em todas as páginas quando a informação fica velha. Durante a importação a
  tela mostra a barra de progresso e a etapa; ao terminar, avisa se deu certo e, se deu erro,
  explica o que aconteceu e o que fazer.
- **Ajuda guiada (F1)**: em qualquer tela, F1 (ou o botão Ajuda) abre um tour que destaca cada parte
  e explica para que serve, sem depender de internet.
- **Log de cada importação**: cada execução grava passo a passo, com hora, qual backup foi escolhido,
  o tamanho e a data do arquivo, cada etapa da leitura e os números apurados -- ou em que ponto parou.
  O log aparece na tela de Importações, pode ser baixado em texto e também vai para
  `logs\importacao.log` no servidor.
- **Versão visível**: o número da versão aparece no pé de todas as telas e fica gravado em cada
  importação, para saber qual pacote gerou cada número. O histórico está em
  [docs/mudancas.md](docs/mudancas.md); o número fica no arquivo `VERSAO`.

**O sistema nunca toca no SET em uso**: não abre o `DADOS-SET.FDB` do caixa, não fala com o
serviço Firebird do SET (porta 3050) e não escreve nada em `C:\Set Sistemas`. Ele lê uma cópia do
backup, com um motor Firebird próprio configurado para não acessar servidor nenhum; relatórios
exportados seguem como alternativa. Ver [implantação sem impacto](docs/implantacao-sem-impacto.md).

O que é **provisório** está marcado: contas locais (até definir a integração com a intranet),
cores e logotipo (até receber a identidade oficial). Ver [docs/plano-inicial.md](docs/plano-inicial.md).

## Rodar em desenvolvimento

Requer Python 3.11+ e PostgreSQL 14+.

```bash
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export STUDIO_SECRET_KEY=dev STUDIO_DB_NOME=cabana STUDIO_DB_USUARIO=cabana
python manage.py migrate
python manage.py configurar_perfis
python manage.py carregar_roteiro --prazo AAAA-MM-DD   # último dia do aviso prévio
python manage.py createsuperuser
python manage.py runserver
```

Abrir `http://127.0.0.1:8000/sistema/`. Para incluir alguém num perfil, use
`/sistema/admin/` (Usuários → Grupos).

## Testes

```bash
python manage.py test --settings=config.settings.test
```

Usa o PostgreSQL configurado pelas variáveis `STUDIO_DB_*` (cria e apaga um banco de teste).
Resultado mais recente em [docs/evidencias-testes.md](docs/evidencias-testes.md).

## Comandos de operação

| Comando | Para quê |
|---|---|
| `configurar_perfis` | Cria ou atualiza os perfis e suas permissões (idempotente). |
| `carregar_roteiro [--fonte Bárbara] [--prazo AAAA-MM-DD]` | Cria no quadro os 21 processos a levantar. |
| `desligar_usuario <usuario> --motivo "..."` | Bloqueia quem saiu e encerra as sessões abertas. |
| `diagnostico_compras planilha.xlsx --dias 90 --data-corte AAAA-MM-DD --saida relatorio.csv` | Gera o diagnóstico de compras. Só lê o arquivo. |
| `importar_set [--arquivo caminho] [--automatica]` | Lê uma cópia do backup do SET e atualiza o painel. Não acessa o banco em uso. |

## Documentação

- [Implantação sem impacto no SET e na operação](docs/implantacao-sem-impacto.md)
- [Diagnóstico de compras](docs/diagnostico-de-compras.md)
- [Leitura do banco do SET por cópia, sem impacto](docs/leitura-firebird.md)
- [Mapeamento das tabelas do SET](docs/mapeamento-set.md)
- [Plano inicial: entendimento, prioridades, arquitetura, fases, backlog e aceite](docs/plano-inicial.md)
- [Roteiro de coleta dos processos da Bárbara](docs/roteiro-coleta-processos.md)
- [Modelo de dados](docs/modelo-de-dados.md)
- [Arquitetura e decisões](docs/arquitetura.md)
- [Por que o login ficou lento, e o que foi feito](docs/login-rapido.md)
- [Perguntas pendentes](docs/perguntas-pendentes.md)
- [Evidências de testes](docs/evidencias-testes.md)
- [Manual: base de processos](docs/manual/base-de-processos.md)
