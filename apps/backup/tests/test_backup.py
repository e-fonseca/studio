"""O backup do código no GitHub: a lista do que vai, o envio e a tela.

Nenhum teste fala com a internet: o cliente do GitHub recebe a função que abre o
pedido, e aqui ela é um dublê que responde do dicionário.
"""

import base64
import io
import json
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.auditoria.models import EventoAuditoria
from apps.backup import envio as envio_servicos, github
from apps.backup.models import REPOSITORIO_PADRAO, ConfiguracaoDeBackup
from apps.contas.perfis import ADMINISTRACAO, ADMINISTRATIVO, VENDEDOR
from apps.core.fabricas import SENHA_TESTE, usuario


class GitHubDeMentira:
    """Responde como a API do GitHub e guarda o que foi pedido."""

    def __init__(self, ramo=None, arvore=None, arquivos=None):
        self.ramo_atual = ramo
        self.arvore_atual = arvore
        self.arquivos = arquivos or {}
        self.pedidos = []
        self.blobs = []
        self.arvores = []
        self.commits = []
        self.refs = []

    def __call__(self, pedido):
        caminho = pedido.full_url.split("/repos/dono/repo", 1)[-1]
        corpo = json.loads(pedido.data) if pedido.data else None
        self.pedidos.append((pedido.method, caminho, corpo))
        assert pedido.get_header("Authorization") == "Bearer segredo-do-token"

        if caminho.startswith("/git/ref/heads/"):
            return {"object": {"sha": self.ramo_atual}} if self.ramo_atual else None
        if caminho.startswith("/git/commits/") and pedido.method == "GET":
            return {"tree": {"sha": self.arvore_atual}}
        if caminho.startswith("/git/trees/") and pedido.method == "GET":
            return {"tree": [{"path": nome, "type": "blob", "sha": resumo}
                             for nome, resumo in self.arquivos.items()]}
        if caminho == "/git/blobs":
            self.blobs.append(corpo)
            return {"sha": f"blob{len(self.blobs)}"}
        if caminho == "/git/trees":
            self.arvores.append(corpo)
            return {"sha": "arvore-nova"}
        if caminho == "/git/commits":
            self.commits.append(corpo)
            return {"sha": "c0ffee" + "0" * 34}
        if caminho.startswith("/git/ref"):
            self.refs.append((pedido.method, caminho, corpo))
            return {}
        raise AssertionError(f"pedido inesperado: {pedido.method} {caminho}")

    def cliente(self):
        return github.GitHub("dono", "repo", "segredo-do-token", abrir=self)


class ResumoDeBlobTest(TestCase):
    def test_e_o_mesmo_resumo_que_o_git_calcula(self):
        """`git hash-object` de um arquivo com "hello\\n" dá este resumo."""
        self.assertEqual(github.resumo_de_blob(b"hello\n"),
                         "ce013625030ba8dba906f756967f9e9ca394464a")

    def test_arquivo_vazio(self):
        self.assertEqual(github.resumo_de_blob(b""),
                         "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391")


