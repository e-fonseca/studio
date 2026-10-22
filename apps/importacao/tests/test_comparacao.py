"""Sincronizar substitui, não soma.

O Edson desconfiou que o número crescia a cada sincronização (07/10/2026). Não
cresce: cada importação guarda a sua própria foto e as telas leem só a mais nova.
Estes testes travam esse comportamento — se alguém algum dia escrever um `update`
que acumule, ou uma consulta sem filtrar pela importação, eles quebram.
"""

import datetime as dt
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.clientes.models import ClienteImportado
from apps.contas.perfis import ADMINISTRACAO
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.financeiro.models import Lancamento
from apps.importacao import comparacao
from apps.importacao.models import (Importacao, ItemVendaImportada, ProdutoImportado,
                                    VendaImportada)
from apps.painel import ticket, vendas_do_dia

CORTE = date(2026, 9, 20)


# Data do arquivo de backup. Fixa de propósito: é ela, junto do nome e do tamanho, que
# diz que as duas importações leram o MESMO backup.
DO_BACKUP = dt.datetime(2026, 9, 20, 23, 40, tzinfo=dt.timezone.utc)


def _importar(quando, arquivo="Set-Cabana-FULL.zip", bytes_=1000, forcada=False):
    """Finge uma importação do mesmo backup: os mesmos dados, uma foto nova."""
    importacao = Importacao.objects.create(
        origem=Importacao.Origem.BANCO,
        situacao=Importacao.Situacao.CONCLUIDA,
        forcada=forcada,
        iniciada_em=quando,
        concluida_em=quando,
        data_corte=CORTE,
        dias_abertos_12m=300,
        produtos=2,
        arquivo=arquivo,
        arquivo_modificado_em=DO_BACKUP,
        arquivo_bytes=bytes_,
    )
    ProdutoImportado.objects.create(
        importacao=importacao, codigo="000123", descricao="TAPETE", grupo="TAPETE",
        fornecedor="GERMAN", custo=Decimal("100"), preco_venda=Decimal("180"),
        estoque=Decimal("4"), vendas_12m=Decimal("10"), receita_12m=Decimal("1800"),
    )
    ProdutoImportado.objects.create(
        importacao=importacao, codigo="000124", descricao="VASO", grupo="CERAMICA",
        custo=Decimal("20"), preco_venda=Decimal("50"), estoque=Decimal("6"),
        vendas_12m=Decimal("3"), receita_12m=Decimal("150"),
    )
    primeira = VendaImportada.objects.create(
        importacao=importacao, id_set=1, numero="1", data=date(2026, 9, 18), hora="10:00",
        dia_da_semana=5, valor=Decimal("300"), forma_pagamento="PIX",
    )
    segunda = VendaImportada.objects.create(
        importacao=importacao, id_set=2, numero="2", data=date(2026, 9, 19), hora="15:00",
        dia_da_semana=6, valor=Decimal("200"), forma_pagamento="PIX",
    )
    ItemVendaImportada.objects.create(
        venda=primeira, codigo="000123", descricao="TAPETE", grupo="TAPETE",
        quantidade=Decimal("1"), valor_total=Decimal("300"),
        custo_unitario=Decimal("100"), custo_total=Decimal("100"),
    )
    ItemVendaImportada.objects.create(
        venda=segunda, codigo="000124", descricao="VASO", grupo="CERAMICA",
        quantidade=Decimal("4"), valor_total=Decimal("200"),
        custo_unitario=Decimal("20"), custo_total=Decimal("80"),
    )
    Lancamento.objects.create(
        importacao=importacao, tipo=Lancamento.Tipo.PAGAR, vencimento=date(2026, 9, 1),
        valor=Decimal("1000"), descricao="ALUGUEL",
    )
    ClienteImportado.objects.create(importacao=importacao, codigo="0001", nome="MARIA")
    return importacao


