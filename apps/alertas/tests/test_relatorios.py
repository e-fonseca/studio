"""Os quatro relatórios: o que cada um diz, e que ele diz o mesmo que a tela."""

from datetime import date, datetime, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.alertas import relatorios, telegram
from apps.caixa.models import CaixaImportado
from apps.compras import limite, lista_de_compra, sugestoes
from apps.financeiro import servicos as financeiro
from apps.financeiro.models import Lancamento
from apps.importacao.models import (Importacao, ItemVendaImportada, ProdutoImportado,
                                    VendaImportada)
from apps.painel import vendas_do_dia as vendas_da_tela

CORTE = date(2026, 9, 20)


class BaseRelatorio(TestCase):
    def setUp(self):
        self.hoje = timezone.localdate()
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO,
            situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(),
            data_corte=CORTE,
            dias_abertos_12m=360,
            produtos=0,
        )

    def conta(self, descricao, dias, valor="100", **campos):
        return Lancamento.objects.create(
            importacao=self.importacao, tipo=Lancamento.Tipo.PAGAR, descricao=descricao,
            contraparte=campos.pop("contraparte", "FORNECEDOR X"),
            grupo=campos.pop("grupo", "1.07.01 - Compra p/ Revenda"),
            vencimento=self.hoje + timedelta(days=dias), valor=Decimal(valor), **campos,
        )

    def produto(self, codigo, **campos):
        padrao = dict(
            importacao=self.importacao, codigo=codigo, descricao=f"PRODUTO {codigo}",
            grupo="TAPETE", fornecedor="GERMAN", custo=Decimal("10"),
            preco_venda=Decimal("25"), estoque=Decimal("0"), vendas_12m=Decimal("360"),
            receita_12m=Decimal("9000"),
        )
        padrao.update(campos)
        return ProdutoImportado.objects.create(**padrao)


class SemImportacaoTest(TestCase):
    """Antes da primeira importação o e-mail não pode inventar número nenhum."""

    def test_todos_dizem_que_nao_ha_dado_e_nao_tem_noticia(self):
        for rotina in ("contas", "vendas", "estoque", "compra"):
            with self.subTest(rotina=rotina):
                relatorio = relatorios.montar(rotina)
                self.assertFalse(relatorio.tem_noticia)
                self.assertIn("Ainda não há dados importados", relatorio.manchete)
                self.assertEqual(relatorio.blocos, [])


