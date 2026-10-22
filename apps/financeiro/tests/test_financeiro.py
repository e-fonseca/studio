"""Contas a pagar, despesas e a projeção de caixa."""

from datetime import date, timedelta
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.auditoria.models import EventoAuditoria
from apps.contas.perfis import ADMINISTRACAO, VENDEDOR
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.financeiro import servicos
from apps.financeiro.models import Lancamento, PagamentoPrevisto
from apps.importacao.models import Importacao


class BaseFinanceiro(TestCase):
    def setUp(self):
        cache.clear()
        self.hoje = timezone.localdate()
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO,
            situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(),
            data_corte=self.hoje - timedelta(days=1),
        )
        # Uma vencida, uma a vencer, uma paga no mês passado e um recebimento.
        self.vencida = Lancamento.objects.create(
            importacao=self.importacao, tipo=Lancamento.Tipo.PAGAR, descricao="ALUGUEL",
            contraparte="IMOBILIARIA CENTRO", grupo="1.01.05 - Aluguel",
            vencimento=self.hoje - timedelta(days=10), valor=Decimal("3000"),
        )
        Lancamento.objects.create(
            importacao=self.importacao, tipo=Lancamento.Tipo.PAGAR, descricao="LUZ",
            contraparte="ENERGIA SA", grupo="1.01.01 - Luz",
            vencimento=self.hoje + timedelta(days=5), valor=Decimal("800"),
        )
        Lancamento.objects.create(
            importacao=self.importacao, tipo=Lancamento.Tipo.PAGAR, descricao="VASOS",
            contraparte="CERAMICA BOA VISTA", grupo="1.07.01 - Compra p/ Revenda",
            vencimento=self.hoje - timedelta(days=40), pagamento=self.hoje - timedelta(days=40),
            valor=Decimal("5000"), valor_pago=Decimal("5000"),
        )
        Lancamento.objects.create(
            importacao=self.importacao, tipo=Lancamento.Tipo.RECEBER, descricao="VENDA 123",
            contraparte="CONSUMIDOR FINAL", grupo="2.01.01 - Vendas",
            vencimento=self.hoje - timedelta(days=40), pagamento=self.hoje - timedelta(days=40),
            valor=Decimal("9000"), valor_pago=Decimal("9000"),
        )
        self.gerente = usuario("gerente", ADMINISTRACAO)


class ResumoTest(BaseFinanceiro):
    def test_separa_vencido_do_que_ainda_vai_vencer(self):
        resumo = servicos.resumir(self.importacao, hoje=self.hoje)
        self.assertEqual(resumo.vencidas.quantidade, 1)
        self.assertEqual(resumo.vencidas.valor, Decimal("3000"))
        self.assertEqual(resumo.a_pagar.quantidade, 1)
        self.assertEqual(resumo.a_pagar.valor, Decimal("800"))

    def test_pagamento_previsto_entra_no_compromisso_e_na_faixa(self):
        PagamentoPrevisto.objects.create(
            descricao="ENTRADA DO PEDIDO", valor=Decimal("1200"),
            vencimento=self.hoje + timedelta(days=3),
        )
        resumo = servicos.resumir(self.importacao, hoje=self.hoje)
        self.assertEqual(resumo.compromisso_total, Decimal("5000"))  # 3000 + 800 + 1200
        sete_dias = next(f for f in resumo.por_faixa if f["dias"] == 7)
        self.assertEqual(sete_dias["valor"], Decimal("2000"))  # 800 do SET + 1200 previsto
        self.assertEqual(sete_dias["previsto"], Decimal("1200"))

    def test_previsto_ja_lancado_no_set_sai_da_projecao(self):
        """Senão o mesmo pagamento conta duas vezes: uma aqui e outra vindo do SET."""
        PagamentoPrevisto.objects.create(
            descricao="JA LANCADO", valor=Decimal("1200"), vencimento=self.hoje + timedelta(days=3),
            lancado_no_set=True,
        )
        resumo = servicos.resumir(self.importacao, hoje=self.hoje)
        self.assertEqual(resumo.previstos.quantidade, 0)
        self.assertEqual(resumo.compromisso_total, Decimal("3800"))

    def test_sem_importacao_nao_quebra(self):
        resumo = servicos.resumir(None)
        self.assertEqual(resumo.compromisso_total, Decimal("0"))
        self.assertEqual(servicos.contas_a_pagar(None), [])


