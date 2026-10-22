from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase

from apps.auditoria.models import EventoAuditoria
from apps.contas.perfis import ADMINISTRACAO, ADMINISTRATIVO, VENDEDOR
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.processos import regras
from apps.processos.models import Afirmacao, Area, ExecucaoTeste, Processo
from apps.processos.roteiro import PROCESSOS_INICIAIS

Estado = Processo.Estado
R = ExecucaoTeste.Resultado

CONTEUDO = {
    "objetivo": "Conferir mercadoria recebida contra o pedido.",
    "gatilho": "Chegada de entrega de fornecedor.",
    "frequencia": "A cada entrega",
    "pre_requisitos": "",
    "passos": "Abrir o pedido\nContar as peças\nAnotar divergências",
    "tela_origem": "SET > Compras",
    "exemplos": "",
    "documentos_entrada": "",
    "documentos_saida": "",
    "conferencias": "",
    "excecoes": "",
    "aprovacao_necessaria": "",
    "evidencia_conclusao": "Pedido marcado como conferido.",
}


class Base(TestCase):
    def setUp(self):
        # Quem documenta e quem testa são duas pessoas do administrativo: a base de
        # processos existe justamente para outra pessoa conseguir executar pela documentação.
        # O vendedor não entra aqui, o perfil dele é só a consulta de balcão.
        self.gerente = usuario("edson", ADMINISTRACAO)
        self.estoque = usuario("barbara", ADMINISTRATIVO)
        self.operador = usuario("carla", ADMINISTRATIVO)
        self.consulta = usuario("vendedor", VENDEDOR)
        self.processo = regras.criar_processo(
            self.estoque, titulo="Recebimento", area=Area.RECEBIMENTO,
            criticidade=Processo.Criticidade.ALTA, titular=self.estoque, substituto=self.operador,
        )

    def escrever(self, autor=None, base=0, **mudancas):
        return regras.salvar_versao(autor or self.estoque, self.processo, versao_base=base,
                                    resumo_mudanca="teste", **{**CONTEUDO, **mudancas})

    def recarregar(self):
        self.processo.refresh_from_db()
        return self.processo


