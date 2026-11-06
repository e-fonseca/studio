"""Menu por assunto, início encaminhando para o Dashboard e a versão só no topo."""

from django.test import TestCase
from django.urls import reverse

from apps.contas.perfis import ADMINISTRACAO, ADMINISTRATIVO, VENDEDOR
from apps.core import menu
from apps.core.fabricas import SENHA_TESTE, usuario


class TestInicioAbreNoDashboard(TestCase):
    def test_gerencia_cai_no_dashboard(self):
        """Pedido de 31/10/2026: "logo quando fazer login quero que abra o Dashboard"."""
        usuario("edson", ADMINISTRACAO)
        self.client.login(username="edson", password=SENHA_TESTE)
        self.assertRedirects(self.client.get(reverse("core:inicio")), reverse("painel:dashboard"))

    def test_vendedor_cai_na_consulta_que_e_a_tela_dele(self):
        """Ele não tem painel: mandar para lá daria 403 na cara de quem acabou de entrar."""
        usuario("balcao", VENDEDOR)
        self.client.login(username="balcao", password=SENHA_TESTE)
        self.assertRedirects(self.client.get(reverse("core:inicio")),
                             reverse("importacao:consulta"))

    def test_quem_nao_tem_perfil_recebe_recado_e_nao_erro(self):
        usuario("novato")
        self.client.login(username="novato", password=SENHA_TESTE)
        resposta = self.client.get(reverse("core:inicio"))
        self.assertContains(resposta, "ainda não foi liberado")

    def test_login_entra_direto_no_dashboard(self):
        usuario("edson", ADMINISTRACAO)
        resposta = self.client.post(reverse("contas:entrar"),
                                    {"username": "edson", "password": SENHA_TESTE}, follow=True)
        self.assertEqual(resposta.resolver_match.view_name, "painel:dashboard")
        # E a Visão geral logo ao lado, no mesmo menu de cima.
        topo = resposta.content.decode()
        topo = topo[:topo.index("</header>")]
        self.assertLess(topo.index(">Dashboard<"), topo.index(">Visão geral<"))


class TestMenuPorAssunto(TestCase):
    """O pedido de 19/10/2026: poucas entradas no topo, e nunca as vinte e sete juntas.

    Eram seis; o Dashboard virou a sétima, e a primeira, em 31/10/2026."""

    def setUp(self):
        usuario("edson", ADMINISTRACAO)
        self.client.login(username="edson", password=SENHA_TESTE)

    def test_o_topo_tem_sete_entradas_com_o_dashboard_na_frente(self):
        self.assertEqual([grupo.rotulo for grupo in menu.GRUPOS],
                         ["Dashboard", "Visão geral", "Compras", "Vendas", "Estoque", "Contas a pagar",
                          "Sistema"])

    def test_nenhuma_tela_aparece_em_dois_assuntos(self):
        vistas = [tela.rota for tela in menu.telas()]
        self.assertEqual(len(vistas), len(set(vistas)), "tela repetida em dois assuntos")

    def test_a_segunda_fileira_traz_so_o_assunto_aberto(self):
        """O ganho inteiro do pedido: na tela de compra não se lê Auditoria nem Clientes."""
        corpo = self.client.get(reverse("compras:lista")).content.decode()
        topo = corpo[:corpo.index("</header>")]
        self.assertIn("Lista de compra", topo)
        self.assertIn("Fornecedores", topo)
        self.assertNotIn(reverse("auditoria:lista"), topo)
        self.assertNotIn(reverse("clientes:lista"), topo)
        self.assertNotIn(reverse("caixa:lista"), topo)

    def test_o_assunto_aberto_fica_aceso_na_primeira_fileira(self):
        corpo = self.client.get(reverse("financeiro:despesas")).content.decode()
        primeira = corpo[corpo.index("menu-principal"):corpo.index("menu-apoio")]
        aceso = primeira[:primeira.index('aria-current="page"')].rsplit("<a ", 1)[-1]
        self.assertIn(">Contas a pagar<", primeira)
        self.assertIn(reverse("financeiro:contas_a_pagar"), aceso)

    def test_a_tela_aberta_fica_marcada_mesmo_vindo_de_uma_tela_irma(self):
        """Abrir Despesas tem que acender Financeiro, senão a pessoa perde onde está."""
        corpo = self.client.get(reverse("financeiro:despesas")).content.decode()
        segunda = corpo[corpo.index("menu-apoio"):corpo.index("</header>")]
        marcado = segunda[:segunda.index('aria-current="page"')]
        self.assertIn(reverse("financeiro:contas_a_pagar"), marcado.rsplit("<a ", 1)[-1])

    def test_clicar_no_assunto_cai_na_tela_que_decide(self):
        """"Compras" leva direto à Lista de compra, não a uma página de índice."""
        compras = menu.grupo_de("compras:lista")
        self.assertEqual(compras.telas[0].rota, "compras:lista")
        self.assertEqual(compras.endereco, reverse("compras:lista"))

    def test_vendedor_ve_um_assunto_so_e_nenhuma_segunda_fileira(self):
        self.client.logout()
        usuario("balcao", VENDEDOR)
        self.client.login(username="balcao", password=SENHA_TESTE)
        pagina = self.client.get(reverse("importacao:consulta"))
        self.assertNotContains(pagina, "menu-apoio")
        self.assertNotContains(pagina, reverse("auditoria:lista"))

    def test_assunto_sem_nenhuma_tela_aberta_some_do_topo(self):
        """Mostrar "Contas a pagar" a quem não abre nada de dinheiro é oferecer porta trancada."""
        pessoa = usuario("balcao2", VENDEDOR)
        chaves = [grupo.chave for grupo in menu.grupos_de(pessoa)]
        self.assertEqual(chaves, ["estoque"])

    def test_toda_rota_do_menu_existe_de_verdade(self):
        """Rota escrita errada no menu só apareceria quando alguém abrisse a tela."""
        for item in menu.telas() + menu.FORA_DO_MENU:
            self.assertTrue(item.endereco.startswith("/sistema/"), item.rota)

    def test_toda_rota_irma_existe_de_verdade(self):
        """Rota irmã escrita errada só apareceria quando alguém abrisse aquela tela.

        A rota pode pedir nenhum, um ou dois números no endereço (um anexo mora dentro de
        um pedido): basta que UMA das formas exista.
        """
        from django.urls import NoReverseMatch, reverse as resolver

        for item in menu.telas():
            for irma in item.irmas:
                for argumentos in ([1], [1, 2], []):
                    try:
                        resolver(irma, args=argumentos)
                        break
                    except NoReverseMatch:
                        continue
                else:
                    self.fail(f"rota irmã inexistente no menu: {irma}")

    def test_o_administrativo_nao_recebe_tela_que_nao_pode_abrir(self):
        self.client.logout()
        usuario("ana", ADMINISTRATIVO)
        self.client.login(username="ana", password=SENHA_TESTE)
        pagina = self.client.get(reverse("financeiro:contas_a_pagar"))
        self.assertNotContains(pagina, reverse("contas:usuarios"))

    def test_as_setas_do_pe_andam_na_ordem_do_menu(self):
        """A seta de "próxima" tem que seguir o assunto, não saltar para outro."""
        corpo = self.client.get(reverse("compras:lista")).content.decode()
        navegacao = corpo[corpo.index('class="navegacao-telas"'):]
        # Depois da Lista vem a Compra guiada desde a 1.45.0 (pedido de 02/11/2026).
        self.assertIn(reverse("compras:guiada"), navegacao)


