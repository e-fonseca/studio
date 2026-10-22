"""Cadastro de clientes: quem a loja tem cadastrado e quem de fato compra."""

from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Sum
from django.shortcuts import render

from apps.importacao import servicos as importacao_servicos

from .models import ClienteImportado


@login_required
@permission_required("clientes.ver_clientes", raise_exception=True)
def lista(request):
    estado = importacao_servicos.estado_dos_dados()
    todos = ClienteImportado.objects.filter(importacao=estado.importacao) if estado.importacao else ClienteImportado.objects.none()
    cadastrados = todos.filter(generico=False)
    genericos = todos.filter(generico=True)
    compraram = cadastrados.filter(compras__gt=0)
    return render(request, "clientes/lista.html", {
        "titulo": "Clientes",
        "estado": estado,
        # Só quem realmente comprou. A maior parte do cadastro nunca teve venda lançada no
        # nome, e uma lista de duzentos nomes com R$ 0,00 não ajuda ninguém a decidir nada.
        "clientes": list(compraram.order_by("-valor_comprado_12m", "-valor_comprado", "nome")[:200]),
        "total": cadastrados.count(),
        "compraram": compraram.count(),
        "sem_compra": cadastrados.count() - compraram.count(),
        "com_compra_12m": cadastrados.filter(valor_comprado_12m__gt=0).count(),
        "pessoas_juridicas": cadastrados.filter(pessoa_juridica=True).count(),
        # O balcão lança em CONSUMIDOR FINAL quem não se identifica: é a maior parte da
        # venda da loja e precisa aparecer separado, senão o cadastro parece vazio sem motivo.
        "balcao_valor": genericos.aggregate(v=Sum("valor_comprado_12m"))["v"] or 0,
        "balcao_vendas": genericos.aggregate(v=Sum("compras"))["v"] or 0,
    })
