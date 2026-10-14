# Sistema auxiliar da Cabana do Jacarandá

Este repositório é o **backup do código** do sistema auxiliar que roda no servidor da
loja (orçamento de compra, estoque, financeiro, clientes, fornecedores, base de
processos e auditoria). Ele é privado e serve para o código existir em algum lugar
além daquele computador.

## Ainda não tem o código. O que falta

Falta **um passo, feito uma vez**, dentro do próprio sistema:

1. No sistema, abrir **Apoio > Backup**.
2. Clicar no link da tela, que vai direto para a página de gerar token do GitHub, e
   gerar um *fine-grained token* com acesso **só a este repositório** e permissão
   **Contents: Read and write**. Quanto mais longo o prazo, melhor — o sistema avisa
   sozinho dez dias antes de vencer.
3. Colar o token na tela e clicar em **Gravar**. Acabou.

Gravar o token já liga o envio automático e já manda a primeira cópia; não há passo
seguinte. A partir daí o código sobe sozinho no fim de cada atualização, e, se a
última cópia passar de uma semana, o sistema tenta de novo por conta própria.

O token é a única parte que não dá para automatizar: o GitHub exige que uma **pessoa**
dê a permissão, e é isso que impede um programa de escrever na conta de alguém sozinho.
Tudo o que vinha depois dela o sistema faz.

## O que vem para cá, e o que nunca vem

**Vem** o código do sistema: programa, telas e documentação. São cerca de 510
arquivos de texto.

**Nunca vem o banco de dados.** Nele estão os nomes dos clientes que vêm do SET, o
extrato bancário conferido e as notas fiscais anexadas aos pedidos. O GitHub é um
serviço fora da loja, e dado pessoal não sai do servidor. O backup dos **dados** é
outro, local: roda todo dia às 23:30 e guarda 14 dias em `C:\cabana-sistema\backups`.

**Nunca vem senha nenhuma.** O arquivo de configuração com a chave do sistema e a senha
do e-mail fica fora da pasta do programa.

A lista do que sobe é por **inclusão**: um arquivo que ninguém listou fica de fora.
Esquecer uma inclusão deixa de salvar um arquivo; esquecer uma exclusão vazaria um.