class ListasTest(BaseFinanceiro):
    def test_contas_a_pagar_vem_com_os_dias_de_atraso(self):
        contas = servicos.contas_a_pagar(self.importacao, hoje=self.hoje)
        self.assertEqual([c.descricao for c in contas], ["ALUGUEL", "LUZ"])
        self.assertEqual(contas[0].atraso, 10)
        self.assertEqual(contas[1].atraso, 0)

    def test_despesas_por_grupo_usam_a_classificacao_do_set(self):
        grupos = servicos.despesas_por_grupo(self.importacao, hoje=self.hoje)
        self.assertEqual(grupos[0]["grupo"], "1.07.01 - Compra p/ Revenda")
        self.assertEqual(grupos[0]["valor"], Decimal("5000"))
        self.assertEqual(grupos[0]["fatia"], Decimal("100"))

    def test_mes_mostra_quanto_entrou_quanto_saiu_e_a_sobra(self):
        meses = servicos.despesas_por_mes(self.importacao)
        self.assertTrue(meses)
        mes = meses[-1]
        self.assertEqual(mes["recebido"], Decimal("9000"))
        self.assertEqual(mes["pago"], Decimal("5000"))
        self.assertEqual(mes["sobra"], Decimal("4000"))

    def test_pagamentos_por_fornecedor(self):
        linhas = servicos.pagamentos_a_fornecedores(self.importacao)
        self.assertEqual(linhas[0]["contraparte"], "CERAMICA BOA VISTA")
        self.assertEqual(linhas[0]["valor"], Decimal("5000"))


class TelasTest(BaseFinanceiro):
    def test_gerencia_ve_as_quatro_telas(self):
        self.client.login(username="gerente", password=SENHA_TESTE)
        for rota in ("contas_a_pagar", "despesas", "contas_a_receber", "pagamentos"):
            with self.subTest(rota=rota):
                resposta = self.client.get(reverse(f"financeiro:{rota}"))
                self.assertEqual(resposta.status_code, 200)

    def test_operador_nao_ve_o_financeiro(self):
        usuario("balcao", VENDEDOR)
        self.client.login(username="balcao", password=SENHA_TESTE)
        resposta = self.client.get(reverse("financeiro:contas_a_pagar"))
        self.assertEqual(resposta.status_code, 403)

    def test_registrar_previsto_grava_e_fica_na_auditoria(self):
        self.client.login(username="gerente", password=SENHA_TESTE)
        resposta = self.client.post(reverse("financeiro:salvar_previsto"), {
            "descricao": "ENTRADA DO PEDIDO DE VASOS",
            "fornecedor": "CERAMICA BOA VISTA",
            "valor": "1.200,50",
            "vencimento": (self.hoje + timedelta(days=10)).isoformat(),
        })
        self.assertRedirects(resposta, reverse("financeiro:pagamentos"))
        previsto = PagamentoPrevisto.objects.get()
        self.assertEqual(previsto.valor, Decimal("1200.50"))
        self.assertEqual(previsto.criado_por, self.gerente)
        self.assertTrue(EventoAuditoria.objects.filter(acao="financeiro.pagamento_previsto").exists())

    def test_valor_sem_sentido_nao_grava_e_explica(self):
        self.client.login(username="gerente", password=SENHA_TESTE)
        resposta = self.client.post(reverse("financeiro:salvar_previsto"), {
            "descricao": "QUALQUER COISA", "valor": "de graça",
            "vencimento": self.hoje.isoformat(),
        }, follow=True)
        self.assertEqual(PagamentoPrevisto.objects.count(), 0)
        self.assertContains(resposta, "preencha a descrição")

    def test_marcar_como_lancado_tira_da_projecao(self):
        previsto = PagamentoPrevisto.objects.create(
            descricao="ENTRADA", valor=Decimal("100"), vencimento=self.hoje,
        )
        self.client.login(username="gerente", password=SENHA_TESTE)
        self.client.post(reverse("financeiro:marcar_lancado", args=[previsto.pk]))
        previsto.refresh_from_db()
        self.assertTrue(previsto.lancado_no_set)


