# O sistema do Studio Industrial

Copiado por inteiro do sistema auxiliar da Cabana (`e-fonseca/sistema`, 1.48.0) em
05/11/2026, a pedido do Edson: *"pode reusar o código, porem com o perfil da empresa studio
industrial / usar github e-fonseca/studio, fazer copia completa"*. O que mudou para o Studio
está em [mudancas.md](mudancas.md), na 2.0.0; este arquivo diz como ele roda ao lado do da
Cabana e o que ainda falta decidir.

## Ao lado do sistema da Cabana, no mesmo servidor

| | Cabana | Studio |
|---|---|---|
| Repositório | `e-fonseca/sistema` | `e-fonseca/studio` |
| Pasta | `C:\cabana-sistema` | `C:\studio-sistema` |
| Configuração | `config\cabana.env`, variáveis `CABANA_*` | `config\studio.env`, variáveis `STUDIO_*` |
| Endereço | `:8095/sistema/` e `https :8443/sistema/` | `:8096/studio/` e `https :8444/studio/` |
| Banco PostgreSQL | `cabana` | `studio` (usuário próprio) |
| Backup do SET | `C:\backup-Set\Cabana\Set-Cabana` | `C:\backup-Set\Studio\Set-Studio` |
| Tarefas do Windows | `\Cabana\CabanaSistema`, `CabanaImportacao` | `\Studio\StudioSistema`, `StudioImportacao` |
| Certificado | autoridade "Cabana do Jacaranda" | autoridade "Studio Industrial" |
| Pacote de atualização | `C:\instalacao\pacote` | `C:\intranet\pacotes\studio` (2.2.0) |
| Cookies | `cabana_sessao`, `cabana_csrf` em `/sistema` | `studio_sessao`, `studio_csrf` em `/studio` (2.2.0) |

Os dois nunca dividem banco, pasta, porta nem tarefa: parar um não mexe no outro.

## Dentro da intranet (2.2.0)

A intranet (`https://192.168.3.254/intranet/`, v1.78.0) mostra o Studio num quadro ao lado do
menu dela, em Gestão › Sistema aux SET, a pedido do Edson (06/11/2026): *"queria que o
sistema aux studio abrisse ao lado do menu dentro da pagina da intranet e não abrisse um
outro link"*.

- Quem deixa o quadro abrir é o Studio: `apps/core/moldura.py` responde com
  `Content-Security-Policy: frame-ancestors 'self'` mais os endereços de
  `STUDIO_INTRANET_ORIGENS` (padrão `https://192.168.3.254`), e tira o `X-Frame-Options: DENY`.
  Variável vazia volta ao `DENY`. Outro site continua sem poder emoldurar o sistema.
- O login continua o do Studio. A intranet está noutra origem (porta 443 contra 8444): ela não
  lê o quadro, e o quadro não lê a intranet. Os cookies funcionam lá dentro porque os dois são o
  mesmo site (mesmo servidor, mesmo `https`).
- O aparelho precisa confiar no certificado do Studio (tela Certificado): dentro de um quadro o
  navegador não mostra o aviso de "não seguro", só recusa. A intranet percebe e mostra um aviso
  com o botão de abrir em outra aba.
- Se a intranet for aberta também por um nome de máquina, o nome entra em
  `STUDIO_INTRANET_ORIGENS` (`https://nome`), separado por vírgula.

## Variáveis próprias do Studio

- `STUDIO_ASSUNTOS_DESLIGADOS` (padrão `compras,estoque`): assuntos que saem do menu.
  Vazio liga todos de volta.

## O que ainda falta decidir (perguntas ao Edson)

1. **Instalador**: os scripts `instalar.ps1`, `atualizar.ps1` e `higienizar.ps1` da Cabana não
   estão no repositório `e-fonseca/sistema`. Para instalar o Studio é preciso a versão deles
   com os nomes do Studio.
   **A pasta do pacote é `C:\intranet\pacotes\studio`** (decidido em 06/11/2026, a pedido
   do Edson; ADR 0020 da intranet). O zip, os comandos e as subpastas `logs`, `downloads` e
   `historico` ficam ali; o programa continua em `C:\studio-sistema`. O código já mostra esse
   caminho (Ficha técnica, diagnóstico da importação, `apps/core/pastas.py`), e os scripts,
   quando vierem da Cabana, têm de trocar `C:\instalacao` por ele: os testes de
   `apps/core/tests/test_atualizador.py` passam a cobrar isso assim que eles entrarem em
   `implantacao/`.
2. **Usuários**: a migração `contas` da Cabana cria as contas da gerência da Cabana. Quem são
   as pessoas do Studio e em que perfil cada uma entra?
3. **E-mail dos alertas**: os padrões vieram da Cabana; qual caixa o Studio usa?
4. **Dados da empresa** (Sistema > Dados da empresa): razão social, CNPJ 34.331.239/0001-66 e
   endereços do Studio.
5. **SET do Studio**: o mapeamento das tabelas (docs/mapeamento-set.md) foi feito no banco da
   Cabana. A primeira importação do backup do Studio confere se é igual.
6. **Trello e Kommo**: qual quadro do Trello, os nomes das listas, e se a conta do Kommo já
   existe (ver [integracao-agente.md](integracao-agente.md)).
7. **Planejamento (2.1.0)**: a exportação do protótipo veio com os movimentos entre empresas
   só com a data; quem lança os de outubro de novo (ou exporta outra vez)? O saldo em conta
   veio sem data, e o dia do Pronampe está "a confirmar". Ver [planejamento.md](planejamento.md).