class OQueVaiNoBackupTest(TestCase):
    def arvore(self, raiz):
        for caminho, conteudo in (
            ("manage.py", "print(1)"),
            ("VERSAO", "1.31.0"),
            ("docs/mudancas.md", "# mudanças"),
            ("templates/base.html", "<html></html>"),
            ("static/css/sistema.css", "body{}"),
            ("static/img/logo.png", "\x89PNG"),
            ("apps/core/__pycache__/texto.cpython-311.pyc", "lixo"),
            ("var/anexos/nota-de-cliente.xml", "<nfe>CPF do cliente</nfe>"),
            ("logs/sistema.log", "linha de log"),
            ("backups/cabana.dump", "banco inteiro"),
            ("dados/copia-set/DADOS-SET.FDB", "banco do SET"),
            ("wheels/django.whl", "roda"),
        ):
            arquivo = raiz / caminho
            arquivo.parent.mkdir(parents=True, exist_ok=True)
            arquivo.write_text(conteudo, encoding="utf-8")

    def test_leva_codigo_e_deixa_dado_e_sobra_de_fora(self):
        import tempfile

        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            self.arvore(raiz)
            caminhos = {arquivo.caminho for arquivo in envio_servicos.arquivos_do_sistema(raiz)}
        self.assertEqual(caminhos, {
            "manage.py", "VERSAO", "docs/mudancas.md", "templates/base.html",
            "static/css/sistema.css", "static/img/logo.png",
        })

    def test_o_banco_e_o_anexo_nunca_entram(self):
        """É a razão de a lista ser por inclusão: anexo de nota tem CNPJ do fornecedor."""
        import tempfile

        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            self.arvore(raiz)
            caminhos = {a.caminho for a in envio_servicos.arquivos_do_sistema(raiz)}
        for proibido in ("var/anexos/nota-de-cliente.xml", "backups/cabana.dump",
                         "dados/copia-set/DADOS-SET.FDB", "logs/sistema.log"):
            self.assertNotIn(proibido, caminhos)

    def test_pasta_de_anexos_fora_do_padrao_tambem_fica_de_fora(self):
        """CABANA_MEDIA_ROOT pode apontar para dentro do programa; o nome não salva."""
        import tempfile

        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            guardados = raiz / "arquivos-da-loja"
            guardados.mkdir()
            (guardados / "nota.xml").write_text("<nfe/>", encoding="utf-8")
            (raiz / "manage.py").write_text("print(1)", encoding="utf-8")
            with override_settings(MEDIA_ROOT=str(guardados)):
                caminhos = {a.caminho for a in envio_servicos.arquivos_do_sistema(raiz)}
        self.assertEqual(caminhos, {"manage.py"})

    def test_arquivo_grande_demais_para_ser_codigo_fica_de_fora(self):
        import tempfile

        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            (raiz / "manage.py").write_text("print(1)", encoding="utf-8")
            (raiz / "enorme.json").write_text("x" * (envio_servicos.TAMANHO_MAXIMO + 1),
                                              encoding="utf-8")
            caminhos = {a.caminho for a in envio_servicos.arquivos_do_sistema(raiz)}
        self.assertEqual(caminhos, {"manage.py"})

    def test_o_sistema_de_verdade_tem_o_que_enviar(self):
        arquivos = envio_servicos.arquivos_do_sistema()
        caminhos = {arquivo.caminho for arquivo in arquivos}
        self.assertIn("VERSAO", caminhos)
        self.assertIn("manage.py", caminhos)
        self.assertGreater(len(arquivos), 100)
        self.assertFalse([c for c in caminhos if "__pycache__" in c])