class TestFiltrosDasContasAPagar(TestCase):
    """Os filtros que a gerência pediu: atrasados, do dia, prestes, a vencer e futura."""

    def setUp(self):
        self.hoje = date(2026, 9, 20)
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO,
            situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(),
            data_corte=self.hoje,
        )
        for dias, descricao in ((-5, "ATRASADA"), (0, "DO DIA"), (3, "ESTA SEMANA"), (40, "LA NA FRENTE")):
            Lancamento.objects.create(
                importacao=self.importacao, tipo=Lancamento.Tipo.PAGAR, id_set=abs(dias) + 1,
                descricao=descricao, vencimento=self.hoje + timedelta(days=dias),
                valor=Decimal("100"),
            )
        self.gerente = usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)

    def _descricoes(self, filtro):
        contas = servicos.contas_a_pagar(self.importacao, hoje=self.hoje, filtro=filtro)
        return sorted(conta.descricao for conta in contas)

    def test_cada_filtro_pega_o_que_promete(self):
        self.assertEqual(self._descricoes("atrasados"), ["ATRASADA"])
        self.assertEqual(self._descricoes("do_dia"), ["DO DIA"])
        self.assertEqual(self._descricoes("prestes"), ["DO DIA", "ESTA SEMANA"])
        self.assertEqual(self._descricoes("a_vencer"), ["DO DIA", "ESTA SEMANA", "LA NA FRENTE"])
        self.assertEqual(self._descricoes("futura"), ["LA NA FRENTE"])
        self.assertEqual(len(self._descricoes("todas")), 4)

    def test_filtro_inventado_cai_no_padrao_em_vez_de_quebrar(self):
        resposta = self.client.get(reverse("financeiro:contas_a_pagar"), {"filtro": "xpto"})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "ATRASADA")

    def test_a_tela_mostra_quanto_cada_filtro_pega(self):
        resposta = self.client.get(reverse("financeiro:contas_a_pagar"), {"filtro": "atrasados"})
        self.assertContains(resposta, "Atrasados")
        self.assertContains(resposta, "Programação futura")
        self.assertContains(resposta, "ATRASADA")
        self.assertNotContains(resposta, "LA NA FRENTE")


