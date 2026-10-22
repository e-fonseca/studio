"""O atualizar.ps1 não pode voltar o sistema no tempo sem ninguém perceber.

Em 22/10/2026 o Edson abriu o sistema e encontrou a tela de início de 05/10: menu antigo,
"Transferência de conhecimento" na frente, nenhuma das telas que a loja usa. O programa
inteiro vive numa pasta só (`C:\\cabana-sistema\\app`), que o instalador apaga e copia de
novo a cada atualização, então basta o script escolher o zip errado para a loja voltar
semanas atrás — e ele escolhia pela DATA DO ARQUIVO, que mente: copiar um zip de uma pasta
para outra leva junto a data antiga.

Agora a escolha é pela versão no nome, e um pacote mais antigo que o instalado faz o script
parar antes de encostar em qualquer coisa. Estes testes leem o script, porque um erro aqui
não aparece em nenhuma tela: aparece na loja, horas depois.
"""

from pathlib import Path

from django.test import SimpleTestCase

SCRIPT = Path(__file__).resolve().parents[3] / "implantacao" / "atualizar.ps1"


class TestOAtualizadorNaoVoltaNoTempo(SimpleTestCase):
    def setUp(self):
        if not SCRIPT.exists():  # o pacote instalado no servidor não leva implantacao/
            self.skipTest("atualizar.ps1 só existe no repositório")
        self.texto = SCRIPT.read_text(encoding="utf-8-sig")

    def test_escolhe_o_pacote_pela_versao_e_nao_so_pela_data(self):
        ordenacao = self.texto[self.texto.index("$zips = @(Get-ChildItem"):]
        ordenacao = ordenacao[: ordenacao.index("\n$ignorados")]
        self.assertIn("VersaoDoTexto $_.Name", ordenacao)
        self.assertIn("LastWriteTime", ordenacao)

    def test_versao_sem_numero_no_nome_nunca_ganha_de_um_pacote_com_nome_certo(self):
        self.assertIn("[version]'0.0.0'", self.texto)

    def test_para_quando_o_pacote_e_mais_antigo_do_que_o_que_esta_no_ar(self):
        """Nos dois caminhos: zip novo na pasta, e repetir o pacote que já estava lá."""
        self.assertEqual(self.texto.count("$versaoDoZip -lt $VersaoInstalada"), 1)
        self.assertEqual(self.texto.count("$vPacote -lt $VersaoInstalada"), 1)
        self.assertEqual(self.texto.count("PAREI:"), 2)

    def test_quem_para_avisa_que_nao_mexeu_em_nada(self):
        """Quem lê 'parei' no meio da noite precisa saber se a loja está no ar."""
        self.assertEqual(
            self.texto.count("Nada foi mexido: o sistema continua no ar como estava."), 2
        )

    def test_da_para_voltar_de_proposito(self):
        """A trava não pode virar uma porta trancada: às vezes voltar é o certo."""
        self.assertIn("[switch]$Voltar", self.texto)
        self.assertEqual(self.texto.count("-not $Voltar"), 2)

    def test_a_conferencia_acontece_antes_de_trocar_a_pasta_do_pacote(self):
        """Parar depois de trocar deixaria o pacote velho armado para a próxima vez."""
        confere = self.texto.index("$versaoDoZip = VersaoDoTexto")
        troca = self.texto.index("if (Test-Path $Pacote) { Remove-Item $Pacote -Recurse -Force }")
        self.assertLess(confere, troca)

    def test_diz_em_voz_alta_qual_versao_esta_no_ar_e_qual_vai_entrar(self):
        self.assertIn("Versão no ar agora:", self.texto)
        self.assertIn("Pacote escolhido:", self.texto)
