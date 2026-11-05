# Certificado SSL (1.18.0)

Código em `apps/core/certificado.py`, tela em `/sistema/certificado/`.

## O problema que isto resolve

O HTTPS entrou na 1.15.0 porque o navegador do celular só libera a câmera em contexto
seguro. O certificado era assinado por ele mesmo, e aí não existe nada em que o aparelho
possa confiar: o aviso do navegador voltava em cada aparelho novo e **a cada renovação**,
para sempre. Em 07/10/2026 o Edson pediu para resolver a questão.

## Como ficou

Dois certificados, em `var/certificado`:

- **`cabana-autoridade.crt`** — a autoridade da loja. Vale 10 anos, é instalada à mão uma
  vez em cada aparelho e é o único arquivo que a tela entrega. A chave
  (`cabana-autoridade.key`) nunca sai do servidor.
- **`cabana.crt`** — o certificado do servidor, assinado pela autoridade. Vale 395 dias e
  se renova sozinho quando faltam 30. Aparelho que já confia na autoridade aceita o
  certificado renovado sem perguntar nada.

## Os prazos não são escolha de gosto

- Acima de **398 dias** os navegadores recusam certificado de servidor.
- Acima de **825 dias** o iOS recusa, mesmo com a autoridade instalada e confiada.
- A autoridade pode valer muito mais, porque quem a instala é uma pessoa, uma vez. Dez
  anos é para não obrigar a reinstalar em todos os aparelhos enquanto o sistema viver.

Há teste travando esses dois limites.

## Extensões que o iPhone exige

Sem `ExtendedKeyUsage([SERVER_AUTH])` o iOS recusa o certificado mesmo com a autoridade
confiada. A autoridade precisa de `BasicConstraints(ca=True)` e `KeyUsage(key_cert_sign)`.
`SubjectKeyIdentifier` e `AuthorityKeyIdentifier` são o que liga um ao outro para o
Android.

## Quando o certificado é refeito

`garantir()` refaz o do servidor quando qualquer uma destas é verdade:

- não existe, ou está ilegível;
- falta menos de 30 dias para vencer;
- **não foi assinado pela autoridade atual** — é o caso de quem atualiza da 1.17.0, cujo
  certificado era assinado por ele mesmo;
- **os endereços do `STUDIO_CERTIFICADO_NOMES` mudaram**. Sem esta checagem, acrescentar
  um endereço no `studio.env` não teria efeito nenhum e o navegador recusaria o endereço
  novo, com o certificado antigo valendo mais um ano.

## A instalação no aparelho

A tela tem o passo a passo dos três sistemas. O que mais dá problema:

- **iPhone**: instalar o perfil **não basta**. É preciso ir em Ajustes › Geral › Sobre ›
  Configurações de Confiança de Certificado e ligar a chave. Sem isso o iPhone instala e
  continua não confiando, sem dizer por quê.
- **Android**: Configurações › Segurança › Criptografia e credenciais › Instalar um
  certificado › **Certificado CA**. O aparelho avisa que é para uso avançado.
- **Windows**: o repositório tem que ser **Autoridades de Certificação Raiz Confiáveis**;
  qualquer outro não vale.

O arquivo é entregue com `Content-Type: application/x-x509-ca-cert`, que é o que faz o
iPhone e o Android entenderem que aquilo é um certificado para instalar.

## Quem pode abrir a tela

Só login, sem permissão: quem instala é a pessoa, no aparelho dela, e a tela não mostra
nenhum número da loja. No **menu** ela só aparece para quem tem `importacao.ver_painel`,
senão entraria na fileira do vendedor, que tem uma tela só — e `primeira_tela` passaria a
mandar o vendedor para cá. Há teste travando as duas coisas.

## A alternativa sem instalação nenhuma

Um domínio de verdade apontando para a loja e um certificado do Let's Encrypt por
validação de DNS. Funciona em qualquer celular que entre na loja, sem passo nenhum, mas
precisa de domínio, de configuração de DNS e de renovação a cada três meses. Enquanto o
sistema é usado só pela equipe, instalar a autoridade uma vez por aparelho resolve e não
depende de nada de fora.

## Por que o Edson disse "SSL ainda não funcionou" (08/10/2026)

A tela dele estava em `http://192.168.3.254:8095/sistema/painel/dashboard/`, marcada
como "Não seguro". E estava certa: o HTTPS nunca esteve nessa porta. Ele mora em
`https://192.168.3.254:8443/sistema/`. Duas coisas estavam silenciosas:

1. **Nada dizia que existia outro endereço.** Quem abre o sistema pelo atalho antigo
   fica no HTTP para sempre e conclui que o certificado não entrou.
2. **Se o túnel não subisse, o sistema não contaria.** `tunel_tls` é de propósito
   tolerante a falha — a loja não pode parar porque o HTTPS não subiu —, mas o erro só
   ia para `logs\sistema.log`, que ninguém abre.