class TestTelaQueEhRecursoDeOutra(TestCase):
    """Tela que virou recurso de outra sai do menu e ganha a volta para a origem.

    Pedido do Edson em 14/10/2026: tirar do menu "Comparar com o ano passado" e "Tempo e
    venda", porque cada uma passou a abrir dentro da tela em que a decisão é tomada. A
    ROTA continua existindo — é lá que ficam a tabela produto a produto, o arquivo e o
    campo de anotar o dia —, então o que o teste cobra é que ela não esteja no menu e que
    quem abrir tenha caminho de volta.
    """

    def setUp(self):
        usuario("edson", ADMINISTRACAO)
        self.client.login(username="edson", password=SENHA_TESTE)

    def test_as_duas_ficam_fora_das_fileiras_do_topo(self):
        corpo = self.client.get(reverse("painel:geral")).content.decode()
        menus = corpo[:corpo.index("</header>")]
        self.assertNotIn(reverse("compras:comparar"), menus)
        self.assertNotIn(reverse("tempo:painel"), menus)
        self.assertNotIn("Comparar com o ano passado", menus)

    def test_a_rota_continua_abrindo(self):
        """Tirar do menu não é apagar a tela: é lá que está a tabela inteira."""
        self.assertEqual(self.client.get(reverse("compras:comparar")).status_code, 200)
        self.assertEqual(self.client.get(reverse("tempo:painel")).status_code, 200)

    def test_o_assunto_de_origem_continua_aceso_no_recurso(self):
        """Senão o topo apagaria justamente quando a pessoa foi mais fundo no assunto."""
        corpo = self.client.get(reverse("compras:comparar")).content.decode()
        primeira = corpo[corpo.index("menu-principal"):corpo.index("</header>")]
        aceso = primeira[:primeira.index('aria-current="page"')].rsplit("<a ", 1)[-1]
        self.assertIn(reverse("compras:lista"), aceso)

    def test_a_seta_de_anterior_volta_para_a_tela_de_origem(self):
        corpo = self.client.get(reverse("compras:comparar")).content.decode()
        navegacao = corpo[corpo.index('class="navegacao-telas"'):]
        self.assertIn(reverse("compras:lista"), navegacao)
        self.assertIn("Lista de compra", navegacao)
        corpo = self.client.get(reverse("tempo:painel")).content.decode()
        navegacao = corpo[corpo.index('class="navegacao-telas"'):]
        self.assertIn(reverse("painel:geral"), navegacao)

    def test_nao_ha_proxima_tela_a_partir_de_um_recurso(self):
        """Ela não é parada do caminho: quem entrou volta de onde veio."""
        corpo = self.client.get(reverse("tempo:painel")).content.decode()
        navegacao = corpo[corpo.index('class="navegacao-telas"'):]
        self.assertNotIn("navegacao-proxima", navegacao)

    def test_o_vaivem_das_outras_telas_nao_passa_por_elas(self):
        """Senão a seta de "próxima" viraria o menu que o Edson acabou de tirar."""
        corpo = self.client.get(reverse("core:versoes")).content.decode()
        navegacao = corpo[corpo.index('class="navegacao-telas"'):]
        self.assertNotIn(reverse("compras:comparar"), navegacao)
        self.assertNotIn(reverse("tempo:painel"), navegacao)

    def test_toda_tela_de_dentro_aponta_para_uma_tela_que_existe(self):
        """`dentro_de` escrito errado deixaria a tela sem caminho de volta, em silêncio."""
        dentro = [item for item in menu.telas() + menu.FORA_DO_MENU if item.dentro_de]
        self.assertTrue(dentro, "nenhuma tela marcada como recurso de outra")
        for item in dentro:
            origem = menu.de_rota(item.dentro_de)
            self.assertIsNotNone(origem, item.rota)
            self.assertFalse(origem.dentro_de, f"{item.rota} aponta para outro recurso")
            self.assertIsNotNone(menu.grupo_de(item.dentro_de),
                                 f"{item.rota} aponta para tela fora de qualquer assunto")


