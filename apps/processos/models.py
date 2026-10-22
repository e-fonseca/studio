"""Base de processos: captura do conhecimento operacional (briefing, seção 5)."""

import hashlib

from django.conf import settings
from django.db import models
from django.urls import reverse


class Area(models.TextChoices):
    ABERTURA_FECHAMENTO = "abertura_fechamento", "Abertura e fechamento"
    CADASTRO_PRODUTOS = "cadastro_produtos", "Cadastro de produtos, códigos e unidades"
    VARIACOES = "variacoes", "Variações artesanais"
    PRECOS_DESCONTOS = "precos_descontos", "Preços e descontos"
    VENDAS = "vendas", "Vendas"
    TROCAS_DEVOLUCOES = "trocas_devolucoes", "Trocas, devoluções e cancelamentos"
    RECEBIMENTO = "recebimento", "Recebimento e conferência"
    INVENTARIO = "inventario", "Inventários"
    QUEBRAS_PERDAS = "quebras_perdas", "Quebras e perdas"
    CONSIGNACAO = "consignacao", "Consignação"
    COMPRAS = "compras", "Compras, prazos e fornecedores"
    SAZONALIDADE = "sazonalidade", "Sazonalidade"
    CONTAS = "contas", "Contas e conciliações"
    RELATORIOS = "relatorios", "Relatórios utilizados"
    SITE = "site", "Rotinas do site (Nuvemshop e Bling)"
    EXCECOES = "excecoes", "Exceções e problemas recorrentes"
    OUTRA = "outra", "Outra"


