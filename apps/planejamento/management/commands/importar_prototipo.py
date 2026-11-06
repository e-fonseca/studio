"""Traz para o sistema o que estava no protótipo da Henriett.

    python manage.py importar_prototipo C:\\caminho\\dados_sistema_financeiro_studio_2026-11-05.json

O arquivo é a exportação do painel "Financeiro Studio Industrial" que rodava no Claude
do perfil da Henriett (trazido pelo Edson em 06/11/2026). Ele tem três partes:

- `pedidos`: um por card do Trello, com venda, custo, oficina, regra e datas;
- `config.geral`: cartões, custos fixos, dívidas, avulsos e as regras gerais;
- `interco`: os movimentos entre Studio e Cabana.

O comando pode rodar de novo sem duplicar nada: o pedido é achado pelo número do card,
a oficina e o cartão pelo nome, o custo fixo, a dívida e o avulso pelo nome. O que já
existe é atualizado com o que veio no arquivo.

Ele **não** apaga nada que exista aqui e não esteja no arquivo. E o arquivo não vai para o
repositório: tem nome e telefone de cliente, e por isso fica onde o Edson o guardou.
"""

import json
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.auditoria.servicos import registrar
from apps.projetos.models import Oficina, Projeto

from ...models import Avulso, Cartao, CustoFixo, Divida, MovimentoEntreEmpresas, Parametros

ETAPAS = {
    "projeto": Projeto.Etapa.APROVADO,
    "producao": Projeto.Etapa.PRODUCAO,
    "entregue": Projeto.Etapa.ENTREGUE,
    "manutencao": Projeto.Etapa.MANUTENCAO,
    "cancelado": Projeto.Etapa.CANCELADO,
}
SALDO = {"Pix": Projeto.SaldoForma.PIX, "Cartão": Projeto.SaldoForma.CARTAO,
         "Quitado": Projeto.SaldoForma.QUITADO, "": Projeto.SaldoForma.A_CONFIRMAR}
REGIMES = {"Padrão": Projeto.Regime.PADRAO, "Cartão": Projeto.Regime.CARTAO,
           "Rogério": Projeto.Regime.MENSAL, "Breno": Projeto.Regime.MENSAL}
# Nome no protótipo -> chave da regra em config.geral. Quem recebe em 3x com corte.
MENSAIS = {"Rogério": "rogerio", "Breno": "breno"}
SEM_OFICINA = {"", "?"}
CEM = Decimal("100")


def _dinheiro(valor):
    if valor in (None, ""):
        return None
    try:
        return Decimal(str(valor)).quantize(Decimal("0.01"))
    except InvalidOperation as erro:
        raise CommandError(f"Valor que não é número: {valor!r}") from erro


def _data(valor):
    return date.fromisoformat(valor[:10]) if valor else None


def _pct(fracao):
    """0.25 no protótipo vira 25 aqui."""
    return None if fracao in (None, "") else (Decimal(str(fracao)) * CEM).quantize(Decimal("0.001"))


