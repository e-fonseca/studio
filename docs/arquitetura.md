# Arquitetura e decisões

## Decisões tomadas

| # | Decisão | Motivo | Reversível? |
|---|---|---|---|
| D1 | Django 5.2 LTS + PostgreSQL | Pilha candidata do briefing; LTS até 04/2028; maduro em segurança | Sim, antes de crescer |
| D2 | Prefixo `/sistema` nas próprias rotas (sem `FORCE_SCRIPT_NAME`) | Funciona igual com o proxy repassando o caminho intacto e no servidor de desenvolvimento | Sim |
| D3 | Regras de negócio em `regras.py`, chamadas pelas telas | A regra fica no servidor; nenhum clique ou URL a contorna | — |
| D4 | Perfis como grupos do Django com permissões por ação | Simples, auditável; o SSO dirá quem é a pessoa, os perfis continuam locais | Sim |
| D5 | Auditoria somente inclusão com gatilho no PostgreSQL | Protege contra alteração por fluxo comum; um DBA ainda pode remover (proteção proporcional) | Sim |
| D6 | Versões de procedimento imutáveis e trava otimista por número de versão | Rastreabilidade e nenhuma perda de edição simultânea | — |
| D7 | Anexos fora da pasta pública, nome no disco = SHA-256, baixados por view com permissão | Evita traversal, acesso por URL adivinhada e execução no navegador | — |
| D8 | django-axes para bloqueio após 5 falhas (15 min) | Proteção contra força bruta até haver SSO | Sim |
| D9 | Fila de tarefas no PostgreSQL (a implementar) em vez de Celery/Redis | Compatível com Windows, persistente, sem serviço extra | Sim |

## Implantação no Windows: opções

| Opção | Como | Prós | Contras |
|---|---|---|---|
| A. Nativa | PostgreSQL para Windows (serviço), Python + Waitress como serviço (NSSM ou WinSW), IIS com URL Rewrite/ARR ou Caddy como proxy HTTPS em `/sistema` | Sem virtualização; usa o IIS se a intranet já estiver nele | Atualizações do Python e do serviço no Windows exigem cuidado |
| B. VM Linux no Hyper-V | Ubuntu LTS com PostgreSQL, Gunicorn e Nginx; o proxy do Windows encaminha `/sistema` | Ambiente padrão do Django, fácil de reproduzir em homologação | Exige Hyper-V, RAM extra e manutenção de outra máquina |

A escolha depende do levantamento abaixo. Docker Desktop não é pressuposto (licença paga em empresas acima de certo porte e exige WSL2/Hyper-V).

## Levantamento do servidor (para a resposta 1)

Rodar no PowerShell do servidor, como administrador, e enviar o resultado (sem senhas):

```powershell
Get-ComputerInfo | Select-Object WindowsProductName, WindowsVersion, OsArchitecture, CsTotalPhysicalMemory, CsNumberOfLogicalProcessors
Get-PSDrive -PSProvider FileSystem | Select-Object Name, Used, Free
Get-WindowsFeature Web-Server, Hyper-V -ErrorAction SilentlyContinue | Select-Object Name, InstallState
Get-Service | Where-Object { $_.Status -eq 'Running' } | Select-Object Name, DisplayName
Get-NetTCPConnection -State Listen | Select-Object LocalAddress, LocalPort, OwningProcess | Sort-Object LocalPort
```

E responder: a intranet roda nesse servidor? Em qual endereço e tecnologia? Há certificado
HTTPS e quem o emitiu? Existe Active Directory?

## Identidade e intranet

Ordem de preferência, a confirmar com a resposta 2:

1. **OIDC** (se a intranet ou um provedor como Keycloak/Entra ID oferecer): SSO, MFA e desligamento centralizados.
2. **LDAP/Active Directory**: login com a conta da rede; permissões continuam no sistema.
3. **Cabeçalho de proxy autenticado** (se a intranet autentica no IIS com Windows Authentication).
4. Se a intranet só tiver usuários próprios em banco: **não copiar hashes**; avaliar com a gestão e decidir antes de implementar.

Até lá: contas locais provisórias, uma por pessoa, senha mínima de 12 caracteres.

## Segurança: o que já está e o que falta

Já: autorização no servidor por ação, CSRF, escape de saída, ORM parametrizado, cookies
HttpOnly/SameSite com caminho `/sistema` (Secure em produção), sessão de 8 horas que expira
ao fechar o navegador, encerramento de sessões ao desligar usuário, bloqueio por força bruta,
validação de anexos por conteúdo, `X-Frame-Options: DENY`, `nosniff`, logs sem senha.

Falta: Content-Security-Policy completa, MFA (via SSO), limites de requisição por rota,
verificação automática de dependências (pip-audit) e lockfile com hashes gerado no servidor,
delegações temporárias de perfil, política de retenção da auditoria.

## Backup (a implementar na fase 1)

`pg_dump` em formato custom + anexos, compactados e **criptografados antes do envio**
(ex.: age ou 7-Zip AES-256), cópia local em disco separado e cópia externa no Google Drive da
conta da Cabana via OAuth com escopo `drive.file`. Chave de recuperação guardada fora do
servidor e fora do Drive. Restauração mensal em banco separado com registro do resultado.
Metas a aprovar: RPO 24 h, RTO 4 h.