class FluxoCompletoTest(Base):
    def test_caminho_feliz_ate_validado(self):
        self.escrever()
        self.assertEqual(self.recarregar().estado, Estado.EM_DOCUMENTACAO)
        regras.enviar_para_teste(self.estoque, self.processo)
        self.assertEqual(self.recarregar().estado, Estado.EM_TESTE)
        regras.registrar_teste(self.gerente, self.processo, resultado=R.CONCLUIU_COM_DIFICULDADE,
                               usou_somente_documentacao=True, dificuldades="Passo 2 confuso")
        regras.validar(self.gerente, self.processo)
        p = self.recarregar()
        self.assertEqual(p.estado, Estado.VALIDADO)
        self.assertEqual(p.versao_validada.numero, 1)
        self.assertEqual(p.validado_por, self.gerente)
        acoes = set(EventoAuditoria.objects.filter(recurso_id=str(p.pk)).values_list("acao", flat=True))
        self.assertTrue({"processo.criado", "processo.versao_criada", "processo.estado_alterado",
                         "processo.teste_registrado"} <= acoes)

    def test_nao_vai_para_teste_incompleto(self):
        self.escrever(evidencia_conclusao="", gatilho="")
        with self.assertRaisesMessage(regras.RegraViolada, "evidência de conclusão"):
            regras.enviar_para_teste(self.estoque, self.processo)

    def test_exige_titular_e_substituto_diferentes(self):
        self.processo.substituto = self.estoque
        self.processo.save()
        self.escrever()
        with self.assertRaisesMessage(regras.RegraViolada, "substituto precisa ser uma pessoa diferente"):
            regras.enviar_para_teste(self.estoque, self.processo)

    def test_autor_e_titular_nao_testam(self):
        self.escrever(autor=self.gerente)
        regras.enviar_para_teste(self.gerente, self.processo)
        for pessoa in (self.gerente, self.estoque):  # autor da versão e titular
            with self.assertRaisesMessage(regras.RegraViolada, "outra pessoa"):
                regras.registrar_teste(pessoa, self.processo, resultado=R.CONCLUIU, usou_somente_documentacao=True)

    def test_teste_sem_sucesso_devolve_para_documentacao(self):
        self.escrever()
        regras.enviar_para_teste(self.estoque, self.processo)
        regras.registrar_teste(self.operador, self.processo, resultado=R.NAO_CONCLUIU,
                               usou_somente_documentacao=True, dificuldades="Faltou o passo do lacre")
        self.assertEqual(self.recarregar().estado, Estado.EM_DOCUMENTACAO)

    def test_teste_com_ajuda_nao_conta_para_validar(self):
        self.escrever()
        regras.enviar_para_teste(self.estoque, self.processo)
        regras.registrar_teste(self.operador, self.processo, resultado=R.CONCLUIU,
                               usou_somente_documentacao=False, dificuldades="")
        self.assertEqual(self.recarregar().estado, Estado.EM_DOCUMENTACAO)

    def test_validar_exige_teste_aprovado_da_versao_atual(self):
        self.escrever()
        regras.enviar_para_teste(self.estoque, self.processo)
        with self.assertRaisesMessage(regras.RegraViolada, "Falta um teste"):
            regras.validar(self.gerente, self.processo)

    def test_so_gerencia_valida(self):
        self.escrever()
        regras.enviar_para_teste(self.estoque, self.processo)
        regras.registrar_teste(self.operador, self.processo, resultado=R.CONCLUIU, usou_somente_documentacao=True)
        with self.assertRaises(regras.SemPermissao):
            regras.validar(self.estoque, self.processo)

    def test_nova_versao_depois_de_validado_volta_para_documentacao(self):
        self.escrever()
        regras.enviar_para_teste(self.estoque, self.processo)
        regras.registrar_teste(self.operador, self.processo, resultado=R.CONCLUIU, usou_somente_documentacao=True)
        regras.validar(self.gerente, self.processo)
        self.escrever(base=1, passos="Abrir o pedido\nContar\nConferir lacre")
        p = self.recarregar()
        self.assertEqual(p.estado, Estado.EM_DOCUMENTACAO)
        self.assertEqual(p.versao_atual.numero, 2)
        self.assertEqual(p.versao_validada.numero, 1)  # referência anterior continua registrada
        regras.enviar_para_teste(self.estoque, p)
        with self.assertRaisesMessage(regras.RegraViolada, "Falta um teste"):
            regras.validar(self.gerente, p)  # o teste da versão 1 não vale para a 2

    def test_devolver_validado_exige_gerencia_e_motivo(self):
        self.escrever()
        regras.enviar_para_teste(self.estoque, self.processo)
        regras.registrar_teste(self.operador, self.processo, resultado=R.CONCLUIU, usou_somente_documentacao=True)
        regras.validar(self.gerente, self.processo)
        with self.assertRaises(regras.SemPermissao):
            regras.devolver(self.estoque, self.processo, "mudou")
        with self.assertRaisesMessage(regras.RegraViolada, "motivo"):
            regras.devolver(self.gerente, self.processo, " ")
        regras.devolver(self.gerente, self.processo, "Fornecedor mudou o processo")
        p = self.recarregar()
        self.assertEqual(p.estado, Estado.EM_DOCUMENTACAO)
        self.assertIsNone(p.versao_validada)


class VersoesTest(Base):
    def test_edicao_concorrente_e_recusada(self):
        self.escrever()
        self.escrever(base=1, objetivo="Mudança da Ana")
        with self.assertRaisesMessage(regras.RegraViolada, "Outra pessoa salvou a versão 2"):
            self.escrever(base=1, objetivo="Mudança do Beto")

    def test_versao_e_imutavel(self):
        v = self.escrever()
        v.objetivo = "alterado"
        with self.assertRaises(PermissionError):
            v.save()

    def test_sem_mudanca_nao_cria_versao(self):
        self.escrever()
        with self.assertRaisesMessage(regras.RegraViolada, "Nada mudou"):
            self.escrever(base=1)


class TextoSeguroTest(Base):
    def test_recusa_senha(self):
        with self.assertRaisesMessage(regras.RegraViolada, "senha"):
            self.escrever(passos="Entrar no SET\nsenha: cabana2024")

    def test_recusa_cpf(self):
        with self.assertRaisesMessage(regras.RegraViolada, "CPF"):
            self.escrever(exemplos="Cliente 123.456.789-09 trocou a peça")

    def test_aceita_texto_comum_sobre_senha(self):
        self.escrever(pre_requisitos="Pedir à gerência a senha de acesso ao SET")