class EnviarTest(TestCase):
    def arquivos(self):
        return [github.Arquivo("manage.py", b"print(1)"),
                github.Arquivo("VERSAO", b"1.31.0")]

    def test_repositorio_vazio_ganha_o_primeiro_commit_e_o_ramo(self):
        falso = GitHubDeMentira()
        resultado = falso.cliente().enviar(self.arquivos(), "main", "primeira")
        self.assertTrue(resultado.enviou)
        self.assertEqual(resultado.enviados, 2)
        self.assertEqual(falso.commits[0]["parents"], [])
        self.assertNotIn("base_tree", falso.arvores[0])
        self.assertEqual(falso.refs[0][0], "POST")

    def test_so_manda_o_arquivo_que_mudou(self):
        """O resumo do git é do conteúdo: o que não mudou nem sobe de novo."""
        iguais = {"manage.py": github.resumo_de_blob(b"print(1)"),
                  "VERSAO": github.resumo_de_blob(b"1.30.0")}
        falso = GitHubDeMentira(ramo="commit-velho", arvore="arvore-velha", arquivos=iguais)
        resultado = falso.cliente().enviar(self.arquivos(), "main", "versão nova")
        self.assertEqual(resultado.enviados, 1)
        self.assertEqual(falso.arvores[0]["tree"][0]["path"], "VERSAO")
        self.assertEqual(falso.arvores[0]["tree"][0]["content"], "1.31.0")
        self.assertEqual(falso.arvores[0]["base_tree"], "arvore-velha")
        self.assertEqual(falso.refs[0][0], "PATCH")

    def test_texto_vai_dentro_da_arvore_e_binario_vai_como_blob(self):
        """Um pedido por arquivo esbarrava no limite do GitHub (22/10/2026)."""
        falso = GitHubDeMentira()
        logo = b"\x89PNG\r\n\x1a\n\x00\x00"
        falso.cliente().enviar(self.arquivos() + [github.Arquivo("static/logo.png", logo)],
                               "main", "primeira")
        self.assertEqual(len(falso.blobs), 1)
        self.assertEqual(base64.b64decode(falso.blobs[0]["content"]), logo)
        por_caminho = {e["path"]: e for e in falso.arvores[0]["tree"]}
        self.assertEqual(por_caminho["manage.py"]["content"], "print(1)")
        self.assertNotIn("sha", por_caminho["manage.py"])
        self.assertEqual(por_caminho["static/logo.png"]["sha"], "blob1")

    def test_o_sistema_inteiro_sobe_em_poucos_pedidos_e_num_commit_so(self):
        """Quinhentos arquivos não podem virar quinhentas escritas."""
        arquivos = [github.Arquivo(f"apps/a{i}.py", (f"# {i}\n" + "x" * 6000).encode())
                    for i in range(500)]
        falso = GitHubDeMentira(ramo="c1", arvore="a1")
        resultado = falso.cliente().enviar(arquivos, "main", "primeira")
        self.assertEqual(resultado.enviados, 500)
        escritas = [p for p in falso.pedidos if p[0] != "GET"]
        self.assertLess(len(escritas), 15)
        self.assertGreater(len(falso.arvores), 1)
        self.assertEqual(falso.arvores[0]["base_tree"], "a1")
        for arvore in falso.arvores[1:]:
            self.assertEqual(arvore["base_tree"], "arvore-nova")
        self.assertEqual(len(falso.commits), 1)
        self.assertEqual(sum(len(a["tree"]) for a in falso.arvores), 500)

    def test_o_texto_enviado_e_o_mesmo_que_o_resumo_confere_depois(self):
        """Acento e fim de linha do Windows: se mudassem no caminho, o arquivo subiria
        de novo em toda atualização."""
        dados = "ação\r\nlinha".encode()
        falso = GitHubDeMentira()
        falso.cliente().enviar([github.Arquivo("LEIA-ME.txt", dados)], "main", "x")
        enviado = falso.arvores[0]["tree"][0]["content"].encode("utf-8")
        self.assertEqual(github.resumo_de_blob(enviado), github.resumo_de_blob(dados))

    def test_nada_mudou_nao_faz_commit_vazio(self):
        iguais = {arquivo.caminho: arquivo.resumo for arquivo in self.arquivos()}
        falso = GitHubDeMentira(ramo="commit-velho", arvore="arvore-velha", arquivos=iguais)
        resultado = falso.cliente().enviar(self.arquivos(), "main", "de novo")
        self.assertFalse(resultado.enviou)
        self.assertEqual(falso.commits, [])
        self.assertIn("Nada mudou", resultado.mensagem)

    def test_arquivo_apagado_no_servidor_sai_do_repositorio(self):
        existentes = {arquivo.caminho: arquivo.resumo for arquivo in self.arquivos()}
        existentes["apps/coisa_antiga.py"] = "a" * 40
        falso = GitHubDeMentira(ramo="c1", arvore="a1", arquivos=existentes)
        resultado = falso.cliente().enviar(self.arquivos(), "main", "limpeza")
        self.assertEqual(resultado.apagados, 1)
        apagado = [e for e in falso.arvores[0]["tree"] if e["sha"] is None]
        self.assertEqual(apagado[0]["path"], "apps/coisa_antiga.py")

    def test_sem_arquivo_nenhum_nao_envia(self):
        with self.assertRaises(github.NaoDeuCerto):
            GitHubDeMentira().cliente().enviar([], "main", "nada")

    def test_arvore_cortada_pelo_github_e_recusada(self):
        falso = GitHubDeMentira(ramo="c1", arvore="a1")
        falso.__call__ = None  # noqa: SLF001 - substituído abaixo

        def responder(pedido):
            caminho = pedido.full_url.split("/repos/dono/repo", 1)[-1]
            if caminho.startswith("/git/ref/heads/"):
                return {"object": {"sha": "c1"}}
            if caminho.startswith("/git/commits/"):
                return {"tree": {"sha": "a1"}}
            return {"tree": [], "truncated": True}

        cliente = github.GitHub("dono", "repo", "segredo-do-token", abrir=responder)
        with self.assertRaises(github.NaoDeuCerto) as erro:
            cliente.enviar(self.arquivos(), "main", "x")
        self.assertIn("arquivos demais", str(erro.exception))