class Command(BaseCommand):
    help = "Importa pedidos, ajustes e movimentos do protótipo financeiro da Henriett (arquivo .json)."

    def add_arguments(self, parser):
        parser.add_argument("arquivo")
        parser.add_argument("--simular", action="store_true",
                            help="Lê e conta tudo, mas não grava nada.")

    def handle(self, arquivo, simular=False, **opcoes):
        try:
            with open(arquivo, encoding="utf-8") as f:
                dados = json.load(f)
        except (OSError, ValueError) as erro:
            raise CommandError(f"Não consegui ler {arquivo}: {erro}") from erro
        if not isinstance(dados, dict) or "pedidos" not in dados:
            raise CommandError("O arquivo não parece a exportação do protótipo: falta 'pedidos'.")

        self.avisos = []
        with transaction.atomic():
            contas = self._ajustes((dados.get("config") or {}).get("geral") or {})
            contas.update(self._pedidos(dados["pedidos"]))
            contas["movimentos"] = self._interco(dados.get("interco") or {})
            registrar("planejamento.importou_prototipo", depois={"arquivo": str(arquivo), **contas})
            if simular:
                transaction.set_rollback(True)

        self.stdout.write(("Simulação, nada gravado. " if simular else "") + ", ".join(
            f"{chave}: {valor}" for chave, valor in contas.items()))
        for aviso in self.avisos:
            self.stdout.write(self.style.WARNING(aviso))

    # -------------------------------------------------------------------------------
    def _ajustes(self, geral):
        self.regras_mensais = {nome: geral.get(chave) or {} for nome, chave in MENSAIS.items()}
        cartoes = {}
        for c in geral.get("cartoes") or []:
            cartao, _ = Cartao.objects.update_or_create(
                nome=c["nome"], defaults={"vencimento": int(c["venc"]), "fecha_dias_antes": int(c["fecha"])})
            cartoes[cartao.nome] = cartao
        self.cartoes = {c.nome: c for c in Cartao.objects.all()}

        p = Parametros.atual()
        for campo, chave in (("margem_minima", "margemMin"), ("taxa_antecipacao", "taxaAntecip"),
                             ("pct_cartao", "pctCartao"), ("pct_primeira", "pct1")):
            if geral.get(chave) is not None:
                setattr(p, campo, _pct(geral[chave]).quantize(Decimal("0.01")))
        if geral.get("atrasoDias") is not None:
            p.atraso_dias = int(geral["atrasoDias"])
        if geral.get("parcelasPadrao") is not None:
            p.parcelas_padrao = int(geral["parcelasPadrao"])
        if geral.get("saldoInicial") is not None:
            p.saldo_inicial = _dinheiro(geral["saldoInicial"])
            self.avisos.append("O saldo em conta veio do protótipo e não diz de que dia é: "
                               "confira e ponha a data nos Ajustes.")
        if geral.get("cartaoPadrao") in self.cartoes:
            p.cartao_padrao = self.cartoes[geral["cartaoPadrao"]]
        p.save()

        fixos = 0
        for f in geral.get("fixos") or []:
            nome = f["nome"]
            tipo = (CustoFixo.Tipo.EMPRESTIMO if any(x in nome.lower() for x in ("capital de giro", "pronampe", "empréstimo"))
                    else CustoFixo.Tipo.FIXO)
            CustoFixo.objects.update_or_create(nome=nome, defaults={
                "valor": _dinheiro(f.get("valor")) or 0, "dia": int(f.get("dia") or 10), "tipo": tipo, "ativo": True})
            fixos += 1
        dividas = 0
        for d in geral.get("dividas") or []:
            Divida.objects.update_or_create(nome=d["nome"], defaults={
                "saldo": _dinheiro(d.get("saldo")) or 0, "taxa_mensal": _pct(d.get("taxa")) or 0,
                "dia": int(d.get("dia") or 1), "ativa": True})
            dividas += 1
        avulsos = 0
        for a in geral.get("avulsos") or []:
            Avulso.objects.update_or_create(nome=a["nome"], defaults={
                "valor": _dinheiro(a.get("valor")) or 0, "data": _data(a["data"]), "pago": bool(a.get("pago"))})
            avulsos += 1
        return {"cartões": len(cartoes), "custos fixos": fixos, "dívidas": dividas, "avulsos": avulsos}

    def _oficina(self, nome):
        nome = (nome or "").strip()
        if nome in SEM_OFICINA:
            return None
        oficina = Oficina.objects.filter(nome__iexact=nome).first()
        if oficina is None:
            oficina = Oficina(nome=nome)
        if nome in MENSAIS:
            regra = self.regras_mensais.get(nome) or {}
            oficina.pagamento = Oficina.Pagamento.MENSAL
            oficina.parcelas_mensais = 3
            oficina.dia_pagamento = int(regra.get("dia") or oficina.dia_pagamento or 30)
            oficina.dia_corte = int(regra.get("corte") or oficina.dia_corte or oficina.dia_pagamento)
        oficina.save()
        return oficina

    def _pedidos(self, pedidos):
        criados = atualizados = 0
        for chave, p in pedidos.items():
            numero = str(p.get("p") or chave).strip()[:40]
            regime = REGIMES.get(p.get("regime") or "Padrão")
            if regime is None:
                self.avisos.append(f"{numero}: regra {p.get('regime')!r} desconhecida, ficou a padrão.")
                regime = Projeto.Regime.PADRAO
            if p.get("oficina") in SEM_OFICINA:
                self.avisos.append(f"{numero}: sem oficina no protótipo ({p.get('oficina')!r}).")
            cartao = None
            if p.get("pg1Cartao"):
                cartao = self.cartoes.get(p["pg1Cartao"])
                if cartao is None:
                    self.avisos.append(f"{numero}: cartão {p['pg1Cartao']!r} não está nos cartões; ficou o padrão.")
            pct1 = _pct(p.get("pct1"))
            valores = {
                "cliente_nome": (p.get("cliente") or "Cliente não informado")[:160],
                "vendedor": (p.get("vendedor") or "")[:80],
                "arquiteto": (p.get("arquiteto") or "")[:120],
                "data_venda": _data(p.get("dataVenda")),
                "etapa": ETAPAS.get(p.get("status"), Projeto.Etapa.PRODUCAO),
                "valor_venda": _dinheiro(p.get("venda")) or 0,
                "recebido": _dinheiro(p.get("recebido")) or 0,
                "venda_cartao": _dinheiro(p.get("vendaCartao")),
                "saldo_forma": SALDO.get(p.get("saldoForma") or "", Projeto.SaldoForma.A_CONFIRMAR),
                "saldo_pix": _dinheiro(p.get("saldoPix")),
                "oficina": self._oficina(p.get("oficina")),
                "regime": regime,
                "custo_oficina": _dinheiro(p.get("custo")) or 0,
                "repasse": _data(p.get("repasse")),
                "primeira_percentual": pct1.quantize(Decimal("0.01")) if pct1 is not None else None,
                "incluir": p.get("incluir") is not False,
                "pg1_data": _data(p.get("pg1Data")),
                "pg1_cartao": cartao,
                "pg1_parcelas": int(p["pg1Parcelas"]) if p.get("pg1Parcelas") else None,
                "pg2_data": _data(p.get("pg2Data")),
                "prazo_entrega": _data(p.get("entregaPrevista")),
                "entregue_em": _data(p.get("entregaReal")),
                "frete": _dinheiro(p.get("frete")) or 0,
                "embalagem": _dinheiro(p.get("embalagem")) or 0,
                "rt": _dinheiro(p.get("rt")) or 0,
                "projeto_desenho": _dinheiro(p.get("projeto")) or 0,
                "observacao": p.get("obs") or "",
            }
            # Card que não é número (ex.: "Armário estoque (troca 28634)") vira o título.
            if not any(ch.isdigit() for ch in numero[:2]):
                valores["titulo"] = numero[:160]
            projeto = Projeto.objects.filter(numero=numero).first()
            if projeto is None:
                projeto = Projeto(numero=numero)
                criados += 1
            else:
                atualizados += 1
            for campo, valor in valores.items():
                setattr(projeto, campo, valor)
            projeto.save()
        return {"pedidos novos": criados, "pedidos atualizados": atualizados}

    def _interco(self, interco):
        lancados = 0
        incompletos = 0
        for chave, m in interco.items():
            if not isinstance(m, dict) or not m.get("valor") or not m.get("tipo"):
                incompletos += 1
                continue
            data = _data(m.get("data"))
            valor = _dinheiro(m["valor"])
            tipo = m["tipo"]
            descricao = (m.get("descricao") or "")[:200]
            existe = MovimentoEntreEmpresas.objects.filter(
                data=data, tipo=tipo, valor=valor, descricao=descricao, cancelado_em__isnull=True).exists()
            if existe:
                continue
            MovimentoEntreEmpresas.objects.create(
                data=data, tipo=tipo, valor=valor, descricao=descricao,
                sentido=m.get("sentido") if tipo != "prolabore" else "",
                empresa=(m.get("empresa") or "").lower() if tipo == "prolabore" else "")
            lancados += 1
        if incompletos:
            self.avisos.append(
                f"{incompletos} movimento(s) entre empresas vieram no arquivo só com a data, sem "
                "valor, tipo e quem deve: não entraram. Peça uma exportação nova ou lance na tela "
                "Entre empresas.")
        return lancados
