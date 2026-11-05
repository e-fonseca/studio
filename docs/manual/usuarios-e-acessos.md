# Manual: usuários e acessos

**Para que serve**: dar e tirar acesso ao Aux SET, decidir o que cada cargo pode ver e
fazer, e saber quem fez o quê. Desde a versão 1.44.0.

**Quem pode usar**

| Perfil | Pode |
|---|---|
| Administrador gerência | Tudo: pessoas, perfis e o que cada perfil pode |
| Administrador de acessos | Criar conta, definir senha, bloquear e encerrar sessão de quem tem menos acesso que ele. Não vê número da loja e não muda perfil |
| Os outros perfis | Nada nesta área. Cada um troca a própria senha clicando no próprio nome, no alto da tela |

**Três regras que o sistema não deixa quebrar**

1. Ninguém mexe no próprio acesso. Para mudar o seu perfil, peça a outra pessoa da gerência.
2. Ninguém dá o que não tem. Acesso a dinheiro (💰) ou à administração (🔑) só é dado por
   quem também tem.
3. Sempre fica alguém administrando. O sistema não deixa bloquear, encerrar ou tirar o
   perfil da última pessoa que administra. Bom ter sempre duas.

## Entrar na área

1. No menu de cima, **Sistema > Usuários**.
2. O sistema pede **a sua senha de novo**. Digite e clique em **Confirmar**. A área fica
   aberta enquanto você estiver usando e fecha sozinha com 15 minutos parada.
3. Cinco senhas erradas seguidas encerram a sessão: entre de novo.

## Pessoa nova (admissão)

1. Em **Usuários**, desça até **Dar acesso a mais alguém**.
2. Preencha **Nome**, **Usuário de acesso** (o que a pessoa digita para entrar, sem espaço,
   por exemplo `cassia`) e o **E-mail** dela, que serve para ela mesma recuperar a senha.
3. Marque o **perfil** do cargo. Pode marcar mais de um; a pessoa pode a soma deles.
4. Se o acesso tem data para acabar (temporário, substituição, estágio), preencha
   **Acesso até**. No dia seguinte a conta se desliga sozinha.
5. Clique em **Criar acesso**. Abre a ficha da pessoa, com a situação **Pendente de ativação**.
6. Na ficha, em **Senha e e-mail**, digite uma senha provisória (12 letras ou mais) e
   clique em **Definir a senha**. A situação passa a **Ativo**.
7. Entregue a senha à pessoa, pessoalmente, e peça para ela trocar na primeira entrada
   clicando no próprio nome, no alto da tela.

**Resultado esperado**: a pessoa entra e vê só as telas do perfil dela.

## Mudança de cargo

1. Em **Usuários**, clique no nome da pessoa.
2. Em **Perfis**, marque o perfil novo e desmarque o antigo.
3. Clique em **Salvar os perfis**. Vale no próximo clique dela, sem precisar sair e entrar.
4. Confira em **O que pode fazer** (clique em "Ver cada uma") o que ela passou a poder.

## Férias, afastamento ou suspeita (bloqueio)

1. Na ficha da pessoa, em **Situação do acesso**, escreva o motivo em **Bloquear por um
   tempo** e clique em **Bloquear**.
2. As sessões abertas dela caem na hora, no computador e no celular.
3. Na volta, clique em **Desbloquear**. Ela volta com os mesmos perfis.

## Saiu da empresa (desligamento)

1. Na ficha da pessoa, em **Encerrar o acesso**, escreva o motivo e clique em
   **Encerrar o acesso**.
2. As sessões abertas caem na hora. A conta não se apaga: o nome dela continua nos pedidos,
   contagens e na auditoria.
3. Se já se sabe o último dia, use **Último dia de acesso** em vez de encerrar na hora.
4. Se ela voltar, **Liberar de novo**.

## Celular perdido ou computador que ficou aberto

1. Na ficha da pessoa, em **Sessões abertas**, cada linha diz de que aparelho e de onde
   (rede da loja, VPN ou endereço seguro) e quando foi o último uso.
2. Clique em **Encerrar esta** na sessão do aparelho, ou em **Encerrar todas**.
3. Se a senha pode ter sido vista, defina uma senha nova em **Senha e e-mail**: as outras
   sessões caem junto.

Na sua própria ficha o botão se chama **Sair dos outros aparelhos**: a sessão em que você
está fica.

## Mudar o que um cargo pode (perfis)

1. Em **Usuários**, clique em **Perfis e permissões**, no alto.
2. A tabela mostra cada permissão numa linha e cada perfil numa coluna. O ✓ diz que o
   perfil pode.
3. Clique no nome do perfil. Marque ou desmarque o que ele pode, escreva **Por que mudou**
   e clique em **Salvar o perfil**. Vale para todos que estão nele, no próximo clique.
4. Caixa travada é acesso que você não tem, ou é o perfil em que você mesmo está: quem muda
   é outra pessoa da gerência.

Para um cargo que não cabe em nenhum perfil, use **Criar um perfil**, começando por uma
cópia do mais parecido. Perfil sem ninguém pode ser **retirado**; o histórico fica e dá para
trazer de volta.

## O que conferir de vez em quando

Em **Perfis e permissões**, o quadro **O que pede atenção** mostra quem administra (bom ter
duas pessoas), quantos veem algum número de dinheiro, quem está sem perfil, quem tem
permissão fora de perfil e as contas técnicas do servidor.

## Se ninguém mais consegue administrar

Acontece se a única pessoa que administra esquecer a senha e não tiver e-mail cadastrado,
ou for bloqueada por engano. Quem cuida do servidor abre o PowerShell como administrador e
roda:

```
cd C:\studio-sistema\app
..\python\python.exe manage.py recuperar_administrador edson --motivo "esqueceu a senha" --senha
```

Troque `edson` pelo usuário de quem vai voltar a administrar. O comando pede a senha nova
duas vezes, devolve o perfil Administrador gerência e libera a conta. Fica na auditoria,
com o motivo.

## Erros comuns

| Mensagem | O que fazer |
|---|---|
| "Ninguém muda o próprio acesso." | Peça a outra pessoa da gerência. |
| "... tem acesso que você não tem ..." | Só quem tem esse acesso mexe na conta dessa pessoa. |
| "Você não pode dar nem tirar o perfil ..." | O perfil tem acesso a dinheiro ou à administração que você não tem. |
| "Assim ninguém mais administraria os acessos ..." | Dê o perfil Administrador gerência a outra pessoa antes. |
| "Por segurança, confirme a sua senha e faça a mudança de novo." | A área ficou 15 minutos parada. Confirme a senha e refaça. |
| "Seu usuário não tem permissão para esta ação. Procure a gerência." | A tela é de outro perfil. Se a pessoa precisa dela, mude o perfil. |
| "Diga em poucas palavras por que o perfil mudou." | Escreva o motivo antes de salvar o perfil. |

**Tudo fica registrado**: quem deu ou tirou acesso, quem bloqueou, quem baixou planilha ou
PDF e quem tentou abrir o que não podia. O **Histórico do acesso**, no fim da ficha de cada
pessoa, mostra o dela.
