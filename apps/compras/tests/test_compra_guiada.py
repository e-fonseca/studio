"""A compra guiada: as perguntas que montam o pedido de um fornecedor (1.45.0).

Pedido do Edson em 02/11/2026: "formato tipo apresentação, pop up, só que com perguntas
fechadas ou abertas (...) para formatar um pedido de compra para o fornecedor assertivo".
Os testes cobram as três promessas da tela: a conta é a da Lista de compra, cada resposta
muda o pedido do jeito que a tela diz, e nada vira pedido sem o clique de quem pode.
"""

import re
from datetime import date, datetime
from decimal import Decimal

from django.http import QueryDict
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.auditoria.models import EventoAuditoria
from apps.compras import guiada, lista_de_compra
from apps.compras.models import CompraGuiada, PoliticaDeCompra, SugestaoDeCompra
from apps.contas.perfis import ADMINISTRACAO, ADMINISTRATIVO, LIDER, VENDEDOR
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.fornecedores.models import Fornecedor
from apps.importacao.models import Importacao, ProdutoImportado
from apps.pedidos.models import AnexoDoPedido, ItemDoPedido, Pedido

CORTE = date(2026, 9, 20)
FORNECEDOR = "GERMAN"


def dados(**campos):
    """Um POST de formulário, com campos que repetem (o `tipo`, a `equipe`) em lista."""
    consulta = QueryDict(mutable=True)
    for chave, valor in campos.items():
        if isinstance(valor, (list, tuple)):
            consulta.setlist(chave, [str(v) for v in valor])
        else:
            consulta[chave] = str(valor)
    return consulta


class BaseGuiada(TestCase):
    def setUp(self):
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO, situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(), data_corte=CORTE, dias_abertos_12m=360, produtos=0,
        )
        # Dez carros-chefe, o mínimo da regra: nove de outro fornecedor, com estoque cheio
        # (fora da lista), e o G1, que fatura mais que todos.
        PoliticaDeCompra.objects.update_or_create(pk=1, defaults={"carros_chefe": 10})
        for numero in range(1, 10):
            self.produto(f"O{numero}", fornecedor="OUTRO", grupo="CESTO", estoque=Decimal("5000"),
                         receita_12m=Decimal("50000"))
        self.produto("G1", estoque=Decimal("0"), vendas_12m=Decimal("360"), receita_12m=Decimal("90000"))
        self.produto("G2", estoque=Decimal("5"), vendas_12m=Decimal("180"), receita_12m=Decimal("4500"))
        self.produto("G3", grupo="ALMOFADA", estoque=Decimal("0"), vendas_12m=Decimal("120"),
                     receita_12m=Decimal("3000"))
        self.produto("G4", grupo="ALMOFADA", estoque=Decimal("4"), vendas_12m=Decimal("60"),
                     receita_12m=Decimal("1500"))
        self.produto("G5", estoque=Decimal("1"), vendas_12m=Decimal("36"), receita_12m=Decimal("900"))
        self.produto("G6", estoque=Decimal("0"), vendas_12m=Decimal("24"), vendas_90d=Decimal("0"),
                     receita_12m=Decimal("600"))
        # Estoque de um ano: não entra na lista, mas pode ser encomendado.
        self.produto("G7", estoque=Decimal("400"), vendas_12m=Decimal("12"), receita_12m=Decimal("300"))

    def produto(self, codigo, **campos):
        padrao = dict(
            importacao=self.importacao, codigo=codigo, descricao=f"PRODUTO {codigo}",
            grupo="TAPETE", fornecedor=FORNECEDOR, custo=Decimal("10"),
            preco_venda=Decimal("25"), estoque=Decimal("0"), vendas_12m=Decimal("120"),
            vendas_90d=Decimal("30"), receita_12m=Decimal("3000"),
        )
        padrao.update(campos)
        return ProdutoImportado.objects.create(**padrao)

    def compra(self, quem=None, **respostas):
        return CompraGuiada.objects.create(fornecedor=FORNECEDOR, criada_por=quem,
                                           respostas=respostas)

    def montar(self, compra, **opcoes):
        return guiada.montar(compra, self.importacao, **opcoes)

    def quantidades(self, proposta):
        return {linha.codigo: linha.quantidade for linha in proposta.linhas}