A partir da 1.19.0:

- Quem entra por um endereço de rede em HTTP vê uma faixa com o endereço seguro
  equivalente, clicável, levando para a mesma página. `localhost` não mostra a faixa: o
  navegador já trata localhost como contexto seguro.
- A tela do Certificado faz o teste de verdade, do próprio servidor:
  `apps/core/https.py:conferir()` abre uma conexão TLS em `127.0.0.1:8443` (sem conferir
  o certificado — o que se quer saber é se **alguém fala TLS ali**) e devolve um dos
  quatro resultados, cada um com o que fazer:

  | Resultado | O que aconteceu | O que fazer |
  |---|---|---|
  | **bom** | a porta respondeu em TLS | se o aparelho ainda reclama, falta instalar a autoridade nele |
  | **ruim**, ninguém atende | o sistema subiu sem a porta segura | reiniciar a tarefa `\Studio\StudioSistema`; o motivo está no fim de `logs\sistema.log` |
  | **ruim**, não fecha o TLS | certificado ou chave corrompidos | apagar a pasta do certificado e reiniciar |
  | **atenção**, não respondeu a tempo | servidor ocupado | atualizar a tela em alguns segundos |

- `STUDIO_HTTPS=0` no `studio.env` desliga tudo; nesse caso a faixa não aparece (não
  adianta oferecer um endereço que não existe) e o diagnóstico diz qual linha mudar.

## A causa de verdade, achada em 08/10/2026

O HTTPS nunca subiu neste servidor, desde a 1.15.0, e o motivo era permissão de pasta.

O instalador configurava `STUDIO_CERTIFICADO_PASTA = C:\studio-sistema\config\certificado`
e, três blocos depois, dava à conta do serviço apenas **leitura** em `config`:

```powershell
icacls $Config /inheritance:r /grant:r ... "${SidNetworkService}:(OI)(CI)R"
```

Então `certificado.garantir()` levantava `PermissionError` ao gravar a chave. Quem chama é
o `servir.py`, dentro de um `try` que engole a falha de propósito (a loja não pode parar
porque o HTTPS não subiu), e o erro ia só para `logs\sistema.log`. Resultado: porta 8443
muda, `/sistema/certificado/autoridade.crt` devolvendo 404, e nada dizendo por quê.

O que mudou na 1.19.1:

- o certificado mora em `C:\studio-sistema\dados\certificado` (a conta do serviço tem
  **M** em `dados`), e o instalador troca sozinho a configuração de quem aponta para a
  pasta antiga;
- `pasta_padrao()` testa se dá para gravar e cai para uma pasta que aceite, na ordem
  configurada → `dados\certificado` → `app\var\certificado`. Pasta que **já tem** o
  certificado ganha, mesmo sem escrita: ler basta;
- a tela do Certificado e o download chamam `garantir()` na hora, então uma instalação
  onde o `servir.py` falhou se conserta ao abrir a tela;
- falhando, aparece o erro na tela (`PermissionError: ...`) em vez de 404;
- `manage.py conferir_certificado` roda na atualização e escreve o resultado junto do
  `conferir_banco`, que é onde se olha quando algo dá errado.

Lição geral: configuração que manda o programa **gravar** em algum lugar tem que vir
acompanhada da permissão de gravar nesse lugar — e quem engole exceção para não derrubar
o sistema precisa deixar o motivo em algum lugar que alguém abra.


## O motivo da falha não some mais (1.20.0)

O túnel TLS sobe numa linha de trabalho separada do processo que inicia o sistema
(`tunel_tls.em_segundo_plano`). Quem inicia já seguiu em frente quando o erro acontece, e
o `except` do `servir.py` nunca vê nada: até a 1.19.1 a falha ia só para
`logs\\sistema.log`. Era por isso que "o SSL não funcionou" não tinha explicação em lugar
nenhum da tela.

Agora, quando a porta segura não sobe, o motivo é gravado em
`dados\\certificado\\https-ultima-falha.txt` (data e erro), e a tela do Certificado mostra
num cartão vermelho: *"O que o servidor registrou na última tentativa"*. Quando a porta
sobe, o arquivo é apagado, então a mensagem some sozinha.

O autodiagnóstico também passou a testar **dois** endereços: o `127.0.0.1`, que diz se o
túnel subiu, e o endereço de rede pelo qual a pessoa chegou na tela (por exemplo
`192.168.3.254`), que diz se ele está escutando na placa de rede. Atender nos dois não
garante que o firewall do Windows deixe outro aparelho entrar — o servidor falando com ele
mesmo não passa pela regra —, e por isso a mensagem de sucesso diz, em uma linha, o que
sobra conferir: a regra *Studio Sistema HTTPS* na porta 8443 e o certificado instalado no
aparelho.