class ContasAPagarTest(BaseRelatorio):
    def test_sem_conta_nas_tres_faixas_nao_tem_noticia(self):
        self.conta("DAQUI A MUITO TEMPO", dias=60)
        relatorio = relatorios.contas_a_pagar(self.importacao, hoje=self.hoje)
        self.assertFalse(relatorio.tem_noticia)
        self.assertIn("Caixa tranquilo", relatorio.manchete)

    def test_as_tres_faixas_na_ordem_da_urgencia(self):
        self.conta("VENCIDA", dias=-10, valor="3000")
        self.conta("HOJE", dias=0, valor="800")
        self.conta("NA SEMANA", dias=5, valor="500")
        relatorio = relatorios.contas_a_pagar(self.importacao, hoje=self.hoje)
        self.assertTrue(relatorio.tem_noticia)
        titulos = [b.titulo for b in relatorio.blocos]
        self.assertIn("Já venceram: 1 conta(s)", titulos[0])
        self.assertIn("Vencem hoje: 1 conta(s)", titulos[1])
        self.assertIn(f"Vencem em até {financeiro.DIAS_PRESTES_A_VENCER} dias", titulos[2])

    def test_a_manchete_leva_o_total_vencido(self):
        self.conta("VENCIDA", dias=-10, valor="3000")
        relatorio = relatorios.contas_a_pagar(self.importacao, hoje=self.hoje)
        self.assertIn("R$ 3.000,00", relatorio.manchete)
        self.assertEqual(relatorio.resumo, relatorio.manchete)

    def test_a_conta_de_hoje_nao_conta_duas_vezes(self):
        """O filtro "prestes" do financeiro já inclui hoje; somar os três inflava o número."""
        self.conta("HOJE", dias=0, valor="800")
        relatorio = relatorios.contas_a_pagar(self.importacao, hoje=self.hoje)
        self.assertIn("1 conta(s)", relatorio.manchete)

    def test_a_linha_diz_quantos_dias_de_atraso(self):
        self.conta("VENCIDA", dias=-10, valor="3000", contraparte="CERAMICA BOA VISTA")
        bloco = relatorios.contas_a_pagar(self.importacao, hoje=self.hoje).blocos[0]
        linha = bloco.linhas[0]
        self.assertEqual(linha["quem"], "CERAMICA BOA VISTA")
        self.assertEqual(linha["valor"], "R$ 3.000,00")
        self.assertIn("10 dia(s) de atraso", linha["detalhe"])

    def test_lista_longa_e_cortada_e_o_e_mail_diz_quantas_ficaram(self):
        """E-mail que precisa de rolagem no celular não é lido."""
        for i in range(relatorios.LINHAS_NO_EMAIL + 5):
            self.conta(f"VENCIDA {i}", dias=-3 - i)
        bloco = relatorios.contas_a_pagar(self.importacao, hoje=self.hoje).blocos[0]
        self.assertEqual(len(bloco.linhas), relatorios.LINHAS_NO_EMAIL)
        self.assertEqual(bloco.escondidas, 5)

    def test_conta_paga_nao_entra(self):
        self.conta("JA PAGA", dias=-10, valor="3000",
                   pagamento=self.hoje - timedelta(days=10), valor_pago=Decimal("3000"))
        self.assertFalse(relatorios.contas_a_pagar(self.importacao, hoje=self.hoje).tem_noticia)

    def test_e_a_mesma_conta_da_tela(self):
        """Número do e-mail diferente do número da tela derruba a confiança no sistema."""
        self.conta("VENCIDA", dias=-10, valor="3000")
        self.conta("HOJE", dias=0, valor="800")
        da_tela = financeiro.contas_a_pagar(self.importacao, hoje=self.hoje, filtro="atrasados")
        bloco = relatorios.contas_a_pagar(self.importacao, hoje=self.hoje).blocos[0]
        self.assertEqual(len(bloco.linhas), len(da_tela))
        self.assertIn(f"{len(da_tela)} conta(s)", bloco.titulo)


class EstoqueTest(BaseRelatorio):
    def test_sem_produto_parado_nao_tem_noticia(self):
        self.produto("1", estoque=Decimal("50"))
        relatorio = relatorios.estoque(self.importacao)
        self.assertFalse(relatorio.tem_noticia)

    def test_produto_que_entrou_e_nao_vendeu_vira_noticia(self):
        self.produto("1", estoque=Decimal("20"), vendas_12m=Decimal("0"), receita_12m=Decimal("0"),
                     compras_12m=Decimal("20"), valor_compras_12m=Decimal("200"))
        relatorio = relatorios.estoque(self.importacao)
        self.assertTrue(relatorio.tem_noticia)
        self.assertIn("Parar de comprar", " ".join(b.titulo for b in relatorio.blocos))
        self.assertIn("R$ 200,00", relatorio.manchete)

    def test_o_primeiro_bloco_e_sempre_o_que_esta_na_prateleira(self):
        self.produto("1", estoque=Decimal("20"))
        relatorio = relatorios.estoque(self.importacao)
        self.assertEqual(relatorio.blocos[0].titulo, "O que está na prateleira hoje")
        self.assertIn("R$ 200,00", relatorio.blocos[0].frase)  # 20 unidades a R$ 10

    def test_o_bloco_de_repor_fica_fora_porque_e_assunto_do_outro_relatorio(self):
        self.produto("1", estoque=Decimal("0"), vendas_90d=Decimal("30"))
        relatorio = relatorios.estoque(self.importacao)
        do_sistema = {b.chave for b in sugestoes.montar(self.importacao).blocos if not b.vazio}
        self.assertIn("repor", do_sistema)
        self.assertNotIn("Repor", " ".join(b.titulo for b in relatorio.blocos))