class AContaEADaListaDeCompra(BaseGuiada):
    def test_com_a_proxima_compra_na_semana_que_vem_a_conta_e_a_da_lista(self):
        """A lista de compra assume que se volta a comprar na semana que vem."""
        lista = lista_de_compra.montar(self.importacao, fornecedor=FORNECEDOR)
        da_lista = {item.codigo: item.quantidade for item in lista.fornecedores[0].itens}
        proposta = self.montar(self.compra(proxima_compra=7))
        self.assertEqual(self.quantidades(proposta), da_lista)
        self.assertEqual(proposta.total, lista.fornecedores[0].valor)

    def test_voltar_a_comprar_mais_tarde_compra_mais(self):
        semana = self.montar(self.compra(proxima_compra=7))
        dois_meses = self.montar(self.compra(proxima_compra=60))
        self.assertGreater(dois_meses.total, semana.total)
        self.assertGreaterEqual(len(dois_meses.no_pedido), len(semana.no_pedido))
        # A compra dura até a seguinte chegar: a próxima compra mais o prazo de entrega.
        self.assertEqual(dois_meses.tempo_ate_chegar, 60 + dois_meses.prazo_dias)

    def test_so_o_fornecedor_escolhido_entra(self):
        proposta = self.montar(self.compra())
        self.assertTrue(proposta.linhas)
        self.assertTrue(all(linha.codigo.startswith("G") for linha in proposta.linhas))

    def test_o_que_a_gerencia_mudou_na_lista_vale_na_compra_guiada(self):
        from apps.compras.models import AjusteDeCompra  # noqa: PLC0415

        AjusteDeCompra.objects.create(codigo="G2", a_mais=Decimal("3"), sugerida=Decimal("1"),
                                      quantidade=Decimal("4"))
        sem = self.montar(self.compra(proxima_compra=7))
        lista = lista_de_compra.montar(self.importacao, fornecedor=FORNECEDOR)
        item = next(i for i in lista.fornecedores[0].itens if i.codigo == "G2")
        self.assertEqual(sem.linha("G2").sugerida, item.quantidade)
        self.assertIn("acrescentou 3", sem.linha("G2").ajuste_da_lista)