class AfirmacoesTest(Base):
    def test_regra_so_pela_gerencia(self):
        with self.assertRaises(regras.SemPermissao):
            regras.registrar_afirmacao(self.estoque, self.processo, tipo=Afirmacao.Tipo.REGRA,
                                       texto="Conferir sempre em dupla", fonte="gestão")
        a = regras.registrar_afirmacao(self.gerente, self.processo, tipo=Afirmacao.Tipo.REGRA,
                                       texto="Conferir sempre em dupla", fonte="gestão")
        self.assertEqual(a.aprovado_por, self.gerente)

    def test_declaracao_por_quem_documenta(self):
        a = regras.registrar_afirmacao(self.estoque, self.processo, tipo=Afirmacao.Tipo.DECLARACAO,
                                       texto="Sempre confiro o lacre", fonte="Bárbara")
        self.assertIsNone(a.aprovado_por)


class AnexosTest(Base):
    LIMITE = 1024 * 1024

    def anexar(self, conteudo, nome, **extra):
        arquivo = SimpleUploadedFile(nome, conteudo)
        opcoes = {"descricao": "tela", "contem_imagem_de_pessoa": False, "autorizacao_registrada": False}
        opcoes.update(extra)
        return regras.anexar(self.estoque, self.processo, arquivo, tamanho_maximo=self.LIMITE, **opcoes)

    def test_aceita_pdf_valido(self):
        anexo = self.anexar(b"%PDF-1.7 conteudo", "../../etc/manual.pdf")
        self.assertEqual(anexo.nome_original, "manual.pdf")
        self.assertNotIn("..", anexo.arquivo.name)

    def test_recusa_extensao_falsa(self):
        with self.assertRaisesMessage(regras.RegraViolada, "não corresponde"):
            self.anexar(b"MZ\x90\x00executavel", "planilha.pdf")

    def test_recusa_tipo_nao_aceito(self):
        with self.assertRaisesMessage(regras.RegraViolada, "Tipo de arquivo"):
            self.anexar(b"echo", "script.bat")

    def test_recusa_tamanho(self):
        with self.assertRaisesMessage(regras.RegraViolada, "limite"):
            self.anexar(b"%PDF-" + b"0" * self.LIMITE, "grande.pdf")

    def test_imagem_de_pessoa_exige_autorizacao(self):
        with self.assertRaisesMessage(regras.RegraViolada, "autorização"):
            self.anexar(b"\x89PNG\r\n\x1a\nxx", "foto.png", contem_imagem_de_pessoa=True)
        self.anexar(b"\x89PNG\r\n\x1a\nxx", "foto.png", contem_imagem_de_pessoa=True, autorizacao_registrada=True)

    def test_duplicado_recusado(self):
        self.anexar(b"%PDF-1", "a.pdf")
        with self.assertRaisesMessage(regras.RegraViolada, "já está anexado"):
            self.anexar(b"%PDF-1", "b.pdf")


