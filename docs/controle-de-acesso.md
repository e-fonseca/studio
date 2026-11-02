# Controle de acesso: perfis, permissões e as travas (1.44.0)

Etapa 1 do prompt "Implementação do módulo de usuários e controle de acesso" (Edson,
02/11/2026). O levantamento do que já existia, item por item, e o plano das quatro
etapas estão em `diagnostico-controle-de-acesso.md`. O passo a passo para a gerência está
em `manual/usuarios-e-acessos.md`. A sessão, a senha e a recuperação por código estão em
`sessao-e-acesso.md`.

## Em uma frase

Cada pessoa recebe um ou mais **perfis**; cada perfil é uma lista de **permissões** do
catálogo; toda tela confere a permissão no servidor a cada clique; e quem mexe em acesso
passa por quatro regras que rodam na hora de gravar: ninguém mexe no próprio acesso,
ninguém dá o que não tem, a conta técnica só é mexida por outra conta técnica, e sempre
fica alguém administrando.

## Arquitetura

| Peça | Onde | O que faz |
|---|---|---|
| Catálogo | `apps/contas/catalogo.py` | As 37 permissões que a tela mostra: código estável, nome em português, o que abre, módulo e as marcas de **dinheiro** e de **administração** |
| Perfis que vêm prontos | `apps/contas/perfis.py` | O padrão de cada um dos oito perfis no primeiro dia. Desde a 1.44.0 é só o começo: o que vale é o que está no banco |
| Regras de concessão | `apps/contas/autorizacao.py` | As quatro regras acima, num lugar só (`conferir_mexer_em`, `conferir_dar_ou_tirar`, `conferir_editar_perfil`, `mantendo_um_administrador`) |
| Serviços | `apps/contas/servicos.py` | Toda mudança de acesso passa por aqui, dentro de transação, com as regras e a auditoria |
| Senha de novo | `apps/contas/confirmacao.py` | A área de acessos pede a senha outra vez; 15 minutos desde o último uso; troca a chave da sessão |
| Telas | `apps/contas/views.py`, `fichas.py` | Usuários (lista e busca), ficha da pessoa, Perfis e permissões (matriz) e um perfil |
| Acesso negado | `apps/core/views.py` (`negado`) | O 403 com a frase da gerência, e a tentativa na auditoria |
| Arquivos baixados | `apps/auditoria/servicos.py` (`registrar_arquivo`) | Todo CSV, planilha, PDF ou texto com dado da loja fica na trilha |
| Comandos do servidor | `recuperar_administrador`, `relatorio_de_acessos`, `configurar_perfis`, `desligar_usuario` | Recuperação, conferência e instalação |

O que cada tela exige continua no `permission_required` de cada view, que o Django confere
a cada requisição, lendo do banco: mudar o perfil vale no clique seguinte da pessoa, sem
sair e entrar. Esconder um item do menu não protege nada; quem protege é a view, e a
varredura `apps/contas/tests/test_rotas_por_perfil.py` abre todas as rotas (142 hoje) com
cada perfil a cada execução dos testes.

### Como as permissões se somam

1. **Perfis concedem ações.** Quem tem dois perfis pode a soma dos dois.
2. **Sem perfil, nada.** A conta entra (a senha confere) e não abre tela nenhuma da loja;
   o teste `test_sem_perfil_nao_abre_nada` confere todas as rotas.
3. **As regras de cada processo continuam valendo** por cima do perfil: o pedido de quem
   não tem "Aprovar pedido" nasce esperando a gerência, pedido aprovado não se edita, a
   contagem fechada não se reabre, o processo só se valida depois de testado por outra
   pessoa.
4. **Bloqueio vale mais que perfil**: conta bloqueada ou desligada não entra, tenha o
   perfil que tiver, e as sessões abertas dela caem na hora.
5. **Permissão individual** (fora de perfil) não se dá pela tela. Só o administrador
   técnico, pelo admin do Django, e cada uma fica na auditoria e na lista "O que pede
   atenção" da tela Perfis e permissões.

### As quatro regras de quem mexe em acesso