class TestVersaoSoNoTopo(TestCase):
    def test_o_rodape_nao_tem_mais_link_para_versoes(self):
        usuario("edson", ADMINISTRACAO)
        self.client.login(username="edson", password=SENHA_TESTE)
        corpo = self.client.get(reverse("painel:geral")).content.decode()
        rodape = corpo[corpo.index("<footer"):]
        self.assertNotIn(reverse("core:versoes"), rodape)
        self.assertIn(reverse("core:versoes"), corpo[:corpo.index("<footer")])


class ComprasComCincoTelas(TestCase):
    """Escolha do Edson em 22/10/2026: "Quatro no menu". Oito abas eram muito para
    decidir rápido; as outras quatro abrem de dentro da Lista de compra, sem apagar nada.

    A quinta é pedido dele em 02/11/2026: "no menu compras criar um sub menu compra
    guiada". Ela vem logo depois da Lista, que continua sendo a primeira."""

    QUE_SAIRAM = ("compras:antes_de_comprar", "compras:sugestoes",
                  "compras:sugestoes_da_equipe", "compras:consulta")

    def entrar(self, nome, perfil):
        usuario(nome, perfil)
        self.client.login(username=nome, password=SENHA_TESTE)

    def test_o_menu_de_compras_tem_cinco_telas(self):
        compras = menu.grupo_de("compras:lista")
        self.assertEqual([tela.rotulo for tela in compras.telas],
                         ["Lista de compra", "Compra guiada", "Pedidos", "Fornecedores",
                          "Indicadores de compra"])

    def test_as_que_sairam_abrem_de_dentro_da_lista(self):
        self.entrar("edson", ADMINISTRACAO)
        corpo = self.client.get(reverse("compras:lista")).content.decode()
        fileira = corpo[corpo.index('class="mais-em-compras"'):]
        fileira = fileira[:fileira.index("</nav>")]
        for rota in self.QUE_SAIRAM:
            with self.subTest(rota=rota):
                self.assertIn(reverse(rota), fileira)
                self.assertEqual(self.client.get(reverse(rota)).status_code, 200)

    def test_quem_entra_numa_delas_continua_com_compras_aceso_e_volta_a_lista(self):
        self.entrar("edson", ADMINISTRACAO)
        corpo = self.client.get(reverse("compras:sugestoes")).content.decode()
        primeira = corpo[corpo.index("menu-principal"):corpo.index("menu-apoio")]
        aceso = primeira[:primeira.index('aria-current="page"')].rsplit("<a ", 1)[-1]
        self.assertIn(reverse("compras:lista"), aceso)
        navegacao = corpo[corpo.index('class="navegacao-telas"'):]
        self.assertIn(reverse("compras:lista"), navegacao)

    def test_o_administrativo_continua_chegando_as_sugestoes_da_equipe(self):
        """É ele quem ouve o cliente pedir o que não tem: a tela não pode sumir para ele."""
        self.entrar("loja", ADMINISTRATIVO)
        corpo = self.client.get(reverse("compras:lista")).content.decode()
        self.assertIn(reverse("compras:sugestoes_da_equipe"), corpo)
