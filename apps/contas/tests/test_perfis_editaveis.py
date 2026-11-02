"""Perfis editáveis pela tela, vários por pessoa, e o instalador que não desfaz nada (1.44.0)."""

import importlib

from django.apps import apps as registro
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from apps.auditoria.models import EventoAuditoria
from apps.contas import autorizacao, catalogo, servicos
from apps.contas.autorizacao import NaoPode
from apps.contas.models import Perfil, PermissaoOferecida
from apps.contas.perfis import (ADMIN_ACESSOS, ADMINISTRACAO, ADMINISTRATIVO, COMPRAS, CONSULTA,
                                ESTOQUE, LIDER, PADRAO, VENDEDOR)
from apps.core.fabricas import SENHA_TESTE, entrar_na_area_de_acessos, usuario


def _permissoes(nome):
    return autorizacao.permissoes_do_perfil(Group.objects.get(name=nome))


class ConfigurarPerfisTest(TestCase):
    def test_cria_os_oito_perfis_com_o_padrao(self):
        servicos.configurar_perfis()
        for nome, codigos in PADRAO.items():
            self.assertEqual(_permissoes(nome), set(codigos), nome)
            self.assertTrue(Perfil.objects.get(grupo__name=nome).padrao)

    def test_rodar_de_novo_nao_duplica_nada(self):
        servicos.configurar_perfis()
        oferecidas = PermissaoOferecida.objects.count()
        servicos.configurar_perfis()
        self.assertEqual(PermissaoOferecida.objects.count(), oferecidas)
        self.assertEqual(Group.objects.filter(name__in=PADRAO).count(), len(PADRAO))

    def test_o_que_a_gerencia_tirou_nao_volta_na_atualizacao(self):
        """Até a 1.43.0 o instalador regravava cada perfil com o padrão do código."""
        servicos.configurar_perfis()
        grupo = Group.objects.get(name=LIDER)
        sem_caixa = _permissoes(LIDER) - {"caixa.ver_caixa"}
        servicos.editar_perfil(grupo, sem_caixa, motivo="o caixa fica com o administrativo")
        servicos.configurar_perfis()
        self.assertNotIn("caixa.ver_caixa", _permissoes(LIDER))

    def test_o_que_a_gerencia_pos_continua_depois_da_atualizacao(self):
        servicos.configurar_perfis()
        grupo = Group.objects.get(name=ESTOQUE)
        servicos.editar_perfil(grupo, _permissoes(ESTOQUE) | {"processos.view_processo"},
                               motivo="o estoque segue o processo de recebimento")
        servicos.configurar_perfis()
        self.assertIn("processos.view_processo", _permissoes(ESTOQUE))

    def test_permissao_nova_de_uma_versao_entra_uma_vez(self):
        servicos.configurar_perfis()
        grupo = Group.objects.get(name=COMPRAS)
        permissao = catalogo.objetos(["compras.ver_compras"])[0]
        # Como se a versão anterior não conhecesse a permissão.
        PermissaoOferecida.objects.filter(grupo=grupo, permissao=permissao).delete()
        grupo.permissions.remove(permissao)
        servicos.configurar_perfis()
        self.assertIn("compras.ver_compras", _permissoes(COMPRAS))

    def test_perfil_retirado_nao_volta(self):
        servicos.configurar_perfis()
        grupo = Group.objects.get(name=CONSULTA)
        servicos.retirar_perfil(grupo)
        servicos.configurar_perfis()
        self.assertEqual(_permissoes(CONSULTA), set())
        self.assertIsNotNone(Perfil.objects.get(grupo=grupo).retirado_em)