class SugestaoDeCompraTest(BaseRelatorio):
    def test_sem_nada_para_comprar_nao_tem_noticia(self):
        self.produto("1", estoque=Decimal("400"))
        relatorio = relatorios.sugestao_de_compra(self.importacao, hoje=self.hoje)
        self.assertFalse(relatorio.tem_noticia)
        self.assertIn("Nenhum produto abaixo do mínimo", relatorio.manchete)

    def test_produto_zerado_que_vende_entra_por_fornecedor(self):
        self.produto("1")
        relatorio = relatorios.sugestao_de_compra(self.importacao, hoje=self.hoje)
        self.assertTrue(relatorio.tem_noticia)
        self.assertIn("GERMAN", relatorio.blocos[0].titulo)
        self.assertIn("1 produto(s) já faltando", relatorio.manchete)

    def test_a_lista_e_a_mesma_da_tela(self):
        """Inclusive o corte do teto: a tela monta e prioriza, e o e-mail faz os dois."""
        for codigo in range(4):
            self.produto(str(codigo), fornecedor=f"FORNECEDOR {codigo}")
        resumo = financeiro.resumir(self.importacao, hoje=self.hoje)
        da_tela = lista_de_compra.priorizar(
            lista_de_compra.montar(self.importacao, hoje=self.hoje),
            limite.montar(self.importacao, hoje=self.hoje, resumo_caixa=resumo).teto,
        )
        relatorio = relatorios.sugestao_de_compra(self.importacao, hoje=self.hoje)
        self.assertIn(f"{da_tela.quantos} na lista", relatorio.manchete)
        self.assertTrue(da_tela.primeiro)
        com_linhas = [b for b in relatorio.blocos if b.linhas]
        self.assertEqual(len(com_linhas), len(da_tela.primeiro))
        nos_blocos = sum(len(b.linhas) + b.escondidas for b in com_linhas)
        self.assertEqual(nos_blocos, sum(len(f.itens) for f in da_tela.primeiro))

    def test_o_que_nao_cabe_no_teto_vira_uma_linha_no_fim(self):
        for codigo in range(4):
            self.produto(str(codigo), fornecedor=f"FORNECEDOR {codigo}")
        relatorio = relatorios.sugestao_de_compra(self.importacao, hoje=self.hoje)
        ultimo = relatorio.blocos[-1].titulo
        if "Fora do teto do mês" in ultimo:
            self.assertIn("produto(s)", ultimo)

    def test_a_linha_diz_o_que_tem_e_o_que_comprar(self):
        self.produto("1")
        bloco = relatorios.sugestao_de_compra(self.importacao, hoje=self.hoje).blocos[0]
        self.assertIn("tem 0, comprar", bloco.linhas[0]["o_que"])


class AvisoDeDadosVelhosTest(BaseRelatorio):
    def test_importacao_antiga_avisa_no_topo_do_e_mail(self):
        """Dado velho muda o que o e-mail significa, então vai escrito antes dos números."""
        self.importacao.data_corte = self.hoje - timedelta(days=30)
        self.importacao.save()
        relatorio = relatorios.contas_a_pagar(self.importacao, hoje=self.hoje)
        self.assertTrue(relatorio.aviso)

    def test_importacao_de_hoje_nao_avisa_nada(self):
        self.importacao.data_corte = self.hoje
        self.importacao.save()
        self.assertEqual(relatorios.contas_a_pagar(self.importacao, hoje=self.hoje).aviso, "")


class ContasEmAbertoTest(BaseRelatorio):
    def test_conta_quantas_estao_em_aberto_para_a_tela_de_configuracao(self):
        self.conta("UMA", dias=-10)
        self.conta("OUTRA", dias=30)
        self.conta("PAGA", dias=-5, pagamento=self.hoje, valor_pago=Decimal("100"))
        self.assertEqual(relatorios.contas_em_aberto(self.importacao), 2)

    def test_sem_importacao_e_zero_e_nao_estoura(self):
        self.assertEqual(relatorios.contas_em_aberto(None), 0)