class BuscaNasContasAPagar(BaseFinanceiro):
    """O campo de pesquisa pedido pelo Edson em 13/10/2026."""

    def setUp(self):
        super().setUp()
        self.com_acento = Lancamento.objects.create(
            importacao=self.importacao, tipo=Lancamento.Tipo.PAGAR,
            descricao="Pedido de Compra 000314", contraparte="QUITÉRIA FLOR MILHO",
            documento="/000314/01", parcela="01/02", grupo="1.07.01 - Compra p/ Revenda",
            vencimento=self.hoje + timedelta(days=3), valor=Decimal("1362"),
        )

    def _procurar(self, termo, filtro="todas"):
        return servicos.contas_a_pagar(self.importacao, hoje=self.hoje, filtro=filtro, busca=termo)

    def test_acha_pelo_fornecedor_digitado_sem_acento(self):
        """Quem procura digita 'quiteria'; o SET gravou 'QUITÉRIA'."""
        self.assertEqual(self._procurar("quiteria"), [self.com_acento])

    def test_acha_tambem_quando_digitam_com_acento(self):
        self.assertEqual(self._procurar("QUITÉRIA"), [self.com_acento])

    def test_acha_pela_descricao_pelo_documento_e_pela_classificacao(self):
        for termo in ("pedido de compra", "000314", "revenda"):
            with self.subTest(termo=termo):
                self.assertIn(self.com_acento, self._procurar(termo))

    def test_termo_que_nao_existe_devolve_lista_vazia(self):
        self.assertEqual(self._procurar("fornecedor que nao existe"), [])

    def test_busca_vazia_traz_tudo(self):
        self.assertEqual(len(self._procurar("   ")), 3)   # aluguel, luz e o pedido

    def test_a_busca_vale_junto_com_o_filtro(self):
        """Procurar dentro de 'Atrasados' não pode trazer conta que ainda vai vencer."""
        self.assertEqual(self._procurar("quiteria", filtro="atrasados"), [])
        self.assertEqual(self._procurar("aluguel", filtro="atrasados"), [self.vencida])

    def test_os_filtros_contam_so_o_que_a_busca_achou(self):
        """Senão o número do filtro e o número da lista discordam na tela."""
        filtros = servicos.filtros_de_contas(self.importacao, hoje=self.hoje, busca="quiteria")
        todas = next(f for f in filtros if f["chave"] == "todas")
        self.assertEqual(todas["quantidade"], 1)
        self.assertEqual(todas["valor"], Decimal("1362"))

    def test_caractere_de_expressao_regular_nao_quebra_a_busca(self):
        """Alguém digita '(' ou '*' sem querer; a tela não pode dar erro 500."""
        for termo in ("(", "*", "p/ revenda", "1.07.01", "[a-z]"):
            with self.subTest(termo=termo):
                self.assertIsInstance(self._procurar(termo), list)
        self.assertIn(self.com_acento, self._procurar("p/ revenda"))

    def test_a_tela_mostra_o_que_foi_procurado(self):
        self.client.login(username="gerente", password=SENHA_TESTE)
        pagina = self.client.get(reverse("financeiro:contas_a_pagar"), {"busca": "quiteria"})
        corpo = pagina.content.decode()
        self.assertEqual(pagina.status_code, 200)
        self.assertIn("QUITÉRIA FLOR MILHO", corpo)
        self.assertNotIn("IMOBILIARIA CENTRO", corpo)
        # O link do filtro tem que levar a busca junto, senão clicar nele apaga a procura.
        self.assertIn("busca=quiteria", corpo)