class EditarPerfilTest(TestCase):
    def setUp(self):
        servicos.configurar_perfis()
        self.gerente = usuario("edson", ADMINISTRACAO)
        self.cassia = usuario("cassia", LIDER)

    def test_mudar_o_perfil_vale_no_proximo_clique(self):
        self.client.login(username="cassia", password=SENHA_TESTE)
        self.assertEqual(self.client.get(reverse("caixa:lista")).status_code, 200)
        servicos.editar_perfil(Group.objects.get(name=LIDER), _permissoes(LIDER) - {"caixa.ver_caixa"},
                               motivo="teste", responsavel=self.gerente)
        self.assertEqual(self.client.get(reverse("caixa:lista")).status_code, 403)

    def test_pela_tela_pede_o_motivo_e_registra_entrou_e_saiu(self):
        entrar_na_area_de_acessos(self.client, "edson")
        grupo = Group.objects.get(name=LIDER)
        url = reverse("contas:perfil", args=[grupo.pk])
        novas = sorted(_permissoes(LIDER) - {"caixa.ver_caixa"})
        resposta = self.client.post(url, {"permissoes": novas}, follow=True)
        self.assertContains(resposta, "Diga em poucas palavras por que")
        self.assertIn("caixa.ver_caixa", _permissoes(LIDER))
        self.client.post(url, {"permissoes": novas, "motivo": "o caixa é do administrativo"})
        self.assertNotIn("caixa.ver_caixa", _permissoes(LIDER))
        evento = EventoAuditoria.objects.get(acao="permissao.perfil_alterado")
        self.assertEqual(evento.depois["sairam"], ["caixa.ver_caixa"])
        self.assertEqual(evento.motivo, "o caixa é do administrativo")
        self.assertEqual(evento.depois["pessoas_no_perfil"], 1)
        # O sinal genérico ficou quieto: a mesma mudança não aparece duas vezes.
        self.assertFalse(EventoAuditoria.objects.filter(acao="permissao.perfil_alterado_por_fora").exists())

    def test_mudanca_por_fora_da_tela_tambem_fica_registrada(self):
        grupo = Group.objects.get(name=ESTOQUE)
        grupo.permissions.add(catalogo.objetos(["processos.view_processo"])[0])
        self.assertTrue(EventoAuditoria.objects.filter(acao="permissao.perfil_alterado_por_fora",
                                                       recurso_id=str(grupo.pk)).exists())

    def test_ninguem_edita_o_perfil_em_que_esta(self):
        with self.assertRaises(NaoPode):
            servicos.editar_perfil(Group.objects.get(name=ADMINISTRACAO), set(catalogo.CODIGOS),
                                   motivo="teste", responsavel=self.gerente)
        entrar_na_area_de_acessos(self.client, "edson")
        tela = self.client.get(reverse("contas:perfil", args=[Group.objects.get(name=ADMINISTRACAO).pk]))
        self.assertContains(tela, "Você está no perfil")
        self.assertNotContains(tela, "Salvar o perfil")

    def test_quem_edita_perfis_sem_dinheiro_nao_poe_dinheiro_em_perfil_nenhum(self):
        editor_de_perfis = Group.objects.create(name="Só edita perfis")
        editor_de_perfis.permissions.set(catalogo.objetos([autorizacao.GERENCIAR, autorizacao.EDITAR_PERFIS]))
        editor = usuario("ti", "Só edita perfis")
        grupo = Group.objects.get(name=ESTOQUE)
        with self.assertRaises(NaoPode):
            servicos.editar_perfil(grupo, _permissoes(ESTOQUE) | {"financeiro.ver_financeiro"},
                                   motivo="teste", responsavel=editor)
        # O que não é dinheiro nem administração, ele põe.
        servicos.editar_perfil(grupo, _permissoes(ESTOQUE) | {"processos.view_processo"},
                               motivo="teste", responsavel=editor)
        self.assertIn("processos.view_processo", _permissoes(ESTOQUE))

    def test_envio_montado_a_mao_nao_destrava_a_caixa_travada(self):
        """A caixa travada não vai no envio; mandar o valor dela à mão não muda nada."""
        editor_de_perfis = Group.objects.create(name="Só edita perfis")
        editor_de_perfis.permissions.set(catalogo.objetos([autorizacao.GERENCIAR, autorizacao.EDITAR_PERFIS]))
        usuario("ti", "Só edita perfis")
        entrar_na_area_de_acessos(self.client, "ti")
        grupo = Group.objects.get(name=ESTOQUE)
        antes = _permissoes(ESTOQUE)
        self.client.post(reverse("contas:perfil", args=[grupo.pk]), {
            "permissoes": sorted(antes | {"financeiro.ver_financeiro", "pedidos.aprovar_pedido"}),
            "motivo": "tentativa",
        })
        self.assertEqual(_permissoes(ESTOQUE), antes)
        # E tirar a caixa travada também não: Estoque tem "Ver pedidos" (dinheiro), que ele não tem.
        self.client.post(reverse("contas:perfil", args=[grupo.pk]), {
            "permissoes": sorted(antes - {"pedidos.view_pedido"}), "motivo": "tentativa"})
        self.assertIn("pedidos.view_pedido", _permissoes(ESTOQUE))

    def test_codigo_inventado_e_recusado(self):
        with self.assertRaises(NaoPode):
            servicos.editar_perfil(Group.objects.get(name=ESTOQUE), {"contas.virar_dono"},
                                   motivo="teste", responsavel=usuario("rh", ADMINISTRACAO))

    def test_quem_so_administra_pessoas_ve_a_matriz_e_nao_edita(self):
        usuario("rh", ADMIN_ACESSOS)
        entrar_na_area_de_acessos(self.client, "rh")
        matriz = self.client.get(reverse("contas:perfis"))
        self.assertEqual(matriz.status_code, 200)
        for permissao in catalogo.CATALOGO:
            self.assertContains(matriz, permissao.nome)
        grupo = Group.objects.get(name=ESTOQUE)
        self.assertNotContains(self.client.get(reverse("contas:perfil", args=[grupo.pk])), "Salvar o perfil")
        resposta = self.client.post(reverse("contas:perfil", args=[grupo.pk]),
                                    {"permissoes": ["processos.view_processo"], "motivo": "x"})
        self.assertEqual(resposta.status_code, 403)

    def test_o_vendedor_nao_abre_a_matriz(self):
        usuario("balcao", VENDEDOR)
        self.client.login(username="balcao", password=SENHA_TESTE)
        self.assertEqual(self.client.get(reverse("contas:perfis")).status_code, 403)


