"""Para onde o código do sistema é copiado, fora do servidor da loja.

Pedido do Edson em 14/10/2026: *"BACKUP = criar rotina de backup no github, conectar
automatico a cada atualizacao (./sistema)"*.

O que vai e o que NÃO vai, e por quê
------------------------------------
Vai o **código** do sistema: os arquivos que compõem o programa, mais a pasta docs.
É o que o GitHub serve para guardar, com histórico, e é o que não existe em nenhum
outro lugar além do servidor da loja e dos pacotes de instalação.

**Não vai o banco de dados.** Nele estão o nome dos clientes que o SET registra, o
extrato bancário importado e os anexos de nota fiscal dos fornecedores. GitHub é um
serviço fora da loja: mandar isso para lá, mesmo em repositório privado, é tirar dado
pessoal do servidor sem necessidade nenhuma. O backup do banco continua sendo o
`backup.ps1`, que roda às 23:30 e guarda 14 dias em `C:\\cabana-sistema\\backups`.

**Não vai segredo nenhum.** O `cabana.env` (com a SECRET_KEY e a senha do e-mail) e o
`pgpass.conf` ficam em `C:\\cabana-sistema\\config`, fora da pasta do programa, então
não entram nem por descuido. Ainda assim o envio monta a lista pelo que PODE ir, nunca
pelo que não pode: regra de exclusão esquecida manda o arquivo; regra de inclusão
esquecida só deixa de mandar.

O token fica cifrado como a senha do e-mail e o token do Telegram (apps/alertas/cifra.py).
"""

from django.conf import settings
from django.db import models

from apps.alertas import cifra

RAMO_PADRAO = "main"

# O repositório que o Edson indicou em 14/10/2026 ("fazer conexão com o diretório
# sistema, destinado para este projeto no github"). Vem preenchido na tela, como o SMTP
# da Hostinger vem em Alertas: assim só falta colar o token. Trocar na tela sobrescreve.
REPOSITORIO_PADRAO = "e-fonseca/sistema"


class ConfiguracaoDeBackup(models.Model):
    """Uma linha só, sempre a de pk=1, como os Dados da empresa."""

    repositorio = models.CharField(
        "repositório no GitHub", max_length=200, blank=True, default=REPOSITORIO_PADRAO,
        help_text="No formato dono/repositório, ou cole o endereço: "
                  "https://github.com/dono/repositorio",
    )
    ramo = models.CharField("ramo (branch)", max_length=80, default=RAMO_PADRAO)
    token_guardado = models.TextField(blank=True, default="")
    ativo = models.BooleanField(
        "mandar a cada atualização", default=False,
        help_text="Com isto ligado, cada atualização do sistema manda o código para o GitHub.",
    )

    ultimo_envio_em = models.DateTimeField(null=True, blank=True)
    ultimo_resultado = models.CharField(max_length=300, blank=True)
    ultimo_deu_certo = models.BooleanField(default=False)
    ultimo_commit = models.CharField(max_length=40, blank=True)
    ultimos_arquivos = models.PositiveIntegerField(default=0)

    # Quando o código chegou ao GitHub pela última vez. Separado de `ultimo_envio_em`,
    # que é a última TENTATIVA: com um token vencido, a tentativa é de hoje e o backup
    # é de três meses atrás, e é a segunda data que diz se a loja está coberta.
    ultimo_sucesso_em = models.DateTimeField(null=True, blank=True)
    # Até quando o token vale, lido do cabeçalho que o GitHub manda em toda resposta
    # (apps/backup/github.validade_do_token). Vazio quando o token não tem prazo.
    token_validade = models.DateField(null=True, blank=True)
    token_validade_lida_em = models.DateTimeField(null=True, blank=True)

    atualizado_em = models.DateTimeField(auto_now=True)
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        verbose_name = "backup no GitHub"
        verbose_name_plural = "backup no GitHub"
        permissions = [("configurar_backup", "Configurar o backup no GitHub")]

    def __str__(self):
        return self.repositorio or "backup no GitHub (não configurado)"

    @classmethod
    def atual(cls):
        registro, _ = cls.objects.get_or_create(
            pk=1, defaults={"ramo": RAMO_PADRAO, "repositorio": REPOSITORIO_PADRAO})
        return registro

    @property
    def token(self):
        return cifra.decifrar(self.token_guardado)

    @token.setter
    def token(self, texto):
        self.token_guardado = cifra.cifrar(texto)

    @property
    def tem_token(self):
        return bool(self.token_guardado)

    @property
    def dono_e_repositorio(self):
        """(dono, repositório) a partir do que foi digitado, ou (None, None).

        Aceita "dono/repo", o endereço do navegador e o endereço de clonar, porque é
        o que a pessoa tem na mão quando acaba de criar o repositório.
        """
        bruto = (self.repositorio or "").strip()
        if not bruto:
            return None, None
        for prefixo in ("https://github.com/", "http://github.com/", "git@github.com:",
                        "github.com/"):
            if bruto.lower().startswith(prefixo):
                bruto = bruto[len(prefixo):]
                break
        bruto = bruto.removesuffix(".git").strip("/")
        partes = [parte for parte in bruto.split("/") if parte]
        if len(partes) != 2:
            return None, None
        return partes[0], partes[1]

    @property
    def configurado(self):
        dono, repositorio = self.dono_e_repositorio
        return bool(dono and repositorio and self.tem_token)

    @property
    def falta_preencher(self):
        """O que a tela cobra antes de o envio poder funcionar."""
        faltando = []
        dono, repositorio = self.dono_e_repositorio
        if not (dono and repositorio):
            faltando.append("o repositório, no formato dono/repositório")
        if not self.tem_token:
            faltando.append("o token de acesso do GitHub")
        return faltando

    @property
    def endereco(self):
        dono, repositorio = self.dono_e_repositorio
        if not dono:
            return ""
        return f"https://github.com/{dono}/{repositorio}"