class RelatorioEmPdf(BaseFinanceiro):
    """O PDF pedido pelo Edson em 13/10/2026, para imprimir e levar para a reunião."""

    def _baixar(self, **parametros):
        self.client.login(username="gerente", password=SENHA_TESTE)
        return self.client.get(reverse("financeiro:contas_a_pagar_em_pdf"), parametros)

    def test_sai_um_pdf_de_verdade(self):
        resposta = self._baixar()
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta["Content-Type"], "application/pdf")
        self.assertIn("contas-a-pagar.pdf", resposta["Content-Disposition"])
        self.assertTrue(resposta.content.startswith(b"%PDF-"))
        self.assertTrue(resposta.content.rstrip().endswith(b"%%EOF"))

    def test_o_papel_traz_as_contas_e_o_total(self):
        corpo = self._baixar().content
        self.assertIn(b"ALUGUEL", corpo)
        self.assertIn(b"IMOBILIARIA CENTRO", corpo)
        self.assertIn("Total desta lista".encode("cp1252"), corpo)

    def test_o_papel_obedece_ao_filtro_e_a_busca_da_tela(self):
        """A tela e o papel nunca podem mostrar contas diferentes."""
        corpo = self._baixar(filtro="atrasados").content
        self.assertIn(b"ALUGUEL", corpo)
        self.assertNotIn(b"LUZ", corpo)
        corpo = self._baixar(busca="energia").content
        self.assertIn(b"LUZ", corpo)
        self.assertNotIn(b"ALUGUEL", corpo)

    def test_acento_chega_inteiro_no_papel(self):
        """O PDF usa WinAnsi: 'Classificação' e 'QUITÉRIA' têm que sair legíveis."""
        Lancamento.objects.create(
            importacao=self.importacao, tipo=Lancamento.Tipo.PAGAR, descricao="MANUTENÇÃO",
            contraparte="QUITÉRIA FLOR MILHO", vencimento=self.hoje, valor=Decimal("10"),
        )
        corpo = self._baixar(busca="quiteria").content
        self.assertIn("MANUTENÇÃO".encode("cp1252"), corpo)
        self.assertIn("QUITÉRIA FLOR MILHO".encode("cp1252"), corpo)

    def test_lista_vazia_nao_quebra_o_relatorio(self):
        resposta = self._baixar(busca="nao existe nada assim")
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("Nenhuma conta nesta lista".encode("cp1252"), resposta.content)

    def test_fica_na_trilha_de_auditoria(self):
        """É uma lista do que a loja deve, com nome de fornecedor, que sai impressa."""
        self._baixar(busca="aluguel")
        evento = EventoAuditoria.objects.filter(acao="financeiro.contas_a_pagar_em_pdf").first()
        self.assertIsNotNone(evento)
        self.assertEqual(evento.depois["busca"], "aluguel")
        self.assertEqual(evento.depois["contas"], 1)

    def test_o_vendedor_nao_tira_o_relatorio(self):
        usuario("vendedora_pdf", VENDEDOR)
        self.client.login(username="vendedora_pdf", password=SENHA_TESTE)
        resposta = self.client.get(reverse("financeiro:contas_a_pagar_em_pdf"))
        self.assertEqual(resposta.status_code, 403)

    def test_toda_lista_da_tela_gera_o_seu_pdf(self):
        """Pedido do Edson em 14/10/2026: o relatório em TODAS as listas, não em uma."""
        for chave, rotulo, _ in servicos.FILTROS:
            with self.subTest(lista=chave):
                resposta = self._baixar(filtro=chave)
                self.assertEqual(resposta.status_code, 200)
                self.assertTrue(resposta.content.startswith(b"%PDF-"))
                self.assertIn(rotulo.encode("cp1252"), resposta.content,
                              "o papel diz de qual lista ele é")

    def test_o_papel_mostra_as_seis_listas_e_marca_a_impressa(self):
        """Quem recebe a folha não vê a tela: sem isto, "1 conta" não diz se é muito."""
        corpo = self._baixar(filtro="atrasados").content
        for _, rotulo, _ in servicos.FILTROS:
            self.assertIn(rotulo.encode("cp1252"), corpo)
        # Parêntese dentro de PDF vai com barra: no fluxo da página está "Atrasados \(esta\)".
        self.assertIn(rb"Atrasados \(esta\)", corpo)
        self.assertNotIn(rb"Do dia \(esta\)", corpo)


