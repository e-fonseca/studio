"""Os quatro relatórios: o que cada um diz, e que ele diz o mesmo que a tela."""

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.alertas import relatorios
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