class VendasDoDiaTest(BaseRelatorio):
    """A relação do dia que o Edson pediu em 11/10/2026, agora também por e-mail."""

    def venda(self, dia=CORTE, valor="0", linhas=()):
        self.proxima = getattr(self, "proxima", 0) + 1
        cabecalho = VendaImportada.objects.create(
            importacao=self.importacao, id_set=self.proxima, numero=str(self.proxima),
            data=dia, hora="10:00", dia_da_semana=(dia.weekday() + 1) % 7,
            valor=Decimal(valor), forma_pagamento="DINHEIRO",
        )
        for linha in linhas:
            codigo, descricao, vendido, custo = linha[:4]
            cadastro = linha[4] if len(linha) > 4 else None
            unitario = None if custo is None else Decimal(custo)
            do_cadastro = None if cadastro is None else Decimal(cadastro)
            ItemVendaImportada.objects.create(
                venda=cabecalho, codigo=codigo, descricao=descricao, grupo="VIME",
                quantidade=Decimal("1"), valor_total=Decimal(vendido),
                custo_unitario=unitario, custo_total=unitario,
                custo_cadastro_unitario=do_cadastro, custo_estimado_total=do_cadastro,
            )
        return cabecalho

    def test_dia_sem_venda_nao_tem_noticia(self):
        relatorio = relatorios.vendas_do_dia(self.importacao)
        self.assertFalse(relatorio.tem_noticia)
        self.assertIn("Nenhuma venda", relatorio.manchete)

    def test_a_manchete_tem_o_dia_o_vendido_e_o_que_sobrou(self):
        self.venda(valor="300", linhas=[("001", "VASO DE VIME", "300", "100")])
        relatorio = relatorios.vendas_do_dia(self.importacao)
        self.assertTrue(relatorio.tem_noticia)
        self.assertIn("20/09/2026", relatorio.manchete)
        self.assertIn("R$ 300,00", relatorio.manchete)
        self.assertIn("R$ 200,00", relatorio.manchete)
        self.assertIn("66,7%", relatorio.manchete)

    def test_o_numero_do_email_e_o_numero_da_tela(self):
        """Regra copiada é regra que diverge: o relatório chama a função da tela."""
        self.venda(valor="300", linhas=[("001", "VASO", "200", "50"),
                                        ("002", "CESTO", "100", "90")])
        relatorio = relatorios.vendas_do_dia(self.importacao)
        da_tela = vendas_da_tela.calcular(self.importacao)
        self.assertIn(relatorios._reais(da_tela.faturamento), relatorio.manchete)
        self.assertIn(relatorios._reais(da_tela.lucro), relatorio.manchete)
        self.assertIn("2 produto(s) em 1 venda(s)", relatorio.blocos[0].frase)

    def test_leva_os_produtos_do_maior_para_o_menor(self):
        self.venda(linhas=[("001", "MENOR", "10", "5"), ("002", "MAIOR", "500", "100")])
        relatorio = relatorios.vendas_do_dia(self.importacao)
        campeoes = next(b for b in relatorio.blocos if b.titulo == "O que mais vendeu")
        self.assertEqual([linha["quem"] for linha in campeoes.linhas], ["MAIOR", "MENOR"])
        self.assertIn("sobrou R$ 400,00", campeoes.linhas[0]["detalhe"])

    def test_avisa_quando_o_produto_nao_tem_custo_nenhum(self):
        self.venda(linhas=[("001", "COM CUSTO", "100", "60"),
                           ("002", "SEM CUSTO", "100", None)])
        relatorio = relatorios.vendas_do_dia(self.importacao)
        self.assertIn("não têm custo nenhum", relatorio.blocos[0].frase)
        self.assertIn("R$ 100,00 de venda que ficam fora da conta do lucro",
                      relatorio.blocos[0].frase)
        # 40 sobre 100: o item sem custo não entra como lucro cheio.
        self.assertIn("40,0%", relatorio.manchete)

    def test_avisa_quando_o_custo_e_estimado_pelo_cadastro(self):
        """De 25/08/2026 em diante é o caso de quase todo item de todo dia."""
        self.venda(linhas=[("001", "ESTIMADO", "100", None, "40")])
        relatorio = relatorios.vendas_do_dia(self.importacao)
        self.assertIn("não gravou o custo de 1 produto", relatorio.blocos[0].frase)
        self.assertIn("o custo é o do cadastro, uma estimativa", relatorio.blocos[0].frase)
        self.assertIn("R$ 60,00", relatorio.manchete)
        campeoes = next(b for b in relatorio.blocos if b.titulo == "O que mais vendeu")
        self.assertIn("custo estimado", campeoes.linhas[0]["detalhe"])

    def test_prejuizo_estimado_nao_vira_bloco_de_alarme(self):
        """Produto vendido a peso apareceria como prejuízo sem a loja ter perdido nada."""
        self.venda(linhas=[("001", "PEDRA POR QUILO", "41", None, "130")])
        titulos = [b.titulo for b in relatorios.vendas_do_dia(self.importacao).blocos]
        self.assertFalse([t for t in titulos if "abaixo do custo" in t])

    def test_domingo_leva_a_meta_e_a_venda_fora_da_regra(self):
        """Pedido de 02/11/2026: o e-mail do dia diz a meta e o desconto que passou da regra."""
        venda = self.venda(valor="85", linhas=[("001", "VASO", "100", "40")])
        venda.desconto, venda.total_produtos = Decimal("15"), Decimal("100")
        venda.forma_pagamento, venda.recebido_por = "CARTAO CREDITO", "CAIXA TESTE"
        venda.save()
        relatorio = relatorios.vendas_do_dia(self.importacao)
        meta = next(b for b in relatorio.blocos if b.titulo == "Meta do dia: Domingo")
        self.assertIn("Vendeu R$ 85,00 de R$ 15.000,00", meta.frase)
        fora = next(b for b in relatorio.blocos if b.titulo.startswith("Descontos fora da regra"))
        self.assertEqual(fora.titulo, "Descontos fora da regra: 1 venda(s)")
        self.assertIn("recebeu Caixa Teste", fora.linhas[0]["quem"])
        self.assertEqual(fora.linhas[0]["valor"], "R$ 15,00")
        self.assertIn("no cartão de crédito ela é sem desconto", fora.linhas[0]["o_que"])

    def test_desconto_dentro_da_regra_nao_vira_bloco(self):
        venda = self.venda(valor="93", linhas=[("001", "VASO", "100", "40")])
        venda.desconto, venda.total_produtos, venda.forma_pagamento = Decimal("7"), Decimal("100"), "PIX"
        venda.save()
        titulos = [b.titulo for b in relatorios.vendas_do_dia(self.importacao).blocos]
        self.assertFalse([t for t in titulos if t.startswith("Descontos fora da regra")])

    def test_vendido_abaixo_do_custo_ganha_um_bloco_proprio(self):
        """É a única coisa aqui que pede ação hoje."""
        self.venda(linhas=[("001", "NO PREJUIZO", "30", "50")])
        relatorio = relatorios.vendas_do_dia(self.importacao)
        titulos = [b.titulo for b in relatorio.blocos]
        self.assertIn("Vendidos abaixo do custo: 1 produto(s)", titulos)

    def test_sem_prejuizo_nao_inventa_o_bloco(self):
        self.venda(linhas=[("001", "NORMAL", "100", "50")])
        titulos = [b.titulo for b in relatorios.vendas_do_dia(self.importacao).blocos]
        self.assertFalse([t for t in titulos if "abaixo do custo" in t])

    def test_o_link_leva_para_a_tela_da_relacao(self):
        self.venda(linhas=[("001", "VASO", "100", "50")])
        relatorio = relatorios.vendas_do_dia(self.importacao)
        self.assertEqual(relatorio.caminho, "/sistema/painel/vendas-do-dia/")