class RelatorioEmPlanilha(BaseFinanceiro):
    """A planilha pedida pelo Edson em 19/10/2026, ao lado do PDF e no mesmo layout."""

    def _baixar(self, **parametros):
        self.client.login(username="gerente", password=SENHA_TESTE)
        return self.client.get(reverse("financeiro:contas_a_pagar_em_planilha"), parametros)

    def _aba(self, resposta):
        import zipfile
        from io import BytesIO
        from xml.etree import ElementTree

        arquivo = zipfile.ZipFile(BytesIO(resposta.content))
        return ElementTree.fromstring(arquivo.read("xl/worksheets/sheet1.xml"))

    def _textos(self, resposta):
        espaco = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        return [t.text for t in self._aba(resposta).iter(f"{espaco}t")]

    def test_sai_uma_planilha_de_verdade(self):
        resposta = self._baixar()
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("spreadsheetml", resposta["Content-Type"])
        self.assertIn("contas-a-pagar.xlsx", resposta["Content-Disposition"])
        # Todo .xlsx é um zip, e todo zip começa por PK.
        self.assertTrue(resposta.content.startswith(b"PK"))

    def test_traz_as_mesmas_contas_do_papel(self):
        """"No mesmo layout" é isto: as duas saídas vêm do mesmo montador."""
        textos = self._textos(self._baixar())
        self.assertIn("ALUGUEL", textos)
        self.assertIn("IMOBILIARIA CENTRO", textos)
        self.assertIn("Total desta lista", textos)
        self.assertIn("Contas a pagar", textos)

    def test_o_valor_da_conta_vai_como_numero_e_nao_como_texto(self):
        """Planilha que não soma é um PDF mais feio."""
        textos = self._textos(self._baixar())
        self.assertFalse([t for t in textos if t and t.startswith("R$")],
                         "saiu dinheiro escrito como texto; a coluna não somaria")

    def test_o_filtro_da_tela_vale_na_planilha(self):
        for chave, rotulo, _ in servicos.FILTROS:
            with self.subTest(lista=chave):
                resposta = self._baixar(filtro=chave)
                self.assertEqual(resposta.status_code, 200)
                self.assertIn(rotulo, " ".join(t for t in self._textos(resposta) if t))

    def test_a_busca_da_tela_vale_na_planilha(self):
        textos = self._textos(self._baixar(busca="aluguel"))
        self.assertIn("Procurado por: aluguel", textos)

    def test_fica_na_trilha_de_auditoria(self):
        """Mesma razão do PDF: é o que a loja deve, com nome de fornecedor, saindo daqui."""
        self._baixar(busca="aluguel")
        evento = EventoAuditoria.objects.filter(
            acao="financeiro.contas_a_pagar_em_planilha").first()
        self.assertIsNotNone(evento)
        self.assertEqual(evento.depois["busca"], "aluguel")
        self.assertEqual(evento.depois["contas"], 1)

    def test_o_vendedor_nao_baixa_a_planilha(self):
        usuario("vendedora_planilha", VENDEDOR)
        self.client.login(username="vendedora_planilha", password=SENHA_TESTE)
        resposta = self.client.get(reverse("financeiro:contas_a_pagar_em_planilha"))
        self.assertEqual(resposta.status_code, 403)


class OsDoisBotoesDaLista(BaseFinanceiro):
    """O botão estava no cartão de busca, acima dos filtros, e parecia servir a uma lista só."""

    def _tela(self, **parametros):
        self.client.login(username="gerente", password=SENHA_TESTE)
        return self.client.get(reverse("financeiro:contas_a_pagar"), parametros).content.decode()

    def test_os_dois_botoes_aparecem_em_qualquer_lista_e_dizem_o_nome_dela(self):
        for chave, rotulo, _ in servicos.FILTROS:
            with self.subTest(lista=chave):
                corpo = self._tela(filtro=chave).replace("&amp;", "&")
                self.assertIn(f"Gerar PDF de {rotulo} para imprimir", corpo)
                self.assertIn(f"Baixar {rotulo} em planilha", corpo)
                self.assertIn(f"/financeiro/pdf/?filtro={chave}", corpo)
                self.assertIn(f"/financeiro/planilha/?filtro={chave}", corpo)

    def test_os_dois_botoes_levam_a_busca_junto(self):
        """Botão que diz o nome da lista e manda outra é o defeito da 1.31.0."""
        corpo = self._tela(filtro="atrasados", busca="aluguel").replace("&amp;", "&")
        self.assertIn("/financeiro/pdf/?filtro=atrasados&busca=aluguel", corpo)
        self.assertIn("/financeiro/planilha/?filtro=atrasados&busca=aluguel", corpo)

    def test_lista_vazia_continua_com_os_botoes(self):
        """Some o botão, e some a resposta para "por que esta lista não imprime?"."""
        corpo = self._tela(busca="nao existe nada assim")
        self.assertIn("para imprimir", corpo)
        self.assertIn("em planilha", corpo)


