# Exemplo: uma tela de números, de ponta a ponta

Modelo da estrutura de `apps/painel/vendas_do_dia.py` + `templates/painel/vendas_do_dia.html`.
Copiar a forma, não o conteúdo.

## O cálculo

```python
ZERO = Decimal("0")
CEM = Decimal("100")


def _porcento(parte, total):
    if not total:
        return None            # None, e não zero: "não dá para calcular" não é "0%"
    return (_decimal(parte) * CEM / _decimal(total)).quantize(Decimal("0.1"))


@dataclass
class Linha:
    codigo: str
    descricao: str
    valor: Decimal = ZERO
    custo: Decimal = ZERO

    @property
    def lucro(self):
        return self.valor - self.custo

    @property
    def prejuizo(self):
        return self.lucro < ZERO


@dataclass
class Resultado:
    linhas: list = field(default_factory=list)
    faturamento: Decimal = ZERO

    @property
    def tem_dados(self):
        return bool(self.linhas)


def calcular(importacao, dia=None, limite=500):
    resultado = Resultado()
    if importacao is None:
        return resultado       # a tela abre e explica, não quebra
    ...
    return resultado
```

Propriedade no `@dataclass` em vez de campo calculado: o template lê `linha.lucro` sem
conta nenhuma dentro do HTML, e o teste lê a mesma coisa.

## A view

```python
@login_required
@permission_required("importacao.ver_painel", raise_exception=True)
def vendas_dia(request):
    estado = servicos.estado_dos_dados()
    return render(request, "painel/vendas_do_dia.html", {
        "titulo": "Vendas do dia",
        "estado": estado,
        "esconder_aviso_dados": True,   # a tela já mostra o estado em destaque
        "v": vendas_servicos.calcular(estado.importacao, dia=_dia_da_url(request.GET.get("dia"))),
    })
```

Entrada torta na URL vira `None` em `_dia_da_url`, nunca exceção.

## A tela

```django
{% extends "base.html" %}
{% load cabana %}
{% block conteudo %}
<div class="cabecalho-pagina">
  <h1>Vendas do dia</h1>
  <p>Tudo o que saiu da loja no dia, com o custo daquele dia, o lucro e a margem.</p>
</div>

{% if not v.tem_dados %}
<section class="cartao cartao-atencao">
  <h2>Ainda não há venda importada</h2>
  <p>Assim que uma importação concluir com vendas, os dias aparecem aqui.</p>
</section>
{% else %}
<div class="cartoes-numero">
  <div class="cartao-numero {% if v.lucro > 0 %}nivel-bom{% else %}nivel-ruim{% endif %}">
    <span class="cartao-titulo">Sobrou no dia</span>
    <strong class="cartao-valor">{{ v.lucro|reais }}</strong>
    <span class="cartao-rodape">Venda menos custo. Ainda não desconta despesa da loja.</span>
  </div>
</div>
{% endif %}
{% endblock %}

{% block ajuda %}
<script type="application/json" id="passos-ajuda">
[{"titulo": "Vendas do dia", "texto": "..."},
 {"seletor": ".filtros", "titulo": "Escolher o dia", "texto": "..."}]
</script>
{% endblock %}
```

Filtros em `reais`, `quantidade` e `contagem` (de `apps/core/templatetags/cabana.py`), e
nunca `{{ valor }}` cru: dinheiro é `R$ 1.234,56` e quantidade é `12`, não `12,000`.

Comparação com `None` dentro de `{% if %}` devolve falso em vez de estourar, mas valor que
pode ser `None` sempre ganha `{% if x is None %}—{% else %}`, senão a tela escreve "—%".