class AsRespostasMudamOPedido(BaseGuiada):
    def test_tipo_desmarcado_sai_do_pedido_inteiro(self):
        proposta = self.montar(self.compra(tipos=["TAPETE"]))
        self.assertEqual({linha.grupo for linha in proposta.linhas}, {"TAPETE"})
        self.assertEqual({tipo.grupo for tipo in proposta.tipos}, {"TAPETE", "ALMOFADA"})

    def test_tipo_que_nao_existe_mais_vale_tudo_em_vez_de_nada(self):
        proposta = self.montar(self.compra(tipos=["SUMIU"]))
        self.assertEqual({linha.grupo for linha in proposta.linhas}, {"TAPETE", "ALMOFADA"})

    def test_so_o_que_esta_faltando(self):
        tudo = self.montar(self.compra())
        faltando = self.montar(self.compra(entra="faltando"))
        self.assertLess(len(faltando.linhas), len(tudo.linhas))
        self.assertTrue(all(linha.urgencia in (lista_de_compra.Urgencia.FALTANDO,
                                               lista_de_compra.Urgencia.ABAIXO_DO_MINIMO)
                            for linha in faltando.linhas))
        self.assertEqual(tudo.por_entra["faltando"], len(faltando.linhas))

    def test_so_os_carros_chefe(self):
        proposta = self.montar(self.compra(entra="carro_chefe"))
        self.assertEqual([linha.codigo for linha in proposta.linhas], ["G1"])

    def test_os_que_mais_vendem_ganham_pergunta_com_o_carro_chefe_na_frente(self):
        proposta = self.montar(self.compra())
        codigos = [linha.codigo for linha in proposta.principais]
        self.assertEqual(codigos[0], "G1")
        self.assertLessEqual(len(codigos), guiada.QUANTOS_PRINCIPAIS)
        receitas = [linha.receita_12m for linha in proposta.principais[1:]]
        self.assertEqual(receitas, sorted(receitas, reverse=True))

    def test_metade_dobro_nao_e_numero(self):
        base = self.montar(self.compra()).linha("G1").sugerida
        proposta = self.montar(self.compra(quantidades={"G1": "dobro", "G2": "nao", "G3": "7"}))
        self.assertEqual(proposta.linha("G1").quantidade, base * 2)
        self.assertEqual(proposta.linha("G2").quantidade, 0)
        self.assertNotIn(proposta.linha("G2"), proposta.no_pedido)
        self.assertEqual(proposta.linha("G3").quantidade, 7)
        self.assertEqual(proposta.decididas, 3)

    def test_a_metade_acompanha_a_sugestao_quando_outra_resposta_muda(self):
        """A resposta guarda a PALAVRA: mudar a próxima compra muda a metade junto."""
        curta = self.montar(self.compra(proxima_compra=7, quantidades={"G1": "metade"}))
        longa = self.montar(self.compra(proxima_compra=90, quantidades={"G1": "metade"}))
        self.assertGreater(longa.linha("G1").quantidade, curta.linha("G1").quantidade)

    def test_encomenda_soma_e_traz_produto_que_nao_estava_na_lista(self):
        base = self.montar(self.compra()).linha("G1").quantidade
        proposta = self.montar(self.compra(encomendas={"G1": "2", "G7": "3"}))
        self.assertEqual(proposta.linha("G1").quantidade, base + 2)
        g7 = proposta.linha("G7")
        self.assertEqual((g7.sugerida, g7.encomenda, g7.quantidade), (0, 3, 3))
        self.assertTrue(g7.foi_ajustada, "encomenda sai em marrom na folha: é decisão de gente")

    def test_o_limite_corta_pelo_fim_e_nao_corta_escolha_nem_encomenda(self):
        escolhas = {"quantidades": {"G6": "5"}, "encomendas": {"G7": "1"}}
        livre = self.montar(self.compra(**escolhas))
        fixo = livre.linha("G6").valor_do_pedido + livre.linha("G7").valor_do_pedido
        primeira = livre.linhas[0]
        self.assertNotIn(primeira.codigo, ("G6", "G7"))
        # Cabe o que não se corta e o primeiro da fila, e nem um centavo a mais.
        limite = fixo + primeira.valor_da_reposicao
        proposta = self.montar(self.compra(orcamento="valor", orcamento_valor=str(limite), **escolhas))
        self.assertTrue(proposta.cortadas)
        self.assertFalse(proposta.linha("G6").cortada, "a quantidade escolhida não se corta")
        self.assertEqual(proposta.linha("G7").quantidade, 1, "a encomenda não se corta")
        self.assertFalse(proposta.linhas[0].cortada, "o primeiro da fila é o último a sair")
        self.assertTrue(all(linha.cortada for linha in proposta.linhas[1:]
                            if linha.codigo not in ("G6", "G7") and linha.sugerida > 0))
        self.assertEqual(proposta.total, limite)
        self.assertEqual(proposta.total_sem_corte - proposta.total, proposta.valor_cortado)

    def test_a_encomenda_por_cima_da_sugestao_nao_gasta_a_sugestao_duas_vezes(self):
        """G1 tem sugestão e encomenda: o limite exato das duas tem que caber sem corte."""
        livre = self.montar(self.compra(encomendas={"G1": "2"}))
        g1 = livre.linha("G1")
        self.assertGreater(g1.sugerida, 0)
        limite = livre.total
        proposta = self.montar(self.compra(encomendas={"G1": "2"}, orcamento="valor",
                                           orcamento_valor=str(limite)))
        self.assertEqual(proposta.cortadas, [], "o pedido inteiro cabe no limite do tamanho dele")
        self.assertEqual(proposta.total, limite)

    def test_o_teto_do_mes_desconta_os_pedidos_daqui_que_nao_chegaram(self):
        antes = guiada.teto_do_mes(self.importacao)
        pedido = Pedido.objects.create(numero=1, fornecedor=FORNECEDOR,
                                       criado_em=timezone.make_aware(datetime(2026, 9, 10, 10)))
        ItemDoPedido.objects.create(pedido=pedido, codigo="G1", descricao="PRODUTO G1",
                                    quantidade=Decimal("10"), custo=Decimal("10"),
                                    valor=Decimal("100"))
        recebido = Pedido.objects.create(numero=2, fornecedor=FORNECEDOR,
                                         situacao=Pedido.Situacao.RECEBIDO,
                                         criado_em=timezone.make_aware(datetime(2026, 9, 11, 10)))
        ItemDoPedido.objects.create(pedido=recebido, codigo="G2", descricao="PRODUTO G2",
                                    quantidade=Decimal("1"), custo=Decimal("10"),
                                    valor=Decimal("999"))
        depois = guiada.teto_do_mes(self.importacao)
        self.assertEqual(depois.quantos_pedidos, 1, "o recebido já está no SET")
        self.assertEqual(antes.sobra - depois.sobra, Decimal("100"))


