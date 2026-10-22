"""Lembretes do dia: o que precisa de atenção hoje, em uma lista curta.

Aparece num aviso quando a pessoa entra no sistema, uma vez por dia. Tudo aqui
sai de número que o sistema já calculou; nada é escrito à mão. Se o painel ainda
não foi calculado nesta sessão, os lembretes que dependem dele ficam de fora, em
vez de fazer a conta dos milhares de produtos em qualquer tela.
"""

from dataclasses import dataclass

from django.urls import reverse

from apps.core.templatetags.cabana import reais
from apps.financeiro import servicos as financeiro
from apps.fornecedores import servicos as fornecedores
from apps.importacao import servicos as importacao
from apps.painel import servicos as painel


@dataclass(frozen=True)
class Lembrete:
    titulo: str
    detalhe: str
    endereco: str = ""
    nivel: str = "informacao"  # informacao, atencao ou urgente


def do_dia(usuario):
    """Lista de lembretes para o usuário informado, do mais urgente para o menos."""
    lembretes = []
    if not usuario.has_perm("importacao.ver_painel"):
        return lembretes

    estado = importacao.estado_dos_dados()
    if estado.nivel in ("vencido", "sem_dados", "atencao"):
        lembretes.append(Lembrete(
            titulo=estado.titulo,
            detalhe=estado.detalhe,
            endereco=reverse("importacao:historico"),
            nivel="urgente" if estado.nivel in ("vencido", "sem_dados") else "atencao",
        ))

    dados = painel.painel_pronto(estado.importacao)
    if dados is not None:
        falta = dados.indicador("falta")
        if falta and falta.itens:
            lembretes.append(Lembrete(
                titulo=f"{falta.itens} produto{'s' if falta.itens != 1 else ''} vendendo e sem estoque",
                detalhe="Venderam nos últimos 90 dias e estão zerados no SET.",
                endereco=reverse("painel:completo") + "?lista=falta",
                nivel="atencao",
            ))
        comprar = dados.indicador("comprar")
        if comprar and comprar.itens:
            lembretes.append(Lembrete(
                titulo=f"Reposição sugerida para {comprar.itens} produto{'s' if comprar.itens != 1 else ''}",
                detalhe="Chegaram ao ponto de reposição considerando o prazo de cada fornecedor.",
                endereco=reverse("painel:completo") + "?lista=comprar",
            ))

    if usuario.has_perm("fornecedores.change_fornecedor") and estado.importacao is not None:
        sem_prazo = sum(1 for r in fornecedores.resumir(estado.importacao) if r.precisa_de_prazo)
        if sem_prazo:
            lembretes.append(Lembrete(
                titulo=f"{sem_prazo} fornecedor{'es' if sem_prazo != 1 else ''} sem prazo de entrega",
                detalhe="Sem o prazo, o sistema sugere comprar mais tarde do que deveria.",
                endereco=reverse("fornecedores:lista"),
            ))

    if usuario.has_perm("financeiro.ver_financeiro") and estado.importacao is not None:
        resumo = financeiro.resumir(estado.importacao)
        if resumo.vencidas.quantidade:
            lembretes.append(Lembrete(
                titulo=f"{resumo.vencidas.quantidade} conta"
                       f"{'s' if resumo.vencidas.quantidade != 1 else ''} vencida"
                       f"{'s' if resumo.vencidas.quantidade != 1 else ''} no SET",
                detalhe=f"Somam {reais(resumo.vencidas.valor)}. Pode ser pagamento feito e ainda "
                        "não baixado no SET.",
                endereco=reverse("financeiro:contas_a_pagar"),
                nivel="urgente",
            ))

    ordem = {"urgente": 0, "atencao": 1, "informacao": 2}
    lembretes.sort(key=lambda lembrete: ordem[lembrete.nivel])
    return lembretes