class ContaSemDataDeVencimento(BaseFinanceiro):
    """Conta em aberto sem data no SET tem que entrar no comprometido.

    Achado na revisão geral de 15/10/2026. "Venceu" e "vai vencer" são os dois lados de
    uma comparação com hoje, e comparação com data vazia não dá verdadeiro nem falso: a
    conta ficava fora das duas, e por isso fora do compromisso total. O importador copia
    a data como ela está no SET, e lá ela pode estar vazia — a folha de contas a pagar já
    imprime "sem data" para exatamente este caso. Resultado: a loja devia mais do que o
    sistema dizia, e o teto de compra de "Antes de comprar", que desconta o compromisso
    do caixa, aparecia maior do que é.
    """

    def setUp(self):
        super().setUp()
        self.sem_data = Lancamento.objects.create(
            importacao=self.importacao, tipo=Lancamento.Tipo.PAGAR, descricao="FRETE",
            contraparte="TRANSPORTADORA", grupo="1.03.01 - Frete",
            vencimento=None, valor=Decimal("8000"),
        )

    def test_entra_no_compromisso_total(self):
        resumo = servicos.resumir(self.importacao, hoje=self.hoje)
        self.assertEqual(resumo.sem_data.quantidade, 1)
        self.assertEqual(resumo.sem_data.valor, Decimal("8000"))
        # 3000 vencida + 800 a vencer + 8000 sem data
        self.assertEqual(resumo.compromisso_total, Decimal("11800"))

    def test_as_fatias_fecham_com_a_lista_de_todas_em_aberto(self):
        """Conferir uma coluna com a outra é o que a gerência faz; tem que fechar."""
        resumo = servicos.resumir(self.importacao, hoje=self.hoje)
        todas = servicos.contas_a_pagar(self.importacao, hoje=self.hoje)
        self.assertEqual(
            resumo.vencidas.quantidade + resumo.a_pagar.quantidade + resumo.sem_data.quantidade,
            len(todas))

    def test_a_tela_mostra_a_fatia_sem_data(self):
        self.client.login(username="gerente", password=SENHA_TESTE)
        corpo = self.client.get(reverse("financeiro:contas_a_pagar")).content.decode()
        self.assertIn("Sem data no SET", corpo)

    def test_sem_conta_assim_a_tela_nao_mostra_o_cartao(self):
        self.sem_data.delete()
        self.client.login(username="gerente", password=SENHA_TESTE)
        corpo = self.client.get(reverse("financeiro:contas_a_pagar")).content.decode()
        self.assertNotIn("Sem data no SET", corpo)


class AJanelaDasDespesas(TestCase):
    """As três janelas da tela de Despesas começam no mesmo dia 1º.

    Achado na revisão geral de 15/10/2026. "Para onde o dinheiro foi" contava 30 dias por
    mês (360) e o mês a mês contava 31 (372), as duas na mesma tela e as duas chamadas de
    doze meses: somar uma coluna e conferir com a outra deixava doze dias de pagamento de
    diferença, sem causa visível. E as duas começavam no meio de um mês, então o mês mais
    antigo entrava com um terço dos dias e puxava a média para baixo.
    """

    def test_a_janela_comeca_no_dia_primeiro(self):
        self.assertEqual(servicos.inicio_da_janela(date(2026, 10, 14), 12), date(2025, 10, 1))
        self.assertEqual(servicos.inicio_da_janela(date(2026, 1, 5), 12), date(2025, 1, 1))
        self.assertEqual(servicos.inicio_da_janela(date(2026, 3, 31), 1), date(2026, 2, 1))
        self.assertEqual(servicos.inicio_da_janela(date(2026, 1, 15), 3), date(2025, 10, 1))

    def test_as_tres_consultas_da_tela_olham_o_mesmo_periodo(self):
        """Mesma régua nas três: antes eram 360, 372 e 372 dias."""
        importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO, situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(), data_corte=date(2026, 10, 14),
        )
        # Um pagamento no dia 20/10/2025: dentro da janela de meses inteiros, e fora da
        # janela de 360 dias que a tela de grupos usava.
        Lancamento.objects.create(
            importacao=importacao, tipo=Lancamento.Tipo.PAGAR, descricao="ALUGUEL ANTIGO",
            contraparte="IMOBILIARIA CENTRO", grupo="1.01.05 - Aluguel",
            vencimento=date(2025, 10, 20), pagamento=date(2025, 10, 20),
            valor=Decimal("3000"), valor_pago=Decimal("3000"),
        )
        por_grupo = servicos.despesas_por_grupo(importacao)
        por_mes = servicos.despesas_por_mes(importacao)
        self.assertEqual(sum(linha["valor"] for linha in por_grupo), Decimal("3000"))
        self.assertEqual(sum(mes["pago"] for mes in por_mes), Decimal("3000"))


