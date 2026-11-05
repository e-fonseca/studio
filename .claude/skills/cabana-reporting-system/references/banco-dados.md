# O banco: a foto por importação

## A regra da foto

Todo modelo vindo do SET tem `importacao = ForeignKey(Importacao)`. Cada importação cria
linhas novas; nada é atualizado no lugar. Toda consulta de tela filtra por `importacao=`,
normalmente a `servicos.ultima_concluida()`. `servicos.limpar_antigas(manter=10)` apaga as
fotos velhas, e o `on_delete=CASCADE` leva os filhos.

Isso está documentado em `docs/sincronizacao-nao-soma.md` e travado por
`apps/importacao/tests/test_comparacao.py`, que foi escrito porque o dono desconfiou que
o número crescia a cada sincronização.

Consulta sem `importacao=` é o defeito mais caro deste sistema: soma duas fotos.

## Modelos vindos do SET

| Modelo | Uma linha é | Chaves do SET |
|---|---|---|
| `ProdutoImportado` | um produto, com 12 meses somados | PRODUTOS |
| `CompraImportada` / `ItemCompraImportada` | uma compra e seus itens | COMPRAS / ICOMPRAS |
| `VendaImportada` | um cupom | VENDAS (`idvenda`) |
| `ItemVendaImportada` | um produto dentro do cupom | IVENDAS (`nvenda` + `empresa`) |
| `Lancamento` | conta a pagar/receber | CONTAS |
| `ClienteImportado` | cliente, só nome/cidade/estado | CLIENTES |
| `CaixaImportado` / `MovimentoCaixa` | turno de caixa e movimento | CAIXA / ICAIXA |

`VendaImportada` tem `UniqueConstraint(importacao, id_set)`: o id do SET não repete
dentro de uma foto. Mesmo assim o item é casado com o cabeçalho pela **ordem** da lista
(`zip(cabecalhos, vendas)`), porque `bulk_create` devolve na ordem recebida e venda velha
do SET pode vir sem id.

## O que o SET mente

- `EMPRESA = 1` é a loja física; o resto é cadastro de teste.
- `status <> 'Estornado'` em venda e em movimento de caixa: estorno não entra em soma.
- Código de produto do SET começa com zero, e o leitor de código de barras lê EAN-13
  começado em zero como UPC-A de 12 dígitos (ver `apps/core/barras.py`).
- `PRECOCUSTO` de item de venda vem vazio em ~5% dos itens.
- Texto vem em codificação antiga: passa por `apps/core/texto.py:consertar`.
- A ficha do fornecedor (prazo, estrelas, observação) é NOSSA, ligada pelo NOME: correção
  de nome vinda do SET precisa de migração que conserte o salvo.

## LGPD

`VENDAS` tem `NOMECLI`, `COMPRADOR` e `COMPRADOR_CPF`. Nada disso é lido. `ItemVendaImportada`
só tem produto, quantidade, valor e custo. Existe teste que falha se alguém acrescentar
campo de cliente em venda. O arquivo de backup com dados pessoais não é copiado para
fora do servidor.

## Firebird

Leitura por `firebird-driver` com a biblioteca cliente **4.0 x64** (`STUDIO_FIREBIRD_DLL`);
32 bits não abre. A cópia do backup é feita antes, e a conferência do arquivo (tamanho e
data) roda antes da leitura: `docs/conferencia-do-backup.md`.

## Gravação

`bulk_create(..., batch_size=1000)`, cabeçalho e depois os filhos. Em 12 meses são ~16 mil
cupons e ~32 mil itens de venda por foto, então gravar item por item fica inviável.