class CriarERetirarPerfilTest(TestCase):
    def setUp(self):
        servicos.configurar_perfis()
        self.gerente = usuario("edson", ADMINISTRACAO)
        entrar_na_area_de_acessos(self.client, "edson")

    def test_criar_copiando_outro(self):
        origem = Group.objects.get(name=ESTOQUE)
        resposta = self.client.post(reverse("contas:criar_perfil"),
                                    {"nome": "Caixa", "copiar_de": origem.pk, "descricao": "Abre e fecha o caixa"})
        novo = Group.objects.get(name="Caixa")
        self.assertRedirects(resposta, reverse("contas:perfil", args=[novo.pk]))
        self.assertEqual(_permissoes("Caixa"), _permissoes(ESTOQUE))
        self.assertFalse(Perfil.objects.get(grupo=novo).padrao)

    def test_nome_repetido_nao_passa(self):
        resposta = self.client.post(reverse("contas:criar_perfil"), {"nome": "compras"}, follow=True)
        self.assertContains(resposta, "Já existe um perfil chamado compras")

    def test_so_se_retira_perfil_vazio_e_dá_para_trazer_de_volta(self):
        grupo = Group.objects.get(name=LIDER)
        usuario("cassia", LIDER)
        resposta = self.client.post(reverse("contas:retirar_perfil", args=[grupo.pk]), follow=True)
        self.assertContains(resposta, "Ainda há gente no perfil")
        vazio = Group.objects.get(name=COMPRAS)
        self.client.post(reverse("contas:retirar_perfil", args=[vazio.pk]))
        self.assertIsNotNone(Perfil.objects.get(grupo=vazio).retirado_em)
        self.assertEqual(_permissoes(COMPRAS), set())
        # Retirado não se dá a ninguém.
        with self.assertRaises(ValueError):
            servicos.definir_perfis(usuario("vanda", VENDEDOR), [COMPRAS])
        self.client.post(reverse("contas:devolver_perfil", args=[vazio.pk]))
        self.assertIsNone(Perfil.objects.get(grupo=vazio).retirado_em)


