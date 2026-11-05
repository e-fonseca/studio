# Implantação sem impacto no SET e na operação

Regra do Edson (05/10/2026): o SET não permite integração, o sistema é alimentado só por
relatórios exportados, e nem a implantação nem o uso podem afetar o SET ou a operação da loja.

## O que as telas do servidor mostram (05/10/2026)

Fonte: capturas enviadas pelo Edson. O que não aparece nelas está marcado como “a confirmar”.

| Item | Visto | Consequência para o projeto |
|---|---|---|
| Processador | Intel Core i5-6500T, 4 núcleos, 2,5 GHz | Máquina modesta: limitar CPU e memória do sistema novo |
| Memória | 16 GB, 8 GB em uso (50%) | Sobram cerca de 8 GB; o sistema novo deve usar no máximo 1,5 a 2 GB |
| Disco C: | SSD de 237 GB, 139 GB livres | Espaço suficiente; dados e backups do sistema em pasta própria |
| SET | `C:\Set Sistemas`, banco Firebird 4.0 (`DADOS-SET.FDB`, ~300 MB), pasta `BKPS` | **Não tocar**: nem arquivo, nem serviço, nem porta do Firebird |
| Intranet | Pastas `C:\intranet`, `intranet-dados`, `inetpub`, `php`, `homolog` | Provável IIS + PHP; `/sistema` entra só depois de testado à parte |
| Outros sistemas | Pastas `baloes-*` | A confirmar o que são; não alterar |
| Acesso remoto | TeamViewer, AnyDesk, UltraVNC, Chrome Remote Desktop, Radmin VPN | Ver “Observação de segurança” abaixo |
| Antivírus | Kaspersky Small Office | Pode bloquear o serviço novo; prever exclusão só da pasta do sistema, se necessário |
| Windows | Windows 10 Pro 64 bits, versão 22H2 (compilação 19045), Dell OptiPlex 3050 | Compatível com PostgreSQL 16/17 e Python 3.12. **O suporte do Windows 10 terminou em 14/10/2025**: sem atualizações de segurança, salvo se houver o programa pago de atualizações estendidas (ESU). Ver observação abaixo |

## Regras que o projeto segue

1. **Zero acesso ao SET em uso.** (Leitura de uma cópia do banco é permitida pelo Edson; ver [leitura-firebird.md](leitura-firebird.md).) O sistema não lê nem abre o `DADOS-SET.FDB`, não usa o Firebird, as
   DLLs nem a porta 3050, não instala nada em `C:\Set Sistemas` e não automatiza telas do SET.
   Os dados entram só por relatórios que uma pessoa exporta do SET pelo caminho normal.
2. **Pasta própria.** Tudo em `C:\studio-sistema` (programa, dados, anexos, logs, backups).
   Desinstalar = parar o serviço e apagar a pasta; nada mais muda no servidor.
3. **Banco separado.** PostgreSQL próprio, ouvindo só em `127.0.0.1` numa porta que não esteja em uso
   (verificada antes), com memória limitada (`shared_buffers` 256 MB, até 20 conexões).
4. **Pouco recurso.** Serviço com prioridade abaixo do normal; importações pesadas e backup fora do
   horário da loja; alerta se a CPU ou o disco passarem de um limite.
5. **Intranet intocada.** Primeiro o sistema roda numa porta própria para homologação.
   Só depois de aprovado entra a regra que publica `/sistema` no IIS, com cópia do `web.config`
   antes e reversão em um passo. Nenhuma mudança em VPN, certificados existentes ou firewall
   além de uma regra para a porta nova, restrita à rede interna.
6. **Sem alterar o Windows.** Sem reiniciar o servidor no horário da loja, sem mudar atualizações
   automáticas, sem desativar o antivírus.
7. **Janela combinada.** Instalação fora do expediente, com o Edson acompanhando, e checklist
   de reversão pronto. Antes, cópia dos backups do SET conferida (só leitura, pela rotina que já existe).
8. **Uso sem risco.** A operação continua toda no SET. O sistema novo só sugere; ninguém precisa
   usá-lo para vender, receber ou emitir nota. Se ele parar, a loja não para.

## Ordem de implantação

1. Rodar o levantamento (comandos em [arquitetura.md](arquitetura.md)) e confirmar a versão do Windows e as portas em uso.
2. Instalar em `C:\studio-sistema` com porta própria e acesso só pela rede interna.
3. Importar relatórios de teste e conferir com o Edson.
4. Uma semana de uso paralelo; medir CPU, memória e disco do servidor antes e depois.
5. Publicar em `/sistema` no IIS, com reversão pronta.

## Observação de segurança

As telas mostram cinco ferramentas de acesso remoto no servidor que guarda o banco do SET,
e uma sessão de compartilhamento com uma conta Gmail. Vale confirmar com quem cuida do
servidor quais são realmente usadas e manter só essas, com senha forte e
autenticação em dois fatores. Isso não faz parte do sistema novo e nada foi alterado.

## Observação sobre o Windows 10

O Windows 10 deixou de receber atualizações de segurança em 14/10/2025. Com cinco programas de
acesso remoto e o banco da loja na mesma máquina, isso aumenta o risco de invasão e de ransomware.
Opções: confirmar se há ESU ativo; planejar atualização para Windows 11 (o i5-6500T não está na
lista oficial de processadores suportados) ou troca do servidor. O sistema novo funciona em
qualquer um dos casos, e o backup criptografado fora do servidor passa a ser ainda mais importante.