class ADespesaMediaPorMes(TestCase):
    """O divisor é mês de calendário, não mês que teve pagamento.

    Achado na revisão geral de 15/10/2026. `despesas_por_mes` agrupa pagamentos, então um
    mês em que a loja não pagou nada simplesmente não existia como chave e saía do
    divisor: a média ficava maior do que a realidade — e é esse número que a gerência usa
    para dizer se o mês está caro.
    """

    def setUp(self):
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO, situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(), data_corte=date(2026, 10, 14),
        )

    def _pagar(self, quando, valor):
        Lancamento.objects.create(
            importacao=self.importacao, tipo=Lancamento.Tipo.PAGAR, descricao="DESPESA",
            contraparte="FORNECEDOR", grupo="1.01.01 - Luz",
            vencimento=quando, pagamento=quando,
            valor=Decimal(valor), valor_pago=Decimal(valor),
        )

    def test_mes_sem_pagamento_entra_no_divisor(self):
        # Pagou em julho e em setembro; agosto ficou em branco. O mês do corte (outubro)
        # não entra na média porque ainda está correndo.
        self._pagar(date(2026, 7, 10), 3000)
        self._pagar(date(2026, 9, 10), 3000)
        self._pagar(date(2026, 10, 2), 9999)
        resumo = servicos.resumir(self.importacao, hoje=date(2026, 10, 14))
        # 6000 em três meses de calendário (julho, agosto, setembro), e não em dois.
        self.assertEqual(resumo.despesa_media_mensal, Decimal("2000"))


class ADataDoPagamentoPrevisto(BaseFinanceiro):
    """Data impossível no formulário de dinheiro vira recado, e não tela de erro.

    Achado na revisão geral de 15/10/2026. A data ia crua para o campo do banco: qualquer
    coisa que não fosse o que o calendário do navegador escreve estourava na gravação, num
    formulário que já tem recado pronto para todo o resto.
    """

    def setUp(self):
        super().setUp()
        self.client.login(username="gerente", password=SENHA_TESTE)

    def _salvar(self, vencimento):
        return self.client.post(reverse("financeiro:salvar_previsto"), {
            "descricao": "ENTRADA DO PEDIDO", "valor": "1.200,00", "vencimento": vencimento,
        }, follow=True)

    def test_data_impossivel_nao_derruba_a_tela(self):
        for ruim in ("2026-13-45", "amanhã", "31/02/2026", "0000-00-00"):
            with self.subTest(ruim=ruim):
                resposta = self._salvar(ruim)
                self.assertEqual(resposta.status_code, 200)
                self.assertEqual(PagamentoPrevisto.objects.count(), 0)
                recados = [str(m) for m in resposta.context["messages"]]
                self.assertTrue(any("data de vencimento" in r for r in recados), recados)

    def test_a_data_do_calendario_do_navegador_continua_valendo(self):
        self._salvar("2026-11-05")
        self.assertEqual(PagamentoPrevisto.objects.get().vencimento, date(2026, 11, 5))

    def test_tambem_aceita_a_data_escrita_como_gente_escreve(self):
        self._salvar("05/11/2026")
        self.assertEqual(PagamentoPrevisto.objects.get().vencimento, date(2026, 11, 5))