class CaixaNoEmailDeVendasTest(BaseRelatorio):
    """Pedidos do Edson: em 28/10/2026, o caixa inicial e o final com quem abriu e fechou;
    em 29/10/2026, o final EM DINHEIRO e o que entrou por PIX, débito e crédito."""

    venda = VendasDoDiaTest.venda
    # O caixa 970 da cópia de 20/09/2026, com os números de verdade.
    FORMAS = {"PIX": "1881.00", "AVISTA": "754.50", "CARTAO DEBITO": "2055.50",
              "CARTAO CREDITO": "3376.50"}

    def caixa(self, id_set, abriu, fechou=None, **campos):
        aberto_em = timezone.make_aware(abriu)
        padrao = dict(
            importacao=self.importacao, id_set=id_set, dia=aberto_em.date(),
            aberto_em=aberto_em, operador="MARIA", operador_fechamento="JOAO",
            saldo_inicial=Decimal("379.40"), saldo_final=Decimal("8180.65"),
            recebido=Decimal("8067.50"), sangrias=Decimal("266.25"), por_forma=self.FORMAS,
            situacao=CaixaImportado.Situacao.FECHADO,
            fechado_em=timezone.make_aware(fechou) if fechou else None,
        )
        padrao.update(campos)
        return CaixaImportado.objects.create(**padrao)

    def bloco(self):
        relatorio = relatorios.vendas_do_dia(self.importacao)
        return next(b for b in relatorio.blocos if b.titulo == "Caixa do dia")

    def valores(self):
        return {linha["quem"]: linha["valor"] for linha in self.bloco().linhas}

    def setUp(self):
        super().setUp()
        self.venda(valor="100", linhas=[("001", "VASO", "100", "50")])

    def test_inicio_e_final_em_dinheiro_e_as_formas_na_ordem_pedida(self):
        self.caixa(970, datetime(2026, 9, 20, 9, 41), datetime(2026, 9, 20, 18, 10))
        self.assertEqual([(linha["quem"], linha["valor"]) for linha in self.bloco().linhas], [
            ("Início do caixa em dinheiro · abriu MARIA", "R$ 379,40"),
            ("Final do dia em dinheiro · fechou JOAO", "R$ 867,65"),
            ("PIX", "R$ 1.881,00"),
            ("Cartão de débito", "R$ 2.055,50"),
            ("Cartão de crédito", "R$ 3.376,50"),
            ("Total de vendas do dia", "R$ 8.067,50"),
        ])

    def test_o_final_nao_e_o_saldo_do_set_que_soma_pix_e_cartao(self):
        """A 1.40.4 mostrava R$ 8.180,65 num dia em que a gaveta tinha R$ 867,65."""
        self.caixa(970, datetime(2026, 9, 20, 9, 41), datetime(2026, 9, 20, 18, 10))
        self.assertNotIn("R$ 8.180,65", self.valores().values())

    def test_o_final_em_dinheiro_e_o_mesmo_da_tela_caixa(self):
        from apps.caixa import dinheiro  # noqa: PLC0415
        caixa = self.caixa(970, datetime(2026, 9, 20, 9, 41), datetime(2026, 9, 20, 18, 10),
                           entradas=Decimal("50"), pagamentos=Decimal("30"))
        final = self.bloco().linhas[1]
        self.assertEqual(final["valor"], relatorios._reais(dinheiro.do_turno(caixa).saldo))
        self.assertIn("− R$ 266,25 de sangria", final["detalhe"])
        self.assertIn("+ R$ 50,00 de entradas", final["detalhe"])
        self.assertIn("− R$ 30,00 pagos pelo caixa", final["detalhe"])

    def test_horas_de_abertura_e_fechamento(self):
        self.caixa(970, datetime(2026, 9, 20, 9, 41), datetime(2026, 9, 21, 9, 44))
        inicio, final = self.bloco().linhas[:2]
        self.assertEqual(inicio["quando"], "09:41")
        self.assertEqual(final["quando"], "21/09 09:44")
        self.assertIn("caixa 970", inicio["o_que"])

    def test_vem_logo_depois_do_resumo_do_dia(self):
        self.caixa(1, datetime(2026, 9, 20, 9, 0), datetime(2026, 9, 20, 18, 0))
        titulos = [b.titulo for b in relatorios.vendas_do_dia(self.importacao).blocos]
        self.assertEqual(titulos[:3], ["O dia de 20/09/2026", "Caixa do dia", "O que mais vendeu"])

    def test_caixa_ainda_aberto_diz_que_e_ate_a_importacao(self):
        self.caixa(2, datetime(2026, 9, 20, 9, 0), situacao=CaixaImportado.Situacao.ABERTO,
                   saldo_final=None, operador_fechamento="")
        final = self.bloco().linhas[1]
        self.assertEqual(final["quem"], "Final do dia em dinheiro · caixa ainda aberto")
        self.assertIn("até a importação", final["detalhe"])

    def test_forma_que_nao_veio_no_dia_nao_aparece(self):
        self.caixa(3, datetime(2026, 9, 20, 9, 0), datetime(2026, 9, 20, 18, 0),
                   por_forma={"AVISTA": "100", "PIX": "50"})
        self.assertNotIn("Cartão de crédito", self.valores())
        self.assertEqual(self.valores()["PIX"], "R$ 50,00")

    def test_forma_desconhecida_aparece_avisando(self):
        """Chutar que é dinheiro faria a gaveta faltar sem explicação."""
        self.caixa(4, datetime(2026, 9, 20, 9, 0), datetime(2026, 9, 20, 18, 0),
                   por_forma={"AVISTA": "100", "VOUCHER LOJA": "40"})
        rotulos = list(self.valores())
        self.assertTrue([r for r in rotulos if r.startswith("VOUCHER LOJA (forma que o sistema")])
        self.assertEqual(self.bloco().linhas[1]["valor"], "R$ 213,15")

    def test_dois_caixas_no_dia_em_ordem_de_abertura_e_inteiros(self):
        self.caixa(11, datetime(2026, 9, 20, 14, 0), datetime(2026, 9, 20, 20, 0), operador="ANA")
        self.caixa(10, datetime(2026, 9, 20, 8, 0), datetime(2026, 9, 20, 13, 0))
        self.caixa(12, datetime(2026, 9, 20, 20, 30), datetime(2026, 9, 20, 23, 0), operador="RUI")
        bloco = self.bloco()
        inicios = [linha["quem"] for linha in bloco.linhas if linha["quem"].startswith("Início")]
        self.assertEqual(inicios, ["Início do caixa em dinheiro · abriu MARIA",
                                   "Início do caixa em dinheiro · abriu ANA",
                                   "Início do caixa em dinheiro · abriu RUI"])
        self.assertEqual(len(bloco.linhas), 16)
        self.assertEqual(bloco.escondidas, 0)
        self.assertIn("3 caixas", bloco.frase)

    def test_caixa_de_outro_dia_nao_entra(self):
        self.caixa(5, datetime(2026, 9, 19, 9, 0), datetime(2026, 9, 19, 18, 0))
        bloco = self.bloco()
        self.assertEqual(bloco.linhas, [])
        self.assertIn("não tem caixa aberto em 20/09/2026", bloco.frase)

    def test_operador_em_branco_no_set_e_dito(self):
        self.caixa(6, datetime(2026, 9, 20, 9, 0), datetime(2026, 9, 20, 18, 0),
                   operador="", operador_fechamento="")
        self.assertIn("sem operador no SET", self.bloco().linhas[0]["quem"])

    def test_o_telegram_leva_quem_e_quanto(self):
        self.caixa(7, datetime(2026, 9, 20, 9, 0), datetime(2026, 9, 20, 18, 0))
        texto = telegram.texto_do_relatorio(relatorios.vendas_do_dia(self.importacao))
        self.assertIn("· Início do caixa em dinheiro · abriu MARIA — R$ 379,40", texto)
        self.assertIn("· Final do dia em dinheiro · fechou JOAO — R$ 867,65", texto)
        self.assertIn("· PIX — R$ 1.881,00", texto)

    def test_total_do_dia_soma_as_formas_de_todos_os_caixas(self):
        """Pedido de 29/10/2026: "somando tudo (dinheiro + pix + cartão de debito + cartão
        de credito)"."""
        self.caixa(1, datetime(2026, 9, 20, 8, 0), datetime(2026, 9, 20, 13, 0),
                   por_forma={"AVISTA": "100", "PIX": "50"})
        self.caixa(2, datetime(2026, 9, 20, 14, 0), datetime(2026, 9, 20, 20, 0),
                   por_forma={"CARTAO DEBITO": "30", "CARTAO CREDITO": "20"})
        total = self.bloco().linhas[-1]
        self.assertEqual(total["quem"], "Total de vendas do dia")
        self.assertEqual(total["valor"], "R$ 200,00")
        self.assertIn("2 caixas", total["o_que"])

    def test_total_que_bate_com_os_produtos_nao_explica_nada(self):
        self.caixa(1, datetime(2026, 9, 20, 8, 0), datetime(2026, 9, 20, 13, 0),
                   por_forma={"AVISTA": "100"})
        self.assertEqual(self.bloco().linhas[-1]["detalhe"], "")

    def test_desconto_no_fechamento_explica_por_que_o_total_e_menor(self):
        """A manchete soma os produtos; o caixa recebe o cupom, já com o desconto."""
        self.venda(valor="90", linhas=[("002", "CESTO", "100", "50")])
        self.caixa(1, datetime(2026, 9, 20, 8, 0), datetime(2026, 9, 20, 13, 0),
                   por_forma={"AVISTA": "190"})
        detalhe = self.bloco().linhas[-1]["detalhe"]
        self.assertIn("os produtos somam R$ 200,00", detalhe)
        self.assertIn("R$ 10,00 de desconto no fechamento", detalhe)

    def test_total_diferente_dos_cupons_manda_conferir_o_caixa(self):
        self.caixa(1, datetime(2026, 9, 20, 8, 0), datetime(2026, 9, 20, 13, 0),
                   por_forma={"PIX": "1000"})
        self.assertIn("confira na tela Caixa", self.bloco().linhas[-1]["detalhe"])