class ORepositorioVazioTest(TestCase):
    """O que o GitHub responde de verdade num repositório recém-criado.

    O dublê dos outros testes devolve None para ramo que não existe, e por isso o
    primeiro envio sempre passou aqui dentro. O GitHub de verdade responde **409
    "Git Repository is empty."** — medido contra a API em 14/10/2026, no repositório
    que o Edson criou —, e esse 409 derrubava justamente o PRIMEIRO envio, que é o
    único que todo mundo faz. O recado mandava tentar de novo, e tentar de novo dava
    no mesmo, para sempre.

    Por isso estes testes não usam o dublê: eles montam a resposta HTTP como ela chega.
    """

    def resposta(self, codigo, mensagem):
        corpo = json.dumps({"message": mensagem}).encode()
        return HTTPError("https://api.github.com/x", codigo, mensagem, {},
                         io.BytesIO(corpo))

    def abrindo(self, erro):
        """`urlopen` trocado por um que levanta o erro, sem encostar na rede."""
        def falso(pedido, timeout=None):  # noqa: ARG001
            raise erro
        return mock.patch.object(github, "urlopen", falso)

    def pedido(self, metodo="GET"):
        from urllib.request import Request  # noqa: PLC0415
        return Request("https://api.github.com/x", method=metodo)

    def test_409_de_repositorio_vazio_e_lido_como_nao_ha_nada_ainda(self):
        with self.abrindo(self.resposta(409, "Git Repository is empty.")):
            self.assertIsNone(github._abrir(self.pedido()))  # noqa: SLF001

    def test_404_continua_sendo_nao_ha_nada_ainda(self):
        with self.abrindo(self.resposta(404, "Not Found")):
            self.assertIsNone(github._abrir(self.pedido()))  # noqa: SLF001

    def test_409_de_escrita_continua_sendo_erro(self):
        """Escrever funciona em repositório vazio, então 409 numa escrita é conflito."""
        with self.abrindo(self.resposta(409, "Reference cannot be updated")):
            with self.assertRaises(github.NaoDeuCerto) as erro:
                github._abrir(self.pedido("POST"))  # noqa: SLF001
        self.assertIn("ramo mudou", str(erro.exception))

    def test_409_de_leitura_que_nao_e_repositorio_vazio_continua_sendo_erro(self):
        with self.abrindo(self.resposta(409, "Reference cannot be updated")):
            with self.assertRaises(github.NaoDeuCerto):
                github._abrir(self.pedido())  # noqa: SLF001

    def test_limite_de_envios_do_github_nao_e_culpa_do_token(self):
        erro = self.resposta(403, "You have exceeded a secondary rate limit.")
        with self.abrindo(erro), self.assertRaises(github.NaoDeuCerto) as recusa:
            github._abrir(self.pedido("POST"))  # noqa: SLF001
        self.assertIn("pediu para esperar", str(recusa.exception))
        self.assertNotIn("permissão", str(recusa.exception))

    def test_o_motivo_sobrevive_a_ser_lido_duas_vezes(self):
        """O corpo do erro é um fluxo: quem lê primeiro leva tudo.

        O 409 é olhado duas vezes — para saber se é repositório vazio e para virar
        frase na tela. Sem guardar a leitura, a segunda vinha vazia e a tela mostrava
        um erro sem motivo nenhum.
        """
        with self.abrindo(self.resposta(409, "Reference cannot be updated")):
            with self.assertRaises(github.NaoDeuCerto) as erro:
                github._abrir(self.pedido())  # noqa: SLF001
        self.assertIn("Reference cannot be updated", str(erro.exception))

    def test_o_primeiro_envio_num_repositorio_vazio_de_verdade_vai_ate_o_fim(self):
        """O caminho inteiro, com o 409 no lugar em que o GitHub o põe."""
        escritas = []

        def responder(pedido):
            caminho = pedido.full_url.split("/repos/dono/repo", 1)[-1]
            if caminho.startswith("/git/ref/heads/"):
                # É aqui que o repositório vazio responde 409.
                return github._abrir(pedido)  # noqa: SLF001
            corpo = json.loads(pedido.data) if pedido.data else None
            escritas.append((pedido.method, caminho, corpo))
            return {"sha": "c0ffee" + "0" * 34}

        cliente = github.GitHub("dono", "repo", "segredo-do-token", abrir=responder)
        with self.abrindo(self.resposta(409, "Git Repository is empty.")):
            resultado = cliente.enviar(
                [github.Arquivo("VERSAO", b"1.33.1")], "main", "primeira")

        self.assertTrue(resultado.enviou)
        self.assertEqual(resultado.enviados, 1)
        metodos = {caminho: metodo for metodo, caminho, _ in escritas}
        self.assertEqual(metodos["/git/refs"], "POST")
        commit = [corpo for _, caminho, corpo in escritas if caminho == "/git/commits"][0]
        self.assertEqual(commit["parents"], [])

    def test_ramo_parecido_nao_passa_pelo_ramo_pedido(self):
        """Pedindo `main`, o GitHub pode devolver a LISTA dos parecidos: nenhum serve."""
        cliente = github.GitHub("dono", "repo", "t", abrir=lambda p: [{"ref": "refs/heads/main-velho"}])
        self.assertIsNone(cliente.ramo("main"))


