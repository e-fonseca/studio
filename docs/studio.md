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

Os dois nunca dividem banco, pasta, porta nem tarefa: parar um não mexe no outro.

## Variáveis próprias do Studio

- `STUDIO_ASSUNTOS_DESLIGADOS` (padrão `compras,estoque`): assuntos que saem do menu.
  Vazio liga todos de volta.

## O que ainda falta decidir (perguntas ao Edson)

1. **Instalador**: os scripts `instalar.ps1`, `atualizar.ps1` e `higienizar.ps1` da Cabana não
   estão no repositório `e-fonseca/sistema`. Para instalar o Studio é preciso a versão deles
   com os nomes do Studio.
2. **Usuários**: a migração `contas` da Cabana cria as contas da gerência da Cabana. Quem são
   as pessoas do Studio e em que perfil cada uma entra?
3. **E-mail dos alertas**: os padrões vieram da Cabana; qual caixa o Studio usa?
4. **Dados da empresa** (Sistema > Dados da empresa): razão social, CNPJ 34.331.239/0001-66 e
   endereços do Studio.
5. **SET do Studio**: o mapeamento das tabelas (docs/mapeamento-set.md) foi feito no banco da
   Cabana. A primeira importação do backup do Studio confere se é igual.
6. **Trello e Kommo**: qual quadro do Trello, os nomes das listas, e se a conta do Kommo já
   existe (ver [integracao-agente.md](integracao-agente.md)).