class TelasEPermissoesTest(Base):
    def entrar(self, u):
        self.assertTrue(self.client.login(username=u.username, password=SENHA_TESTE))

    def test_quadro_mostra_colunas_e_busca(self):
        self.escrever()
        self.entrar(self.operador)
        resposta = self.client.get("/sistema/processos/?q=lacre")
        self.assertContains(resposta, "Em teste por outra pessoa")
        self.assertNotContains(resposta, "P-%03d · Recebimento" % self.processo.pk)
        resposta = self.client.get("/sistema/processos/?q=pedido")
        self.assertContains(resposta, "Recebimento")

    def test_vendedor_nao_cadastra_nem_edita(self):
        self.entrar(self.consulta)
        self.assertEqual(self.client.get("/sistema/processos/novo/").status_code, 403)
        self.assertEqual(self.client.get(f"/sistema/processos/{self.processo.pk}/procedimento/").status_code, 403)
        self.assertEqual(self.client.post("/sistema/processos/novo/", {"titulo": "x", "area": "outra"}).status_code, 403)

    def test_vendedor_nao_envia_para_teste_pela_url(self):
        self.escrever()
        self.entrar(self.consulta)
        self.client.post(f"/sistema/processos/{self.processo.pk}/enviar-para-teste/")
        self.assertEqual(self.recarregar().estado, Estado.EM_DOCUMENTACAO)

    def test_vendedor_nao_abre_a_base_de_processos(self):
        """O perfil de balcão não tem nada a fazer aqui: a tela inteira é da gerência e do administrativo."""
        self.entrar(self.consulta)
        self.assertEqual(self.client.get("/sistema/processos/").status_code, 403)
        # O registro de teste devolve para a página do processo com um aviso, em vez de
        # 403: quem não pode nem abrir o processo cai no 403 da própria página.
        resposta = self.client.post(f"/sistema/processos/{self.processo.pk}/testes/",
                                    {"resultado": "concluiu", "usou_somente_documentacao": "on"})
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(self.client.get(resposta["Location"]).status_code, 403)
        self.assertFalse(self.processo.testes.exists())

    def test_fluxo_pelas_telas(self):
        self.entrar(self.estoque)
        resposta = self.client.post("/sistema/processos/novo/", {
            "titulo": "Inventário mensal", "area": "inventario", "criticidade": "alta",
            "fonte_conhecimento": "Bárbara", "titular": self.estoque.pk, "substituto": self.operador.pk,
        })
        novo = Processo.objects.get(titulo="Inventário mensal")
        self.assertRedirects(resposta, f"/sistema/processos/{novo.pk}/procedimento/")
        self.client.post(f"/sistema/processos/{novo.pk}/procedimento/",
                         {**CONTEUDO, "versao_base": 0, "resumo_mudanca": "Primeira versão."})
        self.client.post(f"/sistema/processos/{novo.pk}/enviar-para-teste/")
        novo.refresh_from_db()
        self.assertEqual(novo.estado, Estado.EM_TESTE)
        pagina = self.client.get(f"/sistema/processos/{novo.pk}/")
        self.assertContains(pagina, "Contar as peças")
        self.assertContains(pagina, "Registrar meu teste")
        self.assertNotContains(pagina, "Validar processo")

    def test_procedimento_com_senha_mostra_erro_sem_salvar(self):
        self.entrar(self.estoque)
        resposta = self.client.post(f"/sistema/processos/{self.processo.pk}/procedimento/",
                                    {**CONTEUDO, "passos": "senha=123", "versao_base": 0, "resumo_mudanca": "x"})
        self.assertContains(resposta, "parece conter uma senha")
        self.assertFalse(self.processo.versoes.exists())

    def test_anexo_so_com_permissao_e_auditado(self):
        anexo = regras.anexar(self.estoque, self.processo, SimpleUploadedFile("m.pdf", b"%PDF-1"),
                              descricao="m", contem_imagem_de_pessoa=False, autorizacao_registrada=False,
                              tamanho_maximo=10**6)
        url = f"/sistema/processos/{self.processo.pk}/anexos/{anexo.pk}/"
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)
        self.entrar(self.operador)
        resposta = self.client.get(url)
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("attachment", resposta["Content-Disposition"])
        self.assertTrue(EventoAuditoria.objects.filter(acao="processo.anexo_baixado").exists())

    def test_anexo_de_outro_processo_nao_abre(self):
        outro = regras.criar_processo(self.estoque, titulo="Outro", area=Area.OUTRA)
        anexo = regras.anexar(self.estoque, outro, SimpleUploadedFile("m.pdf", b"%PDF-1"), descricao="m",
                              contem_imagem_de_pessoa=False, autorizacao_registrada=False, tamanho_maximo=10**6)
        self.entrar(self.operador)
        self.assertEqual(self.client.get(f"/sistema/processos/{self.processo.pk}/anexos/{anexo.pk}/").status_code, 404)

    def test_sem_perfil_nao_ve_quadro(self):
        sem = usuario("sem_perfil")
        self.entrar(sem)
        self.assertEqual(self.client.get("/sistema/processos/").status_code, 403)


class RoteiroTest(TestCase):
    def test_telas_abrem_com_processos_sem_responsavel(self):
        call_command("carregar_roteiro", stdout=open("/dev/null", "w"))
        self.client.force_login(usuario("op", ADMINISTRATIVO))
        self.assertContains(self.client.get("/sistema/processos/"), "a definir")
        for p in Processo.objects.all():
            self.assertContains(self.client.get(f"/sistema/processos/{p.pk}/"), "Ainda não há procedimento escrito.")

    def test_carregar_roteiro_e_idempotente(self):
        call_command("carregar_roteiro", "--prazo", "2026-11-04", stdout=open("/dev/null", "w"))
        call_command("carregar_roteiro", stdout=open("/dev/null", "w"))
        self.assertEqual(Processo.objects.count(), len(PROCESSOS_INICIAIS))
        self.assertFalse(Processo.objects.exclude(estado=Estado.A_LEVANTAR).exists())
        self.assertEqual(Processo.objects.filter(fonte_conhecimento="Bárbara").count(), len(PROCESSOS_INICIAIS))
