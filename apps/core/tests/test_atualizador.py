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

Desde a 1.47.1 o zip chega em C:\\instalacao\\pacote, a mesma pasta de onde os dois comandos
rodam (pedido do Edson em 04/11/2026), e o higienizar.ps1 roda de lá também.
"""

from pathlib import Path

from django.test import SimpleTestCase

SCRIPT = Path(__file__).resolve().parents[3] / "implantacao" / "atualizar.ps1"
HIGIENIZAR = SCRIPT.with_name("higienizar.ps1")
LEIA_ME = SCRIPT.with_name("LEIA-ME.txt")


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
        self.assertEqual(self.texto.count("PAREI: o pacote"), 1)
        self.assertEqual(self.texto.count("PAREI: em $Pacote está a versão"), 1)

    def test_quem_para_avisa_que_nao_mexeu_em_nada(self):
        """Quem lê 'parei' no meio da noite precisa saber se a loja está no ar.

        São três paradas: as duas da versão mais antiga e a da troca da pasta do pacote
        que não deu certo (1.47.1).
        """
        paradas = self.texto.count("PAREI:")
        self.assertEqual(paradas, 3)
        self.assertEqual(
            self.texto.count("Nada foi mexido: o sistema continua no ar como estava."), paradas
        )

    def test_da_para_voltar_de_proposito(self):
        """A trava não pode virar uma porta trancada: às vezes voltar é o certo."""
        self.assertIn("[switch]$Voltar", self.texto)
        self.assertEqual(self.texto.count("-not $Voltar"), 2)

    def test_a_conferencia_acontece_antes_de_trocar_a_pasta_do_pacote(self):
        """Parar depois de trocar deixaria o pacote velho armado para a próxima vez."""
        confere = self.texto.index("$versaoDoZip = VersaoDoTexto")
        troca = self.texto.index("Get-ChildItem $Pacote -Force | Where-Object")
        self.assertLess(confere, troca)

    def test_diz_em_voz_alta_qual_versao_esta_no_ar_e_qual_vai_entrar(self):
        self.assertIn("Versão no ar agora:", self.texto)
        self.assertIn("Pacote escolhido:", self.texto)


class TestOZipChegaNaPastaDoPacote(SimpleTestCase):
    """Uma pasta só desde a 1.47.1: o zip chega em C:\\instalacao\\pacote.

    Em 04/11/2026 o Edson salvou o zip da 1.47.0 dentro de C:\\instalacao\\pacote, ao lado
    do atualizar.ps1 e do higienizar.ps1, e pediu que fosse sempre assim. O atualizador de
    antes só procurava em C:\\instalacao: rodado daquele jeito, teria repetido a versão que
    já estava no ar, dizendo "Nenhum pacote novo".
    """

    def setUp(self):
        if not SCRIPT.exists():  # o pacote instalado no servidor não leva implantacao/
            self.skipTest("atualizar.ps1 só existe no repositório")
        self.texto = SCRIPT.read_text(encoding="utf-8-sig")

    def test_procura_o_zip_na_pasta_do_pacote_e_no_lugar_de_antes(self):
        busca = self.texto[self.texto.index("$zips = @(Get-ChildItem"):]
        busca = busca[: busca.index("\n")]
        self.assertIn("(Join-Path $Pacote 'cabana-sistema*.zip')", busca)
        self.assertIn("(Join-Path $Base 'cabana-sistema*.zip')", busca)

    def test_o_zip_sai_da_pasta_antes_de_ela_ser_esvaziada(self):
        """Senão o zip novo, que chega dentro dela, sumiria junto com a versão anterior."""
        guarda = self.texto.index(
            "foreach ($z in $zips) { Move-Item $z.FullName (Join-Path $Historico $z.Name) -Force }"
        )
        esvazia = self.texto.index("Get-ChildItem $Pacote -Force | Where-Object")
        self.assertLess(guarda, esvazia)

    def test_a_pasta_do_pacote_e_esvaziada_e_nunca_apagada(self):
        """O PowerShell pode estar aberto dentro dela, e o Windows não apaga pasta em uso."""
        self.assertNotIn("Remove-Item $Pacote", self.texto)
        self.assertNotIn("Move-Item $raiz $Pacote", self.texto)
        self.assertIn("Get-ChildItem $raiz -Force | Move-Item -Destination $Pacote -Force", self.texto)

    def test_se_a_troca_falhar_o_zip_volta_para_a_pasta(self):
        """O sistema ainda não foi tocado nessa hora: basta rodar de novo."""
        self.assertEqual(self.texto.count("} catch {"), 1)
        captura = self.texto[self.texto.index("} catch {"):]
        captura = captura[: captura.index("exit 1")]
        self.assertIn("Move-Item $guardado (Join-Path $Pacote $z.Name)", captura)
        self.assertIn("Nada foi mexido", captura)

    def test_o_comando_de_antes_continua_valendo(self):
        """É por ele que um servidor numa versão anterior à 1.47.1 chega à nova."""
        self.assertIn("foreach ($arquivo in @('atualizar.ps1', 'LEIA-ME.txt'))", self.texto)
        self.assertIn("Copy-Item (Join-Path $Pacote $arquivo) (Join-Path $Base $arquivo)", self.texto)

    def test_o_cabecalho_mostra_os_dois_comandos_da_pasta_do_pacote(self):
        cabecalho = self.texto[: self.texto.index("#>")]
        self.assertIn(r"C:\instalacao\pacote\atualizar.ps1", cabecalho)
        self.assertIn(r"C:\instalacao\pacote\higienizar.ps1", cabecalho)

    def test_o_leia_me_ensina_a_sair_de_uma_versao_antiga(self):
        """O atualizador já instalado é o que procura o próximo zip, e o antigo não olha em pacote."""
        if not LEIA_ME.exists():
            self.skipTest("LEIA-ME.txt só existe no repositório")
        texto = LEIA_ME.read_text(encoding="utf-8-sig")
        self.assertIn("Vindo de uma versão anterior à 1.47.1", texto)
        self.assertIn(r"C:\instalacao\pacote\atualizar.ps1", texto)


class TestAHigienizacaoRodaDasDuasPastas(SimpleTestCase):
    """O mesmo higienizar.ps1 roda da cópia instalada (a tarefa das 03:40) e da pasta do pacote.

    Até a 1.47.0 ele achava o sistema subindo uma pasta a partir de onde estava: certo em
    C:\\cabana-sistema\\scripts, errado em C:\\instalacao\\pacote, de onde procurava o Python
    em C:\\instalacao e saía sem dizer nada na tela.
    """

    def setUp(self):
        if not HIGIENIZAR.exists():  # o pacote instalado no servidor não leva implantacao/
            self.skipTest("higienizar.ps1 só existe no repositório")
        self.texto = HIGIENIZAR.read_text(encoding="utf-8-sig")

    def test_so_sobe_uma_pasta_quando_o_sistema_esta_la(self):
        self.assertIn("[string]$Destino = ''", self.texto)
        self.assertIn(r"$Destino = 'C:\cabana-sistema'", self.texto)
        self.assertIn(
            r"if ($acima -and (Test-Path (Join-Path $acima 'python\python.exe'))) { $Destino = $acima }",
            self.texto,
        )
        self.assertNotIn("$Raiz = Split-Path $PSScriptRoot -Parent", self.texto)

    def test_sem_o_sistema_diz_na_tela_o_que_faltou(self):
        falta = self.texto[self.texto.index("if (-not (Test-Path $python))"):]
        falta = falta[: falta.index("exit 1")]
        self.assertIn("Write-Host", falta)

    def test_quem_roda_na_mao_ve_o_resultado(self):
        """Antes só o -Conferir mostrava algo; limpar de verdade não dizia nada na tela."""
        self.assertIn("foreach ($linha in $saida) { Write-Host $linha }", self.texto)
        self.assertIn("Higienização concluída.", self.texto)

    def test_o_registro_nao_derruba_a_limpeza(self):
        registrar = self.texto[self.texto.index("function Registrar"):]
        registrar = registrar[: registrar.index("\n}")]
        self.assertIn("try {", registrar)

    def test_o_cabecalho_mostra_os_comandos_da_pasta_do_pacote(self):
        cabecalho = self.texto[: self.texto.index("#>")]
        self.assertIn(r"C:\instalacao\pacote\higienizar.ps1 -Conferir", cabecalho)


class TestOsAvisosMandamParaAPastaDoPacote(SimpleTestCase):
    """Os avisos de erro da importação ensinam o comando de atualizar: o da pasta do pacote."""

    def test_nenhum_aviso_usa_o_caminho_de_antes(self):
        from apps.importacao import diagnostico

        passos = [passo for _regra, explicacao in diagnostico.CAUSAS for passo in explicacao.como_resolver]
        passos += diagnostico.GERAL.como_resolver
        com_comando = [passo for passo in passos if "atualizar.ps1 " in passo or passo.endswith("atualizar.ps1")]
        self.assertTrue(com_comando)
        for passo in com_comando:
            if "C:" in passo:
                self.assertIn(r"C:\instalacao\pacote\atualizar.ps1", passo)
            self.assertNotIn(r"C:\instalacao\atualizar.ps1", passo)