class ConfiguracaoTest(TestCase):
    def test_entende_as_tres_formas_de_escrever_o_repositorio(self):
        for bruto in ("loja/cabana-sistema",
                      "https://github.com/loja/cabana-sistema",
                      "https://github.com/loja/cabana-sistema.git",
                      "git@github.com:loja/cabana-sistema.git"):
            configuracao = ConfiguracaoDeBackup(repositorio=bruto)
            self.assertEqual(configuracao.dono_e_repositorio, ("loja", "cabana-sistema"), bruto)

    def test_texto_que_nao_e_repositorio_nao_passa(self):
        for bruto in ("", "cabana", "https://github.com/", "a/b/c"):
            self.assertEqual(ConfiguracaoDeBackup(repositorio=bruto).dono_e_repositorio,
                             (None, None), bruto)

    def test_o_token_e_guardado_cifrado(self):
        configuracao = ConfiguracaoDeBackup.atual()
        configuracao.token = "ghp_segredo"
        configuracao.save()
        self.assertNotIn("ghp_segredo", configuracao.token_guardado)
        self.assertEqual(ConfiguracaoDeBackup.atual().token, "ghp_segredo")

    def test_diz_o_que_falta_antes_de_poder_enviar(self):
        """Desde a 1.32.0 o repositório já vem preenchido: o que falta é só o token."""
        configuracao = ConfiguracaoDeBackup.atual()
        self.assertEqual(configuracao.falta_preencher, ["o token de acesso do GitHub"])
        configuracao.token = "ghp_x"
        self.assertEqual(configuracao.falta_preencher, [])
        self.assertTrue(configuracao.configurado)

    def test_a_tela_nasce_com_o_repositorio_que_ele_indicou(self):
        """Pedido dele em 14/10/2026: "fazer conexão com o diretório sistema"."""
        self.assertEqual(ConfiguracaoDeBackup.atual().dono_e_repositorio,
                         ("e-fonseca", "sistema"))

    def test_repositorio_apagado_na_mao_volta_a_ser_cobrado(self):
        """Vir preenchido não é o mesmo que não poder ficar vazio."""
        configuracao = ConfiguracaoDeBackup.atual()
        configuracao.repositorio = ""
        self.assertEqual(configuracao.falta_preencher,
                         ["o repositório, no formato dono/repositório",
                          "o token de acesso do GitHub"])