class Processo(models.Model):
    class Estado(models.TextChoices):
        A_LEVANTAR = "a_levantar", "A levantar"
        EM_DOCUMENTACAO = "em_documentacao", "Em documentação"
        EM_TESTE = "em_teste", "Em teste por outra pessoa"
        VALIDADO = "validado", "Validado pela gestão"

    class Criticidade(models.TextChoices):
        ALTA = "alta", "Alta"
        MEDIA = "media", "Média"
        BAIXA = "baixa", "Baixa"

    titulo = models.CharField("título", max_length=200)
    area = models.CharField("área", max_length=30, choices=Area.choices)
    criticidade = models.CharField(max_length=10, choices=Criticidade.choices, default=Criticidade.MEDIA)
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.A_LEVANTAR, db_index=True)
    titular = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="responsável titular", null=True, blank=True,
        on_delete=models.PROTECT, related_name="processos_titular",
    )
    substituto = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="processos_substituto",
    )
    fonte_conhecimento = models.CharField(
        "quem conhece o processo hoje", max_length=150, blank=True,
        help_text="Ex.: Bárbara. Serve para planejar as entrevistas.",
    )
    prazo_coleta = models.DateField("prazo para coleta", null=True, blank=True)
    versao_atual = models.ForeignKey(
        "VersaoProcesso", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    versao_validada = models.ForeignKey(
        "VersaoProcesso", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    validado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    validado_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["prazo_coleta", "titulo"]
        permissions = [
            ("documentar_processo", "Pode cadastrar e documentar processos"),
            ("registrar_teste", "Pode registrar execução de teste de um processo"),
            ("validar_processo", "Pode validar processo em nome da gestão"),
            ("aprovar_regra", "Pode aprovar regras de processo"),
            ("ver_anexo", "Pode baixar anexos de processos"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["titulo", "area"], name="processo_titulo_area_unico"),
            models.CheckConstraint(
                condition=~models.Q(estado="validado")
                | (models.Q(validado_por__isnull=False) & models.Q(versao_validada__isnull=False)),
                name="processo_validado_tem_responsavel",
            ),
        ]

    def __str__(self):
        return f"{self.codigo} {self.titulo}"

    @property
    def codigo(self):
        return f"P-{self.pk:03d}" if self.pk else "P-novo"

    def get_absolute_url(self):
        return reverse("processos:detalhe", args=[self.pk])


class VersaoProcesso(models.Model):
    """Versão imutável do procedimento. Editar cria uma nova versão."""

    processo = models.ForeignKey(Processo, on_delete=models.PROTECT, related_name="versoes")
    numero = models.PositiveIntegerField()
    objetivo = models.TextField()
    gatilho = models.TextField("gatilho (o que dispara o processo)", blank=True)
    frequencia = models.CharField("frequência", max_length=120, blank=True)
    pre_requisitos = models.TextField("pré-requisitos", blank=True)
    passos = models.TextField("passos", help_text="Um passo por linha, em linguagem simples.")
    tela_origem = models.CharField("tela ou sistema de origem", max_length=200, blank=True)
    exemplos = models.TextField("exemplos anonimizados", blank=True)
    documentos_entrada = models.TextField("documentos de entrada", blank=True)
    documentos_saida = models.TextField("documentos de saída", blank=True)
    conferencias = models.TextField("conferências", blank=True)
    excecoes = models.TextField("exceções", blank=True)
    aprovacao_necessaria = models.TextField("aprovação necessária", blank=True)
    evidencia_conclusao = models.TextField("evidência de conclusão", blank=True)
    resumo_mudanca = models.CharField("o que mudou nesta versão", max_length=300)
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    criado_em = models.DateTimeField(auto_now_add=True)

    CAMPOS_CONTEUDO = [
        "objetivo", "gatilho", "frequencia", "pre_requisitos", "passos", "tela_origem", "exemplos",
        "documentos_entrada", "documentos_saida", "conferencias", "excecoes",
        "aprovacao_necessaria", "evidencia_conclusao",
    ]

    class Meta:
        ordering = ["processo", "-numero"]
        verbose_name = "versão do processo"
        verbose_name_plural = "versões do processo"
        constraints = [
            models.UniqueConstraint(fields=["processo", "numero"], name="versao_numero_unico"),
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionError("Versões de processo são imutáveis; crie uma nova versão.")
        super().save(*args, **kwargs)

    def lista_passos(self):
        return [linha.strip() for linha in self.passos.splitlines() if linha.strip()]

    def __str__(self):
        return f"{self.processo.codigo} v{self.numero}"


class Afirmacao(models.Model):
    """Separa o que foi dito, o que foi observado e o que a gestão aprovou."""

    class Tipo(models.TextChoices):
        DECLARACAO = "declaracao", "Declaração de quem executa hoje"
        OBSERVACAO = "observacao", "Observação prática"
        REGRA = "regra", "Regra aprovada pela gestão"

    processo = models.ForeignKey(Processo, on_delete=models.PROTECT, related_name="afirmacoes")
    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    texto = models.TextField()
    fonte = models.CharField("quem disse ou observou", max_length=150)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    registrado_em = models.DateTimeField(auto_now_add=True)
    aprovado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        ordering = ["tipo", "registrado_em"]
        verbose_name = "afirmação"
        verbose_name_plural = "afirmações"
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(tipo="regra") | models.Q(aprovado_por__isnull=False),
                name="regra_exige_aprovador",
            )
        ]


class ExecucaoTeste(models.Model):
    """Outra pessoa executa o procedimento usando só a documentação."""

    class Resultado(models.TextChoices):
        CONCLUIU = "concluiu", "Concluiu sem ajuda"
        CONCLUIU_COM_DIFICULDADE = "concluiu_dificuldade", "Concluiu, com dificuldades registradas"
        NAO_CONCLUIU = "nao_concluiu", "Não conseguiu concluir"

    processo = models.ForeignKey(Processo, on_delete=models.PROTECT, related_name="testes")
    versao = models.ForeignKey(VersaoProcesso, on_delete=models.PROTECT, related_name="testes")
    executor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    executado_em = models.DateTimeField(auto_now_add=True)
    resultado = models.CharField(max_length=24, choices=Resultado.choices)
    usou_somente_documentacao = models.BooleanField(
        "usei somente a documentação, sem ajuda de quem executa hoje", default=False
    )
    dificuldades = models.TextField(blank=True)

    class Meta:
        ordering = ["-executado_em"]
        verbose_name = "execução de teste"
        verbose_name_plural = "execuções de teste"

    @property
    def aprovado(self):
        return self.usou_somente_documentacao and self.resultado != self.Resultado.NAO_CONCLUIU


def caminho_anexo(instancia, nome):
    # Nome no disco não usa o nome enviado (evita traversal e colisões).
    return f"processos/{instancia.processo_id}/{instancia.sha256[:2]}/{instancia.sha256}"


class Anexo(models.Model):
    processo = models.ForeignKey(Processo, on_delete=models.PROTECT, related_name="anexos")
    arquivo = models.FileField(upload_to=caminho_anexo, max_length=200)
    nome_original = models.CharField(max_length=200)
    tipo = models.CharField(max_length=10)
    tamanho = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    descricao = models.CharField("descrição", max_length=200)
    contem_imagem_de_pessoa = models.BooleanField(
        "a imagem ou gravação mostra pessoas ou dados pessoais", default=False
    )
    autorizacao_registrada = models.BooleanField("a autorização de uso foi registrada", default=False)
    enviado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    enviado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-enviado_em"]
        constraints = [
            models.UniqueConstraint(fields=["processo", "sha256"], name="anexo_sem_duplicidade"),
            models.CheckConstraint(
                condition=models.Q(contem_imagem_de_pessoa=False) | models.Q(autorizacao_registrada=True),
                name="imagem_de_pessoa_exige_autorizacao",
            ),
        ]

    @staticmethod
    def calcular_sha256(arquivo):
        h = hashlib.sha256()
        for bloco in arquivo.chunks():
            h.update(bloco)
        arquivo.seek(0)
        return h.hexdigest()