| Regra | O que impede | Onde |
|---|---|---|
| Ninguém mexe no próprio acesso | Dar a si mesmo um perfil, editar o perfil em que está, bloquear, desligar ou pôr data no próprio acesso | `conferir_mexer_em`, `conferir_editar_perfil` |
| Ninguém dá o que não tem | Dar, tirar ou editar permissão com marca de dinheiro ou de administração sem tê-la; mexer na conta (senha, e-mail, bloqueio, sessões) de quem tem acesso que o ator não tem, porque quem define a senha de alguém passa a poder entrar como ele | `faltam_para`, `conferir_dar_ou_tirar` |
| Conta técnica só pela conta técnica | Quem administra pela tela mexer no superusuário criado no servidor | `conferir_mexer_em` |
| Sempre fica alguém administrando | Tirar, bloquear, desligar ou deixar sem a permissão a última conta ativa, com senha, que administra pessoas **e** perfis. Vale para a tela, para os comandos e para a data marcada para o acesso acabar | `mantendo_um_administrador` |

As regras rodam no servidor, com o que está no banco, e não com o que a tela mostrou: um
POST montado à mão (trocar o número da pessoa no endereço, mandar uma caixa que a tela
mostrou travada, mandar a chave da sessão de outra pessoa) recebe a mesma recusa. Os testes
de `test_controle_de_acesso.py` fazem exatamente isso.

### A senha de novo

Para abrir Usuários, a ficha de alguém ou Perfis e permissões, a pessoa digita a própria
senha outra vez. Vale enquanto ela estiver usando a área e fecha com 15 minutos parada
(o tempo está em `confirmacao.py`).
Ao confirmar, a sessão troca de chave. Cinco senhas erradas seguidas encerram a sessão.
Mudança enviada depois que a janela fechou não é aplicada sozinha: a tela pede a senha e
a pessoa refaz. Quem não administra recebe o 403 direto, sem a tela da senha.

## Modelo de dados

Nada se apaga e nenhuma tabela antiga mudou de forma; a 1.44.0 acrescenta:

| Tabela | Campos novos | Para quê |
|---|---|---|
| `contas_vinculoidentidade` | `bloqueado_em`, `bloqueio_motivo` | Bloqueado (parada temporária) separado de desligado (saiu da empresa) |
| `contas_perfil` (nova) | `grupo` (1 para 1 com o grupo do Django), `descricao`, `padrao`, `ordem`, `retirado_em` | A descrição que a tela mostra, se veio com o sistema, a ordem e o "retirado" (perfil fora de uso sem perder o histórico) |
| `contas_permissaooferecida` (nova) | `grupo`, `codigo`, `oferecida_em` | Quais permissões do padrão o instalador já deu a cada perfil. É o que deixa o `configurar_perfis` acrescentar permissão nova de uma versão sem devolver o que a gerência tirou |

Permissões novas: `contas.editar_perfis`, `compras.ver_compras`, `importacao.ver_vendas`,
`importacao.ver_margem` e `importacao.ver_importacoes`. As quatro últimas vêm da divisão
do `importacao.ver_painel`, que até a 1.43.0 abria todos os números da loja, da lista de
compra à margem.

A sessão (tabela de sessões do Django) guarda a mais, no login, o endereço e o navegador
(`ip`, `aparelho`), e, na área de acessos, a hora da confirmação da senha.

## Os perfis no primeiro dia

Ninguém muda de perfil na atualização. Os quatro de hoje ficam com o que tinham; os quatro
novos ficam prontos, vazios de gente.

| Perfil | Para quem | Pode, no começo |
|---|---|---|
| Administrador gerência | Edson, Henriett, Moizes | Tudo o que está no catálogo |
| Líder de loja | Cássia | O administrativo, mais montar pedido (espera a gerência) e responder sugestões |
| Operador administrativo | | Lançamentos, contas, fornecedores, painéis, contagem, sugestões |
| Operador vendedor | Balcão | Só a consulta de balcão, sem custo nem valor |
| Administrador de acessos | (novo) | Só administrar pessoas: cria conta, define senha, bloqueia, encerra sessão. Não vê número da loja |
| Compras | (novo) | Lista de compra, fornecedores, sugestões e pedidos; o pedido espera a gerência |
| Estoque | (novo) | Consulta, contagem, receber mercadoria e anexar nota, sugerir compra |
| Consulta e auditoria | (novo) | Só olha: indicadores, vendas, pedidos, fornecedores, processos e a auditoria |

A matriz inteira, permissão por permissão (💰 dinheiro, 🔑 administração):

