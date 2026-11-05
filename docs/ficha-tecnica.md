# Ficha técnica do sistema (1.21.0)

Tela em `/sistema/processos/ficha-tecnica/`, código em `apps/processos/ficha_tecnica.py`.

## Por que ela existe, e por que dentro da Base de processos

Em 08/10/2026 o Edson perguntou "qual a linguagem de programação utilizada e versão do
banco de dados" e, com a resposta na mão, pediu: "incorporar essas informações dentro de
base de processos".

O lugar é o certo e não é por acaso. A Base de processos existe para o que está na cabeça
de uma pessoa não se perder, e quem um dia precisar manter este sistema sem ter
participado de nada disto precisa exatamente dessa lista. A tela do quadro passou a dizer
isso em uma frase: vale para o trabalho da loja e vale para o próprio sistema.

## A regra que manda no arquivo: ler, nunca digitar

Nenhuma versão é escrita à mão. Versão digitada envelhece em silêncio — basta uma
atualização de dependência e a ficha passa a mentir, e ficha que mente é pior do que ficha
nenhuma, porque a pessoa age por ela.

| O que a tela mostra | De onde vem |
| --- | --- |
| Python | `platform.python_version()` |
| Django | `django.get_version()` |
| PostgreSQL | `connection.pg_version`, a conexão que o sistema já usa |
| psycopg, Waitress, firebird-driver, django-axes, openpyxl, cryptography | `importlib.metadata.version`, o que o instalador de fato instalou |
| Firebird: versão | `STUDIO_FIREBIRD_VERSAO` no `studio.env`, gravada pelo instalador |
| Firebird: arquitetura | primeiros bytes do próprio `fbclient.dll` (`_arquitetura_do_pe`) |
| Sistema operacional | `platform.system()` e `platform.release()` |
| Versão do sistema | arquivo `VERSAO` da raiz (`apps/core/versao.py`) |
| Caminhos | as próprias configurações (`BASE_DIR`, `IMPORTACAO_*`, `MEDIA_ROOT`) |

O que **não** puder ser lido aparece escrito "não foi possível ler agora", com etiqueta de
atenção. Nunca um palpite, e nunca um valor antigo guardado.

Duas escolhas dentro dessa regra custaram pensamento:

- **O PostgreSQL responde, mas pode não responder.** `connection.pg_version` abre conexão,
  e com o banco parado isso levanta exceção. A ficha captura e segue: uma tela de
  documentação nunca pode cair por causa daquilo que documenta. Há teste disso.
- **O Firebird não é carregado aqui.** Perguntar a versão ao motor significa carregar o
  `fbclient.dll`, que é caro e é justamente o que falha quando algo está errado — é o
  trabalho do `manage.py conferir_firebird`. Então a versão vem de quem instalou o motor:
  desde a 1.21.0 o instalador grava `STUDIO_FIREBIRD_VERSAO` no `studio.env`. A
  arquitetura, essa sim, é lida do arquivo, porque motor de 32 bits debaixo de um Python
  de 64 já travou a importação uma vez e vale ficar à vista.

## O que é escrito à mão, de propósito

As **decisões** (`DECISOES` no mesmo arquivo): por que tudo mora dentro de uma pasta só,
por que o Firebird aqui só lê a cópia, por que nenhuma tela depende da internet, por que
cada importação é uma foto que não se soma, por que o sistema se limpa de madrugada e por
que a busca do tempo é tarefa de servidor e nunca tela. Essas não se leem de lugar nenhum,
não envelhecem sozinhas, e sem elas a tabela de versões é uma lista de nomes. As decisões
de projeto em formato de tabela continuam em `docs/arquitetura.md`; aqui ficam as que
explicam o formato do sistema para quem não participou dele — a lista é a do código, e não
um número escrito aqui, que envelheceria na primeira decisão nova.

## Quem vê

A mesma permissão do quadro (`processos.view_processo`): gerência e administrativo. O
perfil de vendedor tem uma tela só, e não é esta — há teste.