class AsPerguntas(BaseGuiada):
    def test_sem_prazo_na_ficha_a_primeira_pergunta_e_o_prazo(self):
        compra = self.compra()
        proposta = self.montar(compra)
        self.assertTrue(proposta.prazo_assumido)
        self.assertEqual(guiada.passos(compra, proposta)[0], guiada.PRAZO)
        self.assertEqual(guiada.passos(compra, proposta)[-1], guiada.REVISAO)

    def test_com_prazo_na_ficha_a_pergunta_nao_aparece(self):
        Fornecedor.objects.create(nome=FORNECEDOR, prazo_dias=20)
        compra = self.compra()
        proposta = self.montar(compra)
        self.assertEqual((proposta.prazo_dias, proposta.prazo_origem), (20, "ficha"))
        self.assertNotIn(guiada.PRAZO, guiada.passos(compra, proposta))

    def test_o_prazo_respondido_vai_para_a_ficha_de_quem_cuida_dos_fornecedores(self):
        quem = usuario("loja", ADMINISTRATIVO)
        compra = self.compra(quem)
        recado = guiada.salvar_resposta(compra, guiada.PRAZO, dados(prazo="30"), quem,
                                        self.importacao)
        self.assertIn("ficha", recado)
        self.assertEqual(Fornecedor.objects.get(nome=FORNECEDOR).prazo_dias, 30)
        evento = EventoAuditoria.objects.get(acao="fornecedor.prazo_alterado")
        self.assertEqual(evento.motivo, "informado na compra guiada")
        # Gravado na ficha, a pergunta não volta, nem nesta compra nem na próxima.
        proposta = self.montar(compra)
        self.assertEqual(proposta.prazo_dias, 30)

    def test_quem_nao_cuida_dos_fornecedores_responde_so_para_esta_compra(self):
        quem = usuario("cliente", VENDEDOR)
        compra = self.compra(quem)
        guiada.salvar_resposta(compra, guiada.PRAZO, dados(prazo="outro", prazo_outro="12"),
                               quem, self.importacao)
        self.assertFalse(Fornecedor.objects.filter(nome=FORNECEDOR, prazo_dias__isnull=False).exists())
        self.assertEqual(self.montar(compra).prazo_dias, 12)

    def test_cada_prazo_mostra_o_pedido_que_da(self):
        compra = self.compra()
        opcoes = guiada.opcoes_de_prazo(compra, self.importacao)
        self.assertEqual([opcao.chave for opcao in opcoes], [dias for dias, _ in guiada.PRAZOS])
        self.assertLess(opcoes[0].valor, opcoes[-1].valor, "prazo maior, pedido maior")
        compra.refresh_from_db()
        self.assertNotIn("prazo", compra.respostas, "a conta das opções não grava nada")

    def test_nao_sei_nao_inventa_prazo(self):
        quem = usuario("gerencia", ADMINISTRACAO)
        compra = self.compra(quem)
        guiada.salvar_resposta(compra, guiada.PRAZO, dados(prazo="nao_sei"), quem, self.importacao)
        self.assertFalse(Fornecedor.objects.exclude(prazo_dias=None).exists())
        proposta = self.montar(compra)
        self.assertTrue(proposta.prazo_assumido)
        self.assertEqual(guiada.onde_parou(compra, proposta), guiada.PROXIMA)

    def test_resposta_que_nao_serve_volta_com_a_frase(self):
        quem = usuario("gerencia", ADMINISTRACAO)
        compra = self.compra(quem)
        for passo, campos in ((guiada.PRAZO, dados(prazo="outro", prazo_outro="")),
                              (guiada.PROXIMA, dados(proxima_compra="11")),
                              (guiada.TIPOS, dados(entra="tudo")),
                              (f"{guiada.PRODUTO}1", dados(quantidade="outro", quantidade_outro="-2")),
                              (guiada.ORCAMENTO, dados(orcamento="valor", orcamento_valor="dois mil"))):
            with self.subTest(passo=passo):
                with self.assertRaises(guiada.RespostaInvalida):
                    guiada.salvar_resposta(compra, passo, campos, quem, self.importacao)

    def test_a_pergunta_do_produto_vale_pelo_produto_e_nao_pela_posicao(self):
        """Mudar os tipos muda quem são os que mais vendem: o novo segundo é pergunta nova."""
        compra = self.compra(quantidades={"G2": "sugerida"}, respondidos=["produto-2"])
        proposta = self.montar(compra)
        self.assertEqual(proposta.principais[1].codigo, "G2")
        self.assertTrue(guiada.respondida(compra, proposta, "produto-2"))
        compra.respostas["tipos"] = ["ALMOFADA"]
        proposta = self.montar(compra)
        self.assertFalse(guiada.respondida(compra, proposta, "produto-2"))

    def test_a_conferencia_so_grava_o_que_a_pessoa_mexeu(self):
        quem = usuario("gerencia", ADMINISTRACAO)
        compra = self.compra(quem)
        proposta = self.montar(compra)
        g1, g2 = proposta.linha("G1"), proposta.linha("G2")
        guiada.salvar_resposta(compra, guiada.REVISAO, dados(**{
            "q-G1": g1.quantidade, "era-G1": g1.quantidade,
            "q-G2": "9", "era-G2": g2.quantidade, "recado": "entregar na sexta",
        }), quem, self.importacao)
        self.assertEqual(compra.respostas["quantidades"], {"G2": "9"})
        self.assertEqual(compra.respostas["recado"], "entregar na sexta")

    def test_na_conferencia_menos_que_a_encomenda_diminui_a_encomenda(self):
        quem = usuario("gerencia", ADMINISTRACAO)
        compra = self.compra(quem, encomendas={"G7": "3"})
        guiada.salvar_resposta(compra, guiada.REVISAO, dados(**{"q-G7": "1", "era-G7": "3"}),
                               quem, self.importacao)
        self.assertEqual(self.montar(compra).linha("G7").quantidade, 1)