| Permissão | Ger. | Líder | Adm. | Vend. | Acessos | Compras | Estoque | Consulta |
|---|---|---|---|---|---|---|---|---|
| **Indicadores** | | | | | | | | |
| Ver os indicadores 💰 `importacao.ver_painel` | ✓ | ✓ | ✓ |  |  |  |  | ✓ |
| **Compras** | | | | | | | | |
| Ver a lista de compra 💰 `compras.ver_compras` | ✓ | ✓ | ✓ |  |  | ✓ |  |  |
| Mudar a lista de compra 💰 `compras.ajustar_compra` | ✓ |  |  |  |  |  |  |  |
| Sugerir compra `compras.sugerir_compra` | ✓ | ✓ | ✓ |  |  | ✓ | ✓ |  |
| Responder as sugestões da equipe `compras.responder_sugestao` | ✓ | ✓ |  |  |  | ✓ |  |  |
| **Pedidos** | | | | | | | | |
| Ver pedidos e receber mercadoria 💰 `pedidos.view_pedido` | ✓ | ✓ | ✓ |  |  | ✓ | ✓ | ✓ |
| Anexar nota e romaneio `pedidos.anexar_documento` | ✓ | ✓ | ✓ |  |  | ✓ | ✓ |  |
| Fazer pedido ao fornecedor 💰 `pedidos.registrar_pedido` | ✓ | ✓ |  |  |  | ✓ |  |  |
| Aprovar pedido 💰 `pedidos.aprovar_pedido` | ✓ |  |  |  |  |  |  |  |
| **Fornecedores** | | | | | | | | |
| Ver fornecedores 💰 `fornecedores.view_fornecedor` | ✓ | ✓ | ✓ |  |  | ✓ |  | ✓ |
| Mudar a ficha do fornecedor `fornecedores.change_fornecedor` | ✓ | ✓ | ✓ |  |  | ✓ |  |  |
| **Vendas** | | | | | | | | |
| Ver as vendas 💰 `importacao.ver_vendas` | ✓ | ✓ | ✓ |  |  |  |  | ✓ |
| Ver custo e margem 💰 `importacao.ver_margem` | ✓ | ✓ | ✓ |  |  |  |  |  |
| Ver clientes 💰 `clientes.ver_clientes` | ✓ | ✓ | ✓ |  |  |  |  |  |
| **Estoque** | | | | | | | | |
| Consulta de balcão `importacao.consultar_produtos` | ✓ | ✓ | ✓ | ✓ |  | ✓ | ✓ |  |
| Contar o estoque `inventario.contar_estoque` | ✓ | ✓ | ✓ |  |  |  | ✓ |  |
| Fechar contagem e organizar `inventario.fechar_contagem` | ✓ | ✓ | ✓ |  |  |  | ✓ |  |
| **Dinheiro** | | | | | | | | |
| Ver o financeiro 💰 `financeiro.ver_financeiro` | ✓ | ✓ | ✓ |  |  |  |  |  |
| Lançar pagamento previsto 💰 `financeiro.lancar_pagamento` | ✓ | ✓ | ✓ |  |  |  |  |  |
| Ver o caixa 💰 `caixa.ver_caixa` | ✓ | ✓ | ✓ |  |  |  |  |  |
| Conciliar o banco 💰 `conciliacao.conciliar_banco` | ✓ | ✓ | ✓ |  |  |  |  |  |
| **Base de processos** | | | | | | | | |
| Ver processos `processos.view_processo` | ✓ | ✓ | ✓ |  |  |  |  | ✓ |
| Abrir anexos dos processos `processos.ver_anexo` | ✓ | ✓ | ✓ |  |  |  |  | ✓ |
| Escrever processos `processos.documentar_processo` | ✓ | ✓ | ✓ |  |  |  |  |  |
| Registrar teste `processos.registrar_teste` | ✓ | ✓ | ✓ |  |  |  |  |  |
| Validar processo `processos.validar_processo` | ✓ |  |  |  |  |  |  |  |
| Aprovar regra `processos.aprovar_regra` | ✓ |  |  |  |  |  |  |  |
| **Tempo** | | | | | | | | |
| Anotar o tempo do dia `tempo.anotar_tempo` | ✓ | ✓ | ✓ |  |  |  |  |  |
| Ligar a busca do tempo 🔑 `tempo.configurar_tempo` | ✓ |  |  |  |  |  |  |  |
| **Sistema** | | | | | | | | |
| Ver as importações `importacao.ver_importacoes` | ✓ | ✓ | ✓ |  |  |  |  | ✓ |
| Importar agora 🔑 `importacao.executar_importacao` | ✓ |  |  |  |  |  |  |  |
| Dados da empresa 🔑 `compras.change_dadosdaempresa` | ✓ |  |  |  |  |  |  |  |
| Alertas por e-mail e Telegram 🔑 `alertas.configurar_email` | ✓ |  |  |  |  |  |  |  |
| Cópia do programa no GitHub 🔑 `backup.configurar_backup` | ✓ |  |  |  |  |  |  |  |
| Ver a auditoria 💰 🔑 `auditoria.ver_auditoria` | ✓ |  |  |  |  |  |  | ✓ |
| **Acessos** | | | | | | | | |
| Administrar pessoas 🔑 `contas.gerenciar_usuarios` | ✓ |  |  |  | ✓ |  |  |  |
| Editar perfis 🔑 `contas.editar_perfis` | ✓ |  |  |  |  |  |  |  |