class VariosPerfisTest(TestCase):
    def test_a_pessoa_pode_a_soma_dos_perfis(self):
        pessoa = usuario("vanda", VENDEDOR, ESTOQUE)
        self.assertTrue(pessoa.has_perm("importacao.consultar_produtos"))
        self.assertTrue(pessoa.has_perm("inventario.contar_estoque"))
        self.assertFalse(pessoa.has_perm("financeiro.ver_financeiro"))

    def test_a_ficha_diz_de_onde_vem_cada_permissao(self):
        servicos.configurar_perfis()
        usuario("edson", ADMINISTRACAO)
        pessoa = usuario("vanda", VENDEDOR, ESTOQUE)
        efetivas = dict(servicos.permissoes_efetivas(pessoa))
        consulta = next(i for i in efetivas["Estoque"] if i["permissao"].codigo == "importacao.consultar_produtos")
        self.assertEqual(sorted(consulta["de"]), [ESTOQUE, VENDEDOR])
        entrar_na_area_de_acessos(self.client, "edson")
        ficha = self.client.get(reverse("contas:ficha", args=[pessoa.pk]))
        self.assertContains(ficha, f"Vem de: {VENDEDOR}, {ESTOQUE}.")


class DivisaoDoPainelTest(TestCase):
    """A migração 0008: quem via o painel continua vendo tudo; os grupos velhos saem do caminho."""

    def _migracao(self):
        return importlib.import_module("apps.contas.migrations.0008_dividir_ver_painel_e_grupos_antigos")

    def test_quem_tinha_o_painel_ganha_as_quatro_e_os_grupos_velhos_se_limpam(self):
        painel = Permission.objects.get(content_type__app_label="importacao", codename="ver_painel")
        personalizado = Group.objects.create(name="Personalizado")
        personalizado.permissions.add(painel)
        compras_velho = Group.objects.create(name="Compras")
        compras_velho.permissions.add(painel)
        Group.objects.create(name="Gerência")
        operadores = Group.objects.create(name="Operadores")
        alguem = get_user_model().objects.create_user("antiga", password=SENHA_TESTE)
        alguem.groups.add(operadores)
        avulsa = get_user_model().objects.create_user("avulsa", password=SENHA_TESTE)
        avulsa.user_permissions.add(painel)

        self._migracao().dividir(registro, None)

        novas = {"compras.ver_compras", "importacao.ver_vendas", "importacao.ver_margem",
                 "importacao.ver_importacoes"}
        self.assertLessEqual(novas, autorizacao.permissoes_do_perfil(personalizado))
        self.assertLessEqual(novas, autorizacao.permissoes_de(get_user_model().objects.get(username="avulsa")))
        self.assertEqual(autorizacao.permissoes_do_perfil(compras_velho), set())
        self.assertFalse(Group.objects.filter(name="Gerência").exists())
        self.assertTrue(Group.objects.filter(name="Operadores").exists())
        limpeza = EventoAuditoria.objects.get(acao="permissao.grupos_antigos_limpos")
        self.assertEqual(limpeza.depois["com_gente_dentro"], {"Operadores": ["antiga"]})
        self.assertEqual(limpeza.usuario_rotulo, "atualização 1.44.0")

    def test_o_administrativo_abre_as_mesmas_telas_de_antes(self):
        usuario("ana", ADMINISTRATIVO)
        self.client.login(username="ana", password=SENHA_TESTE)
        for rota in ("compras:lista", "painel:vendas_dia", "margem:lista", "importacao:historico",
                     "painel:dashboard", "painel:geral"):
            self.assertEqual(self.client.get(reverse(rota)).status_code, 200, rota)

    def test_consulta_ve_indicadores_e_vendas_mas_nao_a_margem_nem_a_lista(self):
        usuario("olhar", CONSULTA)
        self.client.login(username="olhar", password=SENHA_TESTE)
        self.assertEqual(self.client.get(reverse("painel:vendas_dia")).status_code, 200)
        self.assertEqual(self.client.get(reverse("margem:lista")).status_code, 403)
        self.assertEqual(self.client.get(reverse("compras:lista")).status_code, 403)
        self.assertEqual(self.client.get(reverse("auditoria:lista")).status_code, 200)

    def test_compras_ve_a_lista_e_nao_os_painéis(self):
        usuario("comprador", COMPRAS)
        self.client.login(username="comprador", password=SENHA_TESTE)
        self.assertEqual(self.client.get(reverse("compras:lista")).status_code, 200)
        self.assertEqual(self.client.get(reverse("painel:dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("margem:lista")).status_code, 403)
