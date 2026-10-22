"""Código de barras desenhado e conferência de CPF."""

from django.test import TestCase

from apps.core import barras, documento


class TestCodigoDeBarras(TestCase):
    def test_reconhece_um_ean13_de_verdade(self):
        # Código real de um produto conhecido, com o verificador fechando.
        self.assertTrue(barras.valido("4006381333931"))
        # Um dos códigos que o SET gerou para a loja.
        self.assertTrue(barras.valido("0000000000024"))

    def test_recusa_codigo_torto(self):
        self.assertFalse(barras.valido("4006381333930"))  # verificador errado
        self.assertFalse(barras.valido("123"))
        self.assertFalse(barras.valido(""))
        self.assertFalse(barras.valido(None))
        self.assertFalse(barras.valido("400638133393X"))

    def test_calcula_o_digito_verificador(self):
        self.assertEqual(barras.digito_verificador("400638133393"), "1")

    def test_desenha_so_quando_o_codigo_vale(self):
        """Desenho errado é pior do que desenho nenhum: o leitor leria outra coisa."""
        self.assertIsNone(barras.svg("123"))
        desenho = barras.svg("0000000000024")
        self.assertIn("<svg", desenho)
        self.assertIn("0000000000024", desenho)

    def test_o_desenho_tem_as_barras_na_quantidade_certa(self):
        """95 módulos: 3 de guarda, 42 à esquerda, 5 do meio, 42 à direita e 3 de guarda."""
        self.assertEqual(len(barras._modulos("0000000000024")), 95)


class TestVariantesDoCodigo(TestCase):
    """O que o leitor pela câmera devolve não é sempre o que está no SET."""

    def test_ean13_que_comeca_com_zero_tambem_vale_sem_o_zero(self):
        """Todo código do SET começa com zero, e o leitor devolve os 12 dígitos sem ele."""
        self.assertEqual(barras.variantes("0000000000024"),
                         ["0000000000024", "000000000024"])

    def test_doze_digitos_do_leitor_acham_o_codigo_de_treze_do_set(self):
        self.assertEqual(barras.variantes("000000000024"),
                         ["000000000024", "0000000000024"])

    def test_codigo_que_nao_comeca_com_zero_fica_como_esta(self):
        self.assertEqual(barras.variantes("4006381333931"), ["4006381333931"])

    def test_nome_digitado_a_mao_passa_inteiro_e_sem_invencao(self):
        self.assertEqual(barras.variantes("TAPETE SISAL"), ["TAPETE SISAL"])

    def test_vazio_nao_procura_nada(self):
        self.assertEqual(barras.variantes(""), [])
        self.assertEqual(barras.variantes("   "), [])
        self.assertEqual(barras.variantes(None), [])


class TestCpf(TestCase):
    def test_aceita_cpf_valido_com_e_sem_pontuacao(self):
        self.assertTrue(documento.valido("529.982.247-25"))
        self.assertTrue(documento.valido("52998224725"))

    def test_recusa_digito_errado_e_numero_repetido(self):
        self.assertFalse(documento.valido("529.982.247-26"))
        self.assertFalse(documento.valido("111.111.111-11"))
        self.assertFalse(documento.valido("123"))
        self.assertFalse(documento.valido(""))

    def test_formata_para_a_tela(self):
        self.assertEqual(documento.formatar("52998224725"), "529.982.247-25")
        self.assertEqual(documento.formatar("123"), "123")