37 permissões, 15 com marca de dinheiro e 8 de administração. O Administrador de acessos,
pela regra "ninguém dá o que não tem", só dá perfil sem marca nenhuma que ele não tenha:
hoje, o Operador vendedor e o próprio Administrador de acessos.

Do exemplo de catálogo do prompt, ficaram de fora o que não tem o que proteger no Aux SET:
cotações (não há módulo de cotação), editar produto (o produto é do SET), publicar ou
reverter importação (a importação lê a cópia do backup e não publica nada) e restaurar
backup (se faz no servidor). O teste `test_catalogo.py` lê o código e falha se uma tela
conferir permissão que não está no catálogo, ou se o catálogo tiver permissão que nenhuma
tela confere.

## Auditoria

Além do que já se registrava (entrada, saída, falha de entrada, perfil, senha, desligamento,
data para acabar, recuperação de senha, aprovação de pedido), a 1.44.0 registra:

| Ação | Quando |
|---|---|
| `acesso.negado` | Alguém logado abriu o que o perfil não deixa. Uma vez por minuto por pessoa e endereço, para recarregar a página não encher a trilha |
| `acesso.senha_confirmada`, `acesso.confirmacao_falhou` | A senha de novo da área de acessos |
| `acesso.usuario_bloqueado`, `acesso.usuario_desbloqueado` | Bloqueio, com o motivo |
| `acesso.sessao_encerrada`, `acesso.sessoes_encerradas` | Uma sessão ou todas, com o aparelho |
| `acesso.prazo_nao_cumprido` | A data para acabar passou, mas a pessoa é a última que administra |
| `acesso.administrador_recuperado` | O comando de recuperação no servidor, com o motivo |
| `permissao.perfil_alterado` | Perfil editado pela tela: o que entrou, o que saiu, quantas pessoas estão nele, e o motivo |
| `permissao.perfil_criado`, `permissao.perfil_retirado`, `permissao.perfil_devolvido` | Perfil novo, fora de uso, de volta |
| `permissao.perfil_alterado_por_fora` | Permissão de um perfil mudada fora da tela (admin do Django) |
| `permissao.ver_painel_dividido`, `permissao.grupos_antigos_limpos` | O que a atualização para a 1.44.0 fez, assinado como "atualização 1.44.0" |
| `dados.arquivo_baixado` | CSV, planilha, PDF ou texto com dado da loja: lista de compra, comparação, produtos do fornecedor, margem, vendas do dia, relatórios do inventário, ajustes da contagem, log da importação |

A entrada do superusuário fica marcada como tal. Senha, token e CPF nunca entram na
trilha (`CAMPOS_PROIBIDOS` e o teste `SenhaNuncaNaAuditoriaTest`), e a trilha não se
altera nem se apaga (gatilho no PostgreSQL, migração `auditoria.0002`).

## Instalação

O `atualizar.ps1` de sempre faz tudo, nesta ordem: backup do banco, migrações, e o
`configurar_perfis`. As migrações da 1.44.0:

1. `contas.0007` cria as tabelas de perfil e as colunas do bloqueio.
2. `importacao.0013` e `compras.0006` criam as quatro permissões da divisão.
3. `contas.0008` dá as quatro a todo perfil (e a toda pessoa) que tinha o `ver_painel`:
   na manhã seguinte cada um abre exatamente as mesmas telas. Depois limpa os grupos do
   começo (Gerência, Compras, Estoque, Operadores, Consulta e auditoria) que a reinstalação
   da 1.4.0 recriou em 22/10 com as permissões antigas: os três com nome de perfil novo
   ficam vazios para receber o padrão novo, e os dois que não voltam são apagados se não
   tiverem ninguém. Se tiverem alguém, a pessoa fica onde está e a auditoria registra.