class TelaTest(TestCase):
    def entrar(self, perfil=ADMINISTRACAO, nome="edson"):
        usuario(nome, perfil)
        self.client.login(username=nome, password=SENHA_TESTE)

    def test_a_tela_explica_que_o_banco_nao_vai(self):
        self.entrar()
        pagina = self.client.get(reverse("backup:painel"))
        self.assertContains(pagina, "banco de dados não vai")
        self.assertContains(pagina, "nomes")

    def test_a_tela_abre_com_o_repositorio_preenchido(self):
        """Como Alertas abre com o SMTP da Hostinger: o que sobra para ele é só o segredo."""
        self.entrar()
        pagina = self.client.get(reverse("backup:painel"))
        self.assertContains(pagina, 'value="e-fonseca/sistema"')
        self.assertContains(pagina, "Falta preencher: o token de acesso do GitHub")
        # E o passo a passo da tela não manda mais criar o repositório.
        self.assertContains(pagina, "ele já vem preenchido")

    def test_gravar_guarda_o_token_sem_mostrar_de_volta(self):
        self.entrar()
        self.client.post(reverse("backup:painel"), {
            "repositorio": "https://github.com/loja/cabana-sistema",
            "ramo": "main", "token": "ghp_segredo",
        })
        configuracao = ConfiguracaoDeBackup.atual()
        self.assertEqual(configuracao.repositorio, "https://github.com/loja/cabana-sistema")
        self.assertEqual(configuracao.token, "ghp_segredo")
        pagina = self.client.get(reverse("backup:painel"))
        self.assertNotContains(pagina, "ghp_segredo")

    def test_o_token_nao_entra_na_auditoria(self):
        self.entrar()
        self.client.post(reverse("backup:painel"), {
            "repositorio": "loja/cabana", "ramo": "main", "token": "ghp_segredo"})
        evento = EventoAuditoria.objects.filter(acao="backup.configurado").first()
        guardado = json.dumps([evento.antes, evento.depois])
        self.assertNotIn("ghp_segredo", guardado)
        self.assertNotIn("token", evento.depois)
        # O que a auditoria diz do token: que agora existe um.
        self.assertFalse(evento.antes["tem_token"])
        self.assertTrue(evento.depois["tem_token"])
        self.assertEqual(evento.antes["repositorio"], REPOSITORIO_PADRAO)
        self.assertEqual(evento.depois["repositorio"], "loja/cabana")

    def test_a_tela_abre_com_o_automatico_ja_marcado_antes_do_primeiro_token(self):
        """Quem cola um token de backup está ligando o backup."""
        self.entrar()
        pagina = self.client.get(reverse("backup:painel"))
        self.assertTrue(pagina.context["formulario"]["ativo"].value())

    def test_gravar_o_token_ja_liga_e_ja_manda_a_primeira_copia(self):
        """Gravar é a ação inteira: não existe segundo clique.

        Antes, o token entrava e a tela ficava dizendo que estava tudo preenchido e que
        nada tinha subido, esperando alguém achar o botão.
        """
        self.entrar()
        with mock.patch.object(envio_servicos, "enviar") as enviou:
            enviou.return_value = github.Resultado(
                enviou=True, commit="c" * 40, enviados=500, ao_todo=500,
                mensagem="500 arquivos enviados, commit ccccccc.")
            pagina = self.client.post(reverse("backup:painel"), {
                "repositorio": "loja/cabana", "ramo": "main", "ativo": "on",
                "token": "token-novo"}, follow=True)
        self.assertTrue(enviou.called)
        self.assertContains(pagina, "Cópia do programa ligada e primeira cópia no GitHub")
        self.assertTrue(ConfiguracaoDeBackup.atual().ativo)

    def test_token_recusado_na_primeira_copia_nao_apaga_o_que_foi_gravado(self):
        """Senão, token errado obrigaria a digitar o repositório tudo de novo."""
        self.entrar()
        with mock.patch.object(envio_servicos, "enviar") as enviou:
            enviou.side_effect = github.NaoDeuCerto("O GitHub recusou o token (401).")
            pagina = self.client.post(reverse("backup:painel"), {
                "repositorio": "loja/cabana", "ramo": "main", "ativo": "on",
                "token": "token-errado"}, follow=True)
        self.assertContains(pagina, "O GitHub recusou o token (401).")
        guardada = ConfiguracaoDeBackup.atual()
        self.assertTrue(guardada.tem_token)
        self.assertEqual(guardada.repositorio, "loja/cabana")

    def test_trocar_o_token_de_um_backup_que_ja_funciona_nao_reenvia_tudo(self):
        """Só a PRIMEIRA cópia sai do gravar; depois quem manda é a atualização."""
        configuracao = ConfiguracaoDeBackup.atual()
        configuracao.repositorio = "loja/cabana"
        configuracao.token = "token-velho"
        configuracao.ativo = True
        configuracao.ultimo_sucesso_em = timezone.now()
        configuracao.save()
        self.entrar()
        with mock.patch.object(envio_servicos, "enviar") as enviou:
            self.client.post(reverse("backup:painel"), {
                "repositorio": "loja/cabana", "ramo": "main", "ativo": "on",
                "token": "token-novo"})
        self.assertFalse(enviou.called)

    def test_nao_deixa_ligar_o_automatico_sem_token(self):
        self.entrar()
        pagina = self.client.post(reverse("backup:painel"), {
            "repositorio": "loja/cabana", "ramo": "main", "ativo": "on"})
        self.assertContains(pagina, "preencha o repositório e o token")
        self.assertFalse(ConfiguracaoDeBackup.atual().ativo)

    def test_repositorio_escrito_errado_e_recusado_na_hora(self):
        self.entrar()
        pagina = self.client.post(reverse("backup:painel"), {
            "repositorio": "cabana", "ramo": "main"})
        self.assertContains(pagina, "formato dono/repositório")

    def test_a_tela_so_oferece_apagar_o_token_depois_que_existe_um(self):
        self.entrar()
        self.assertNotContains(self.client.get(reverse("backup:painel")), "Apagar o token")
        configuracao = ConfiguracaoDeBackup.atual()
        configuracao.token = "ghp_x"
        configuracao.save()
        self.assertContains(self.client.get(reverse("backup:painel")), "Apagar o token")

    def test_apagar_o_token_limpa_o_guardado(self):
        self.entrar()
        configuracao = ConfiguracaoDeBackup.atual()
        configuracao.token = "ghp_x"
        configuracao.save()
        self.client.post(reverse("backup:painel"), {
            "repositorio": "loja/cabana", "ramo": "main", "apagar_token": "on"})
        self.assertFalse(ConfiguracaoDeBackup.atual().tem_token)

    def test_enviar_sem_configurar_explica_em_vez_de_quebrar(self):
        self.entrar()
        resposta = self.client.post(reverse("backup:enviar_agora"), follow=True)
        self.assertContains(resposta, "Antes de enviar")

    def test_so_a_gerencia_entra(self):
        for perfil, nome in ((ADMINISTRATIVO, "moizes"), (VENDEDOR, "balcao")):
            self.entrar(perfil, nome=nome)
            self.assertEqual(self.client.get(reverse("backup:painel")).status_code, 403, nome)
            self.client.logout()