class OPedido(BaseGuiada):
    def gerar(self, quem, **respostas):
        compra = self.compra(quem, **respostas)
        proposta = self.montar(compra)
        return compra, proposta, guiada.gerar_pedido(compra, proposta, quem, emitido_por="Teste")

    def test_o_pedido_da_gerencia_nasce_valendo_com_a_folha_anexada(self):
        quem = usuario("gerencia", ADMINISTRACAO)
        compra, proposta, pedido = self.gerar(quem, recado="mandar o XML")
        self.assertEqual(pedido.situacao, Pedido.Situacao.ABERTO)
        self.assertEqual(pedido.observacao, "mandar o XML")
        self.assertEqual(pedido.itens.count(), len(proposta.no_pedido))
        self.assertEqual(pedido.valor_total, proposta.total)
        self.assertTrue(AnexoDoPedido.objects.filter(pedido=pedido, tipo=AnexoDoPedido.Tipo.PEDIDO).exists())
        compra.refresh_from_db()
        self.assertEqual(compra.situacao, CompraGuiada.Situacao.CONCLUIDA)
        self.assertEqual(compra.pedido_numero, pedido.numero)
        self.assertIn("Próxima compra em 30 dias", compra.resumo)
        self.assertTrue(EventoAuditoria.objects.filter(acao="compras.compra_guiada_concluida").exists())

    def test_o_pedido_da_lider_espera_a_gerencia(self):
        quem = usuario("cassia", LIDER)
        _, _, pedido = self.gerar(quem)
        self.assertEqual(pedido.situacao, Pedido.Situacao.AGUARDANDO)
        anexo = AnexoDoPedido.objects.get(pedido=pedido)
        self.assertIn("ESPERANDO-APROVACAO", anexo.nome_original.upper())

    def test_gerar_duas_vezes_nao_faz_dois_pedidos(self):
        quem = usuario("gerencia", ADMINISTRACAO)
        compra, proposta, _ = self.gerar(quem)
        self.assertIsNone(guiada.gerar_pedido(compra, proposta, quem))
        self.assertEqual(Pedido.objects.count(), 1)

    def test_pedido_sem_nada_nao_e_gravado(self):
        quem = usuario("gerencia", ADMINISTRACAO)
        zerado = {codigo: "nao" for codigo in ("G1", "G2", "G3", "G4", "G5", "G6")}
        with self.assertRaises(guiada.RespostaInvalida):
            self.gerar(quem, quantidades=zerado)
        self.assertFalse(Pedido.objects.exists())

    def test_a_sugestao_da_equipe_entra_e_ganha_a_resposta(self):
        quem = usuario("gerencia", ADMINISTRACAO)
        sugestao = SugestaoDeCompra.objects.create(produto="PRODUTO G7", codigo="G7",
                                                   quantidade=Decimal("2"))
        self.assertIn(sugestao, guiada.sugestoes_da_equipe(self.compra(), self.importacao))
        _, proposta, pedido = self.gerar(quem, equipe={str(sugestao.pk): "2"})
        self.assertEqual(proposta.linha("G7").encomenda, 2)
        sugestao.refresh_from_db()
        self.assertEqual(sugestao.situacao, SugestaoDeCompra.Situacao.COMPRADA)
        self.assertIn(str(pedido.numero), sugestao.resposta)


