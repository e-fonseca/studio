"""Cadastro de clientes: o que aparece e o que o sistema não guarda."""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.clientes.models import ClienteImportado
from apps.contas.perfis import ADMINISTRACAO, VENDEDOR
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.importacao.models import Importacao


class ClientesTest(TestCase):
    def setUp(self):
        hoje = timezone.localdate()
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO,
            situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(),
            data_corte=hoje - timedelta(days=1),
        )
        ClienteImportado.objects.create(
            importacao=self.importacao, id_set=84, codigo="0083", nome="CONSUMIDOR FINAL",
            generico=True, compras=43397, valor_comprado=Decimal("4000000"),
            valor_comprado_12m=Decimal("1000000"),
        )
        ClienteImportado.objects.create(
            importacao=self.importacao, id_set=103, codigo="0102", nome="PAULO ALVARENGA",
            cidade="Niterói", uf="RJ", compras=3, valor_comprado=Decimal("590.68"),
            valor_comprado_12m=Decimal("0"),
        )
        ClienteImportado.objects.create(
            importacao=self.importacao, id_set=5, codigo="0004", nome="CONDOMINIO VANGUARDA",
            pessoa_juridica=True, cidade="São Paulo", uf="SP", compras=3,
            valor_comprado=Decimal("110"), valor_comprado_12m=Decimal("110"),
        )
        usuario("gerente", ADMINISTRACAO)

    def test_cliente_do_balcao_fica_fora_da_lista_e_aparece_separado(self):
        self.client.login(username="gerente", password=SENHA_TESTE)
        resposta = self.client.get(reverse("clientes:lista"))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context["total"], 2)
        self.assertEqual(resposta.context["com_compra_12m"], 1)
        self.assertEqual(resposta.context["compraram"], 2)
        self.assertEqual(resposta.context["sem_compra"], 0)
        self.assertEqual(resposta.context["pessoas_juridicas"], 1)
        self.assertEqual(resposta.context["balcao_vendas"], 43397)
        nomes = [c.nome for c in resposta.context["clientes"]]
        self.assertNotIn("CONSUMIDOR FINAL", nomes)
        self.assertEqual(nomes[0], "CONDOMINIO VANGUARDA")

    def test_modelo_nao_guarda_dado_pessoal_alem_do_necessario(self):
        """Documento, endereço e telefone ficam no SET: não há campo para eles aqui."""
        campos = {campo.name for campo in ClienteImportado._meta.get_fields()}
        for proibido in ("cpf", "cnpj", "rg", "endereco", "telefone", "email", "nascimento"):
            self.assertNotIn(proibido, campos)

    def test_operador_nao_ve_clientes(self):
        usuario("balcao", VENDEDOR)
        self.client.login(username="balcao", password=SENHA_TESTE)
        self.assertEqual(self.client.get(reverse("clientes:lista")).status_code, 403)