class TestNaoSoma(TestCase):
    def setUp(self):
        agora = timezone.now()
        self.primeira = _importar(agora - timedelta(hours=2))
        self.segunda = _importar(agora - timedelta(hours=1))

    def test_a_segunda_importacao_do_mesmo_backup_da_os_mesmos_numeros(self):
        resultado = comparacao.montar()
        self.assertTrue(resultado.tem_com_que_comparar)
        self.assertEqual(resultado.mudaram, [])
        self.assertFalse(resultado.alguma_dobrou)

    def test_cada_importacao_guarda_a_sua_propria_foto(self):
        self.assertEqual(ProdutoImportado.objects.count(), 4)
        self.assertEqual(ProdutoImportado.objects.filter(importacao=self.primeira).count(), 2)
        self.assertEqual(ProdutoImportado.objects.filter(importacao=self.segunda).count(), 2)

    def test_o_ticket_medio_nao_dobra_com_a_segunda_importacao(self):
        """A conta que o Edson olha. Se alguma consulta esquecesse o filtro, dobrava aqui."""
        resultado = ticket.calcular(self.segunda)
        self.assertEqual(resultado.total.vendas, 2)
        self.assertEqual(resultado.total.faturamento, Decimal("500"))
        self.assertEqual(resultado.total.ticket, Decimal("250.00"))

    def test_a_relacao_do_dia_nao_dobra_com_a_segunda_importacao(self):
        """O item da venda é foto como todo o resto: ele tem que seguir a mesma regra."""
        dia = vendas_do_dia.calcular(self.segunda, dia=date(2026, 9, 19))
        self.assertEqual(dia.faturamento, Decimal("200.00"))
        self.assertEqual(dia.custo, Decimal("80.00"))
        self.assertEqual(dia.itens, 1)
        # A foto velha continua inteira, com os seus próprios itens.
        velha = vendas_do_dia.calcular(self.primeira, dia=date(2026, 9, 19))
        self.assertEqual(velha.faturamento, Decimal("200.00"))
        self.assertEqual(ItemVendaImportada.objects.count(), 4)

    def test_apagar_a_foto_velha_leva_os_itens_dela(self):
        """Senão o banco cresceria para sempre: são 32 mil itens por importação."""
        self.assertEqual(ItemVendaImportada.objects.count(), 4)
        self.primeira.delete()
        self.assertEqual(ItemVendaImportada.objects.count(), 2)

    def test_uma_terceira_importacao_tambem_nao_muda_nada(self):
        _importar(timezone.now())
        resultado = comparacao.montar()
        self.assertEqual(resultado.mudaram, [])

    def test_o_mesmo_arquivo_lido_de_novo_e_reconhecido(self):
        self.assertTrue(comparacao.montar().mesmo_backup)

    def test_backup_novo_aparece_como_arquivo_diferente(self):
        _importar(timezone.now(), bytes_=2000)
        self.assertFalse(comparacao.montar().mesmo_backup)

    def test_forcar_a_leitura_do_mesmo_backup_tambem_nao_soma(self):
        """O botão Forçar relê o mesmo arquivo de propósito, e é aqui que ele se prova.

        Pedido do Edson em 10/10/2026: ao forçar, tomar muito cuidado para não somar.
        Forçar não tem caminho próprio de gravação — é a mesma importação, com a sua
        própria foto —, então reler o mesmo backup tem que dar exatamente os mesmos
        números e deixar as telas lendo só a foto nova.
        """
        forcada = _importar(timezone.now(), forcada=True)
        resultado = comparacao.montar()
        self.assertEqual(resultado.atual, forcada)
        self.assertEqual(resultado.mudaram, [], "forçar releu o mesmo backup: nada pode mudar")
        self.assertFalse(resultado.alguma_dobrou)
        self.assertTrue(resultado.mesmo_backup)
        self.assertEqual(ProdutoImportado.objects.filter(importacao=forcada).count(), 2)
        self.assertEqual(ticket.calcular(forcada).total.faturamento, Decimal("500"))


class TestOQueMudou(TestCase):
    def setUp(self):
        agora = timezone.now()
        self.primeira = _importar(agora - timedelta(hours=2))
        self.segunda = _importar(agora - timedelta(hours=1), bytes_=2000)
        # O backup novo trouxe uma venda nova: é movimento da loja, não acúmulo.
        VendaImportada.objects.create(
            importacao=self.segunda, id_set=3, numero="3", data=date(2026, 9, 20),
            hora="11:00", dia_da_semana=0, valor=Decimal("100"), forma_pagamento="PIX",
        )

    def test_a_diferenca_e_so_o_movimento_do_periodo(self):
        resultado = comparacao.montar()
        mudou = {linha.rotulo: linha.diferenca for linha in resultado.mudaram}
        self.assertEqual(mudou["Vendas dos 12 meses"], 1)
        self.assertEqual(mudou["Faturamento dos 12 meses"], Decimal("100"))
        self.assertEqual(len(mudou), 2)

    def test_nao_acusa_dobra_num_crescimento_normal(self):
        self.assertFalse(comparacao.montar().alguma_dobrou)

    def test_acusa_quando_um_numero_dobra(self):
        """O alarme que o Edson quer: se um dia dobrar, a tela grita."""
        for id_set in range(10, 14):
            VendaImportada.objects.create(
                importacao=self.segunda, id_set=id_set, numero=str(id_set),
                data=date(2026, 9, 20), hora="11:00", dia_da_semana=0,
                valor=Decimal("10"), forma_pagamento="PIX",
            )
        self.assertTrue(comparacao.montar().alguma_dobrou)


class TestTelaDeImportacoes(TestCase):
    def setUp(self):
        agora = timezone.now()
        _importar(agora - timedelta(hours=2))
        _importar(agora - timedelta(hours=1))
        usuario("gerencia", ADMINISTRACAO)
        self.client.login(username="gerencia", password=SENHA_TESTE)

    def test_a_tela_diz_que_substitui_e_mostra_a_conferencia(self):
        resposta = self.client.get(reverse("importacao:historico"))
        self.assertContains(resposta, "O que mudou desde a importação anterior")
        self.assertContains(resposta, "substitui")
        self.assertContains(resposta, "substitui, e não soma")

    def test_sem_segunda_importacao_a_tela_explica_em_vez_de_quebrar(self):
        Importacao.objects.all().delete()
        _importar(timezone.now())
        resposta = self.client.get(reverse("importacao:historico"))
        self.assertContains(resposta, "Só existe uma importação concluída")

    def test_sem_importacao_nenhuma_a_tela_abre(self):
        Importacao.objects.all().delete()
        resposta = self.client.get(reverse("importacao:historico"))
        self.assertEqual(resposta.status_code, 200)
