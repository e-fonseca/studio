# Perfis e permissões

Três perfis, e só três (definidos pelo Edson em 07/10/2026, em
`apps/contas/perfis.py`):

| Perfil | Quem | O que abre |
|---|---|---|
| `Administrador gerência` | Edson, Henriett, Moizes | tudo, inclusive usuários, auditoria, importação e alertas |
| `Operador administrativo` | a definir | contas, fornecedores, painéis, caixa, inventário, sugestão |
| `Operador vendedor` | a definir | **uma** tela: `/sistema/importacao/consulta/` |

## A regra do vendedor

O vendedor não vê custo, margem nem valor nenhum. É condição do dono do sistema, e vale
para tela, para exportação e para API. Tela de dinheiro nova **não** ganha permissão de
vendedor; o teste que prova isso é um 403 em cada rota nova.

## Permissões que importam para relatório

- `importacao.ver_painel` — painéis, margem, compras, vendas do dia. Gerência e
  administrativo.
- `importacao.consultar_produtos` — a consulta de balcão. Os três perfis.
- `importacao.executar_importacao` — disparar importação. Só gerência.
- `alertas.configurar_email` — a tela de alertas, que guarda a senha da caixa e o token do
  robô, e decide o que sai do servidor para fora. Só gerência.
- `financeiro.ver_financeiro`, `caixa.ver_caixa`, `clientes.ver_clientes` — dinheiro e
  cliente, nunca vendedor.

## Como escrever

```python
@login_required
@permission_required("importacao.ver_painel", raise_exception=True)
def vendas_dia(request):
    ...
```

`raise_exception=True` dá 403 em vez de mandar para a tela de entrada, que é o certo para
quem já está logado e não tem direito.

**Esconder o menu não protege nada.** O que protege é o `permission_required` de cada
view. O menu (`apps/core/menu.py`) só evita mostrar o que a pessoa não pode abrir.

## Contas

Conta nova nasce com `set_unusable_password()`: ninguém entra até a gerência definir a
senha. Permissão nova só entra no perfil porque o instalador roda `configurar_perfis`
depois de migrar — no banco local é preciso rodar à mão, senão a tela nova dá 403.