class EnvioCompletoTest(TestCase):
    def configurar(self):
        configuracao = ConfiguracaoDeBackup.atual()
        configuracao.repositorio = "dono/repo"
        configuracao.token = "segredo-do-token"
        configuracao.ativo = True
        configuracao.save()
        return configuracao

    def test_guarda_o_resultado_e_registra_na_auditoria(self):
        configuracao = self.configurar()
        falso = GitHubDeMentira()
        resultado = envio_servicos.enviar(configuracao=configuracao, cliente=falso.cliente())
        self.assertTrue(resultado.enviou)
        configuracao.refresh_from_db()
        self.assertTrue(configuracao.ultimo_deu_certo)
        self.assertTrue(configuracao.ultimo_commit)
        self.assertIn("commit", configuracao.ultimo_resultado)
        self.assertTrue(EventoAuditoria.objects.filter(acao="backup.enviado").exists())

    def test_a_mensagem_do_commit_diz_a_versao_e_o_dia(self):
        configuracao = self.configurar()
        falso = GitHubDeMentira()
        envio_servicos.enviar(configuracao=configuracao, cliente=falso.cliente())
        self.assertIn("versão", falso.commits[0]["message"])

    def test_erro_do_github_fica_guardado_para_a_tela_mostrar(self):
        configuracao = self.configurar()

        def recusar(pedido):
            raise github.NaoDeuCerto("O GitHub recusou o token (401).")

        cliente = github.GitHub("dono", "repo", "x", abrir=recusar)
        with self.assertRaises(github.NaoDeuCerto):
            envio_servicos.enviar(configuracao=configuracao, cliente=cliente)
        configuracao.refresh_from_db()
        self.assertFalse(configuracao.ultimo_deu_certo)
        self.assertIn("401", configuracao.ultimo_resultado)
        self.assertTrue(EventoAuditoria.objects.filter(acao="backup.envio_falhou").exists())
