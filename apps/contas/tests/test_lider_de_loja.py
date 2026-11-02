"""O perfil Líder de loja: o administrativo inteiro, mais montar o pedido e responder a equipe.

Pedido do Edson em 31/10/2026, para a Cássia: *"será líder de loja / acesso moderado as
informações gerenciais / foco sera compras de mercadorias / controle de fornecedores /
gestao da equipe local / lançamentos de pagamentos / controle de estoque"*.

O "moderado" é o que este arquivo cobra: nada de usuários, auditoria, configuração, lista
de compra nem aprovar o próprio pedido. A conferência de telas LÊ o menu, como a varredura
de rotas: tela nova entra na conta no dia em que nasce.
"""

from django.test import TestCase
from django.urls import reverse

from apps.contas.perfis import ADMINISTRACAO, ADMINISTRATIVO, DESCRICOES, LIDER, PERFIS
from apps.core import menu
from apps.core.fabricas import SENHA_TESTE, entrar_na_area_de_acessos, usuario


class PermissoesDaLiderTest(TestCase):
    def test_tem_tudo_do_administrativo(self):
        self.assertTrue(set(PERFIS[ADMINISTRATIVO]) <= set(PERFIS[LIDER]))

    def test_monta_pedido_e_responde_a_equipe(self):
        lider = usuario("cassia", LIDER)
        for permissao in ("pedidos.registrar_pedido", "compras.responder_sugestao",
                          "fornecedores.change_fornecedor", "financeiro.lancar_pagamento",
                          "inventario.contar_estoque", "inventario.fechar_contagem",
                          "caixa.ver_caixa", "importacao.ver_painel"):
            with self.subTest(permissao=permissao):
                self.assertTrue(lider.has_perm(permissao))

    def test_nao_aprova_pedido_nem_mexe_no_que_e_da_gerencia(self):
        lider = usuario("cassia", LIDER)
        for permissao in ("pedidos.aprovar_pedido", "compras.ajustar_compra",
                          "contas.gerenciar_usuarios", "auditoria.ver_auditoria",
                          "importacao.executar_importacao", "compras.change_dadosdaempresa",
                          "alertas.configurar_email", "backup.configurar_backup",
                          "tempo.configurar_tempo", "processos.validar_processo",
                          "processos.aprovar_regra"):
            with self.subTest(permissao=permissao):
                self.assertFalse(lider.has_perm(permissao))

    def test_so_a_gerencia_aprova_pedido(self):
        quem_aprova = [nome for nome, codigos in PERFIS.items() if "pedidos.aprovar_pedido" in codigos]
        self.assertEqual(quem_aprova, [ADMINISTRACAO])

    def test_tem_descricao_para_a_tela_de_usuarios(self):
        self.assertIn("gerência aprova", DESCRICOES[LIDER])


class TelasDaLiderTest(TestCase):
    """Abre o que a permissão dela deixa, e leva 403 no resto. A lista sai do menu."""

    def test_cada_tela_do_menu_abre_ou_fecha_pela_permissao(self):
        usuario("cassia", LIDER)
        self.client.login(username="cassia", password=SENHA_TESTE)
        dela = set(PERFIS[LIDER])
        for item in menu.telas():
            with self.subTest(tela=item.rota):
                resposta = self.client.get(reverse(item.rota))
                if item.permissao is None or item.permissao in dela:
                    self.assertNotEqual(resposta.status_code, 403, f"{item.rota} devia abrir")
                    self.assertLess(resposta.status_code, 500)
                else:
                    self.assertEqual(resposta.status_code, 403, f"{item.rota} devia fechar")

    def test_o_menu_nao_mostra_o_que_ela_nao_abre(self):
        usuario("cassia", LIDER)
        self.client.login(username="cassia", password=SENHA_TESTE)
        # A segunda fileira do menu é a do assunto aberto: Sistema numa, Compras na outra.
        sistema = self.client.get(reverse("importacao:historico"))
        self.assertNotContains(sistema, reverse("contas:usuarios"))
        self.assertNotContains(sistema, reverse("auditoria:lista"))
        self.assertNotContains(sistema, reverse("alertas:painel"))
        compras = self.client.get(reverse("compras:lista"))
        self.assertContains(compras, reverse("pedidos:lista"))

    def test_a_gerencia_pode_dar_o_perfil_pela_tela(self):
        gerente = usuario("edson", ADMINISTRACAO)
        entrar_na_area_de_acessos(self.client, "edson")
        tela = self.client.get(reverse("contas:usuarios"))
        self.assertContains(tela, f'name="perfis" value="{LIDER}"')
        self.assertContains(tela, DESCRICOES[LIDER])
        resposta = self.client.post(reverse("contas:criar_usuario"), {
            "apelido": "cassia", "nome": "Cássia", "sobrenome": "Teste", "perfis": [LIDER],
        }, follow=True)
        self.assertContains(resposta, "Usuário cassia criado.")
        from django.contrib.auth import get_user_model  # noqa: PLC0415
        criada = get_user_model().objects.get(username="cassia")
        self.assertEqual(list(criada.groups.values_list("name", flat=True)), [LIDER])
        self.assertTrue(gerente.has_perm("pedidos.aprovar_pedido"))