class AsTelas(BaseGuiada):
    def entrar(self, nome, perfil):
        quem = usuario(nome, perfil)
        self.client.login(username=nome, password=SENHA_TESTE)
        return quem

    def test_o_vendedor_nao_abre(self):
        self.entrar("balcao", VENDEDOR)
        self.assertEqual(self.client.get(reverse("compras:guiada")).status_code, 403)

    def test_a_compra_de_outra_pessoa_nao_abre(self):
        dona = usuario("cassia", LIDER)
        compra = self.compra(dona)
        self.entrar("gerencia", ADMINISTRACAO)
        endereco = reverse("compras:guiada_passo", args=[compra.pk, guiada.PROXIMA])
        self.assertEqual(self.client.get(endereco).status_code, 404)
        self.assertEqual(self.client.get(reverse("compras:guiada_folha", args=[compra.pk])).status_code, 404)

    def test_a_abertura_le_a_loja_e_oferece_os_fornecedores(self):
        self.entrar("gerencia", ADMINISTRACAO)
        pagina = self.client.get(reverse("compras:guiada"))
        self.assertContains(pagina, "De qual fornecedor é esta compra?")
        self.assertContains(pagina, f'value="{FORNECEDOR}"')
        self.assertContains(pagina, "Parado sem vender no ano")
        self.assertContains(pagina, "Os que mais vendem e estão acabando")

    def test_fornecedor_que_nao_existe_volta_para_a_abertura(self):
        self.entrar("gerencia", ADMINISTRACAO)
        resposta = self.client.post(reverse("compras:guiada_comecar"),
                                    {"fornecedor": "outro", "outro_fornecedor": "NINGUEM"})
        self.assertRedirects(resposta, reverse("compras:guiada") + "?fornecedor=NINGUEM")
        self.assertFalse(CompraGuiada.objects.exists())

    def test_o_caminho_inteiro_ate_o_pedido(self):
        quem = self.entrar("gerencia", ADMINISTRACAO)
        resposta = self.client.post(reverse("compras:guiada_comecar"), {"fornecedor": FORNECEDOR})
        compra = CompraGuiada.objects.get(criada_por=quem)
        endereco = lambda passo: reverse("compras:guiada_passo", args=[compra.pk, passo])  # noqa: E731
        self.assertRedirects(resposta, endereco(guiada.PRAZO))

        respostas = {
            guiada.PRAZO: {"prazo": "15"},
            guiada.PROXIMA: {"proxima_compra": "30"},
            guiada.TIPOS: {"tipo": ["TAPETE", "ALMOFADA"], "entra": "tudo"},
            guiada.VENDA: {"media": ""},
            guiada.ENCOMENDAS: {"acao": "continuar"},
            guiada.ORCAMENTO: {"orcamento": "livre"},
        }
        passo = guiada.PRAZO
        vistos = []
        while passo != guiada.REVISAO:
            pagina = self.client.get(endereco(passo))
            self.assertEqual(pagina.status_code, 200, passo)
            self.assertContains(pagina, "Pedido agora:")
            campos = respostas.get(passo, {"quantidade": "sugerida"})
            resposta = self.client.post(endereco(passo), campos)
            self.assertEqual(resposta.status_code, 302, f"{passo}: {resposta.content[:300]!r}")
            vistos.append(passo)
            passo = resposta["Location"].rstrip("/").rsplit("/", 1)[-1]
        self.assertEqual(vistos[:5], [guiada.PRAZO, guiada.PROXIMA, guiada.TIPOS, guiada.VENDA,
                                      f"{guiada.PRODUTO}1"])
        self.assertEqual(vistos[-2:], [guiada.ENCOMENDAS, guiada.ORCAMENTO])

        pagina = self.client.get(endereco(guiada.REVISAO))
        self.assertContains(pagina, "Gerar o pedido")
        self.assertContains(pagina, 'name="q-G1"')
        resposta = self.client.post(endereco(guiada.REVISAO), {"acao": "gerar", "recado": "ok"})
        self.assertRedirects(resposta, reverse("compras:guiada_pronto", args=[compra.pk]))
        pedido = Pedido.objects.get()
        self.assertContains(self.client.get(resposta["Location"]), f"Pedido {pedido.numero} guardado")
        # Depois de virar pedido, qualquer pergunta leva ao fim, e não a outro pedido.
        self.assertRedirects(self.client.get(endereco(guiada.ORCAMENTO)),
                             reverse("compras:guiada_pronto", args=[compra.pk]))
        self.assertEqual(Pedido.objects.count(), 1)

    def test_resposta_invalida_volta_na_mesma_pergunta_com_o_recado(self):
        quem = self.entrar("gerencia", ADMINISTRACAO)
        compra = self.compra(quem)
        endereco = reverse("compras:guiada_passo", args=[compra.pk, f"{guiada.PRODUTO}1"])
        pagina = self.client.post(endereco, {"quantidade": "outro", "quantidade_outro": ""})
        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, "Escreva quantas unidades comprar.")
        self.assertContains(pagina, 'value="outro" checked')

    def test_quem_nao_gera_pedido_monta_e_baixa_a_folha(self):
        quem = self.entrar("loja", ADMINISTRATIVO)
        compra = self.compra(quem)
        pagina = self.client.get(reverse("compras:guiada_passo", args=[compra.pk, guiada.REVISAO]))
        self.assertNotContains(pagina, 'value="gerar"')
        folha = self.client.get(reverse("compras:guiada_folha", args=[compra.pk]))
        self.assertEqual(folha["Content-Type"], "application/pdf")
        self.assertIn("ESPERANDO-APROVACAO", folha["Content-Disposition"].upper())
        resposta = self.client.post(reverse("compras:guiada_passo", args=[compra.pk, guiada.REVISAO]),
                                    {"acao": "gerar"})
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(Pedido.objects.exists())
        self.assertTrue(EventoAuditoria.objects.filter(acao="dados.arquivo_baixado").exists())

    def test_a_folha_de_previa_nao_grava_pedido(self):
        quem = self.entrar("gerencia", ADMINISTRACAO)
        compra = self.compra(quem)
        folha = self.client.get(reverse("compras:guiada_folha", args=[compra.pk]))
        self.assertEqual(folha.status_code, 200)
        self.assertNotIn("ESPERANDO-APROVACAO", folha["Content-Disposition"].upper())
        self.assertFalse(Pedido.objects.exists())

    def test_pergunta_que_deixou_de_existir_leva_a_que_falta(self):
        quem = self.entrar("gerencia", ADMINISTRACAO)
        compra = self.compra(quem)
        resposta = self.client.get(reverse("compras:guiada_passo", args=[compra.pk, "produto-9"]))
        self.assertRedirects(resposta, reverse("compras:guiada_passo", args=[compra.pk, guiada.PRAZO]))

    def test_deixar_de_lado_nao_apaga_e_tira_da_abertura(self):
        quem = self.entrar("gerencia", ADMINISTRACAO)
        compra = self.compra(quem, proxima_compra=15)
        self.assertContains(self.client.get(reverse("compras:guiada")), "Você parou no meio")
        self.client.post(reverse("compras:guiada_deixar", args=[compra.pk]))
        compra.refresh_from_db()
        self.assertEqual(compra.situacao, CompraGuiada.Situacao.DEIXADA)
        self.assertEqual(compra.respostas["proxima_compra"], 15)
        self.assertNotContains(self.client.get(reverse("compras:guiada")), "Você parou no meio")

    def test_comecar_de_novo_o_mesmo_fornecedor_continua_a_que_estava_aberta(self):
        quem = self.entrar("gerencia", ADMINISTRACAO)
        self.client.post(reverse("compras:guiada_comecar"), {"fornecedor": FORNECEDOR})
        self.client.post(reverse("compras:guiada_comecar"), {"outro_fornecedor": FORNECEDOR.lower()})
        self.assertEqual(CompraGuiada.objects.filter(criada_por=quem).count(), 1)

    def test_por_e_tirar_encomenda_pela_tela_fica_gravado(self):
        quem = self.entrar("gerencia", ADMINISTRACAO)
        compra = self.compra(quem)
        endereco = reverse("compras:guiada_passo", args=[compra.pk, guiada.ENCOMENDAS])
        procura = self.client.get(endereco, {"procurar": "G7"})
        self.assertContains(procura, "Pôr no pedido")
        resposta = self.client.post(endereco, {"acao": "adicionar", "codigo": "G7", "unidades": "2"})
        self.assertRedirects(resposta, endereco, fetch_redirect_response=False)
        compra.refresh_from_db()
        self.assertEqual(compra.respostas["encomendas"], {"G7": "2"})
        pagina = self.client.get(endereco)
        self.assertContains(pagina, "Encomenda posta no pedido.")
        self.assertNotContains(pagina, "Nenhuma encomenda neste pedido.")
        self.client.post(endereco, {"acao": "tirar", "codigo": "G7"})
        compra.refresh_from_db()
        self.assertEqual(compra.respostas["encomendas"], {})

    def test_salvar_a_conferencia_fica_nela_e_grava_so_o_mexido(self):
        quem = self.entrar("gerencia", ADMINISTRACAO)
        compra = self.compra(quem)
        endereco = reverse("compras:guiada_passo", args=[compra.pk, guiada.REVISAO])
        g1 = str(self.montar(compra).linha("G1").quantidade.normalize())
        resposta = self.client.post(endereco, {"acao": "salvar", "q-G2": "9", "era-G2": "1",
                                               "q-G1": g1, "era-G1": g1, "q-G4": "", "era-G4": "2",
                                               "recado": "Entregar até sexta."})
        self.assertRedirects(resposta, endereco, fetch_redirect_response=False)
        compra.refresh_from_db()
        self.assertEqual(compra.respostas["quantidades"], {"G2": "9", "G4": "0"},
                         "o G1 voltou igual e segue a conta; o G4 apagado é zero")
        self.assertEqual(compra.respostas["recado"], "Entregar até sexta.")
        self.assertContains(self.client.get(endereco), "Mudanças guardadas.")
        self.assertFalse(Pedido.objects.exists())

    def test_mudar_uma_resposta_pela_conferencia_volta_para_ela(self):
        quem = self.entrar("gerencia", ADMINISTRACAO)
        compra = self.compra(quem)
        revisao = reverse("compras:guiada_passo", args=[compra.pk, guiada.REVISAO])
        venda = reverse("compras:guiada_passo", args=[compra.pk, guiada.VENDA])
        self.assertContains(self.client.get(revisao), f"{venda}?de=revisao")
        resposta = self.client.post(venda, {"media": "90", "de": "revisao"})
        self.assertRedirects(resposta, revisao, fetch_redirect_response=False)
        compra.refresh_from_db()
        self.assertEqual(compra.respostas["media"], "90")

    def test_continuar_leva_a_pergunta_que_falta(self):
        quem = self.entrar("gerencia", ADMINISTRACAO)
        compra = self.compra(quem)
        resposta = self.client.get(reverse("compras:guiada_continuar", args=[compra.pk]))
        self.assertRedirects(resposta, reverse("compras:guiada_passo", args=[compra.pk, guiada.PRAZO]),
                             fetch_redirect_response=False)

    def test_o_pronto_da_lider_diz_que_espera_a_gerencia(self):
        quem = self.entrar("cassia", LIDER)
        compra = self.compra(quem)
        revisao = reverse("compras:guiada_passo", args=[compra.pk, guiada.REVISAO])
        self.assertContains(self.client.get(revisao), "nasce esperando a aprovação da gerência")
        resposta = self.client.post(revisao, {"acao": "gerar"})
        self.assertRedirects(resposta, reverse("compras:guiada_pronto", args=[compra.pk]),
                             fetch_redirect_response=False)
        self.assertContains(self.client.get(resposta["Location"]), "esperando a gerência")

    def test_a_conferencia_pergunta_pelo_que_dura_mais_de_um_ano(self):
        """O mínimo do SET em 10 para um produto que vende 1 por ano: 10 anos parado."""
        self.produto("M1", vendas_12m=Decimal("1"), vendas_90d=Decimal("0"), receita_12m=Decimal("25"),
                     estoque_minimo_set=Decimal("10"))
        self.produto("M2", vendas_12m=Decimal("1"), vendas_90d=Decimal("0"), receita_12m=Decimal("25"),
                     estoque_minimo_set=Decimal("10"))
        quem = self.entrar("gerencia", ADMINISTRACAO)
        compra = self.compra(quem, encomendas={"M2": "1"})
        proposta = self.montar(compra)
        self.assertEqual([linha.codigo for linha in proposta.longe], ["M1"],
                         "a linha com encomenda é do cliente: não entra na pergunta")
        revisao = reverse("compras:guiada_passo", args=[compra.pk, guiada.REVISAO])
        self.assertContains(self.client.get(revisao), "dura mais de um ano na prateleira")
        resposta = self.client.post(revisao, {"acao": "tirar_longe", "recado": "Mandar o XML."})
        self.assertRedirects(resposta, revisao, fetch_redirect_response=False)
        compra.refresh_from_db()
        self.assertEqual(compra.respostas["quantidades"], {"M1": "0"})
        self.assertEqual(compra.respostas["recado"], "Mandar o XML.", "a tabela e o recado ficam gravados")
        pagina = self.client.get(revisao)
        self.assertContains(pagina, "Saiu do pedido 1 produto que durava mais de um ano")
        self.assertNotContains(pagina, "Mudanças guardadas.")
        self.assertEqual(self.montar(compra).longe, [])

    def _primeiro_botao(self, pagina, formulario):
        trecho = pagina[pagina.index(f'id="{formulario}"'):]
        return re.search(r'<button type="submit"[^>]*>', trecho).group(0)

    def test_o_enter_na_conferencia_so_salva(self):
        """O Enter num campo aperta o primeiro botão do formulário: ele não pode gerar o pedido."""
        quem = self.entrar("gerencia", ADMINISTRACAO)
        compra = self.compra(quem)
        pagina = self.client.get(reverse("compras:guiada_passo", args=[compra.pk, guiada.REVISAO]))
        self.assertContains(pagina, 'value="gerar"')
        self.assertIn('value="salvar"', self._primeiro_botao(pagina.content.decode(), "guiada-respostas"))

    def test_o_enter_no_outro_fornecedor_nao_compra_do_carro_chefe(self):
        """Os botões "Comprar de" têm formulário próprio, fora do Enter da pergunta."""
        self.entrar("gerencia", ADMINISTRACAO)
        pagina = self.client.get(reverse("compras:guiada")).content.decode()
        self.assertIn('name="direto"', pagina)
        self.assertNotIn('form="guiada-comecar"', pagina)
        self.assertNotIn("direto", self._primeiro_botao(pagina, "guiada-comecar"))

    def test_a_lista_de_compra_leva_a_compra_guiada(self):
        self.entrar("gerencia", ADMINISTRACAO)
        self.assertContains(self.client.get(reverse("compras:lista")),
                            f'class="guiada-convite" href="{reverse("compras:guiada")}"')