Depois das migrações, o `configurar_perfis` cria os perfis que faltam, grava a descrição
de cada um e acrescenta só a permissão do padrão que aquele perfil ainda não recebeu, uma
vez: o que a gerência tirar pela tela não volta na atualização seguinte. Rodar duas vezes
não duplica nada. Nesta primeira vez ele só acrescenta, aos perfis de hoje, o "Editar
perfis" do Administrador gerência; o resto eles já tinham.

Para conferir antes e depois, no servidor, de dentro de `C:\cabana-sistema\app`:

    ..\python\python.exe manage.py relatorio_de_acessos

## Recuperação

Quando ninguém mais consegue administrar pela tela (a única pessoa esqueceu a senha e não
tem e-mail cadastrado, foi bloqueada por engano, ou a conta técnica não é conhecida), no
servidor, como administrador do Windows, de dentro de `C:\cabana-sistema\app`:

    ..\python\python.exe manage.py recuperar_administrador edson --motivo "esqueceu a senha" --senha

O comando reativa a conta, tira bloqueio e data para acabar, dá o perfil Administrador
gerência, apaga as tentativas de senha errada e, com `--senha`, pede uma senha nova duas
vezes na tela (nunca na linha de comando, que ficaria no histórico do PowerShell). Fica na
auditoria como "linha de comando", com o motivo. Quem roda isso já pode tudo no servidor;
por isso não há regra de autoridade nele, só o registro.

## Testes

Rodados em 02/11/2026 sobre o banco de teste (PostgreSQL 16):

| Arquivo | O que confere |
|---|---|
| `test_controle_de_acesso.py` | As quatro regras pelo serviço e por POST montado à mão; bloqueio e desbloqueio; sessão de outra pessoa; a senha de novo (janela, troca de chave, cinco erros, redirecionamento para fora); 403 na auditoria; senha nunca na trilha; os comandos do servidor; arquivos baixados na auditoria |
| `test_perfis_editaveis.py` | O instalador que não desfaz o que a gerência mudou; editar perfil (pela tela, com caixa travada, com POST manipulado); criar, retirar e devolver perfil; vários perfis; a divisão do `ver_painel` |
| `test_catalogo.py` | O catálogo amarrado ao código, nos dois sentidos |
| `test_rotas_por_perfil.py` | As 142 rotas com cada um dos oito perfis e com a conta sem perfil: nenhuma quebra, o vendedor só abre a consulta, sem perfil não abre nada, o Administrador de acessos não abre número da loja |

O resultado da suíte inteira está em `mudancas.md`, na entrada da 1.44.0.

## O que fica para as próximas etapas

- **Alçada de compra** (etapa 2): limite por valor; quem pede não aprova acima dele; pedido
  aprovado que muda volta para aprovação; trava na aprovação simultânea; custo do pedido só
  para quem tem permissão de custo (hoje o perfil Estoque vê o valor do pedido ao receber).
- **Código do celular para a administração e só HTTPS** (etapa 3, decisão do Edson no
  cartão). Enquanto o balcão entrar por HTTP na 8095, o cookie não pode ser `Secure`.
- **Entrada pela intranet** (etapa 4): depende de saber como a intranet confere quem entra.
  Até lá cada pessoa tem usuário e senha do Aux SET, e o "Estado da integração" da tela de
  usuários diz isso.
- **Convite por e-mail**: a conta nova nasce "Pendente de ativação" (sem senha) e a gerência
  define a senha na ficha. Mandar um link de ativação por e-mail fica para quando a caixa
  `naoresponder@` estiver configurada na loja.
- **Exceção individual com validade**: não há permissão individual pela tela, de propósito
  (o prompt pede evitar na primeira versão). Quem precisar de uma coisa a mais ganha um
  perfil, que pode ter data para acabar na ficha.
- **Sessão pelo endereço seguro (8443)**: a ficha mostra "endereço seguro (https)" em vez do
  IP de quem entrou, porque o túnel do HTTPS entrega a conexão ao sistema como se viesse do
  próprio servidor.
