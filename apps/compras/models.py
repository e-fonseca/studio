"""O que a loja decide comprar: sugestão de quem está no balcão, quantidade
ajustada pela gerência e os dados que vão no cabeçalho do pedido.

Diferente da tela de Sugestões, que é o sistema calculando em cima do número do
SET, isto aqui é a pessoa dizendo o que ela viu: o cliente pediu e não tinha,
acabou na prateleira, vai faltar no fim de semana. É informação que não está em
tabela nenhuma e que some quando fica só na conversa.

Cada sugestão guarda data, hora e quem escreveu (pedido do Edson, 07/10/2026), e
a gerência responde dizendo o que fez com ela. Nada disso vai para o SET.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class SugestaoDeCompra(models.Model):
    class Motivo(models.TextChoices):
        CLIENTE_PEDIU = "cliente_pediu", "Cliente pediu e não tinha"
        ACABOU = "acabou", "Acabou na prateleira"
        VAI_FALTAR = "vai_faltar", "Vai faltar"
        VENDE_BEM = "vende_bem", "Vende bem, vale ter mais"
        NOVIDADE = "novidade", "Novidade que vale experimentar"
        OUTRO = "outro", "Outro motivo"

    class Situacao(models.TextChoices):
        ABERTA = "aberta", "Aguardando a gerência"
        COMPRAR = "comprar", "Entrou na lista de compra"
        COMPRADA = "comprada", "Já foi comprada"
        DESCARTADA = "descartada", "Não vamos comprar"

    produto = models.CharField("produto", max_length=200)
    codigo = models.CharField("código no SET", max_length=60, blank=True)
    quantidade = models.DecimalField("quantidade sugerida", max_digits=12, decimal_places=3,
                                     null=True, blank=True)
    motivo = models.CharField(max_length=20, choices=Motivo.choices, default=Motivo.CLIENTE_PEDIU)
    observacao = models.TextField("observação", blank=True)
    fornecedor = models.CharField("fornecedor sugerido", max_length=200, blank=True)

    # Data, hora e quem escreveu: é o que a gerência olha para saber de quando é a
    # informação e com quem conversar sobre ela.
    criada_em = models.DateTimeField("data e hora", default=timezone.now)
    criada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
                                   related_name="sugestoes_de_compra")

    situacao = models.CharField(max_length=20, choices=Situacao.choices, default=Situacao.ABERTA)
    resposta = models.TextField("resposta da gerência", blank=True)
    respondida_em = models.DateTimeField(null=True, blank=True)
    respondida_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                       on_delete=models.SET_NULL, related_name="sugestoes_respondidas")

    class Meta:
        ordering = ["-criada_em", "-id"]
        verbose_name = "sugestão de compra"
        verbose_name_plural = "sugestões de compra"
        indexes = [models.Index(fields=["situacao", "-criada_em"])]
        permissions = [
            ("sugerir_compra", "Escrever sugestão de compra"),
            ("responder_sugestao", "Responder sugestão de compra"),
        ]

    def __str__(self):
        return self.produto

    @property
    def aberta(self):
        return self.situacao == self.Situacao.ABERTA

    @property
    def quem_escreveu(self):
        """O nome de quem escreveu, ou um recado em vez de vazio quando a conta saiu."""
        if self.criada_por is None:
            return "usuário removido"
        return self.criada_por.get_full_name() or self.criada_por.get_username()


class AjusteDeCompra(models.Model):
    """O que a gerência acrescenta (ou tira) da quantidade que o sistema sugeriu.

    Pedido do Edson em 20/10/2026: *"no campo de quantidade sugerida, adicionar
    quantidade manual, com a soma dos dois campos gera a quantidade total de cada
    produto por fornecedor"*. O que se guarda aqui é a PARCELA MANUAL, não o total:

        total = sugerida de hoje + a mais

    Guardar a parcela, e não o total, é o que faz a decisão da pessoa sobreviver à
    sincronização. Até a 1.36.0 o campo guardava o número final: quem escrevia 15
    porque um cliente encomendou 5 ficava com 15 mesmo quando a venda subia e o
    sistema passava a pedir 14 sozinho — a encomenda do cliente sumia dentro de um
    número fixo, e a tela só sabia avisar que "a conta mudou". Guardando o 5, o
    total vira 19 sozinho e a encomenda continua lá.

    `nao_comprar` é o "este não, agora": ele não se confunde com a parcela zero e
    não envelhece quando a sugestão muda, que era o defeito da convenção antiga de
    digitar 0.

    É dado NOSSO: não tem `importacao` e a sincronização não o refaz. Liga ao
    produto pelo código do SET, nunca por chave estrangeira, porque a foto do SET é
    apagada e refeita a cada sincronização e o ajuste tem que sobreviver a isso.
    """

    codigo = models.CharField("código do produto no SET", max_length=60, unique=True)
    # O total no momento em que foi salvo. Fica para a trilha e para o histórico; quem
    # manda na tela é `a_mais` somado à sugestão DE HOJE, que pode já ser outra.
    quantidade = models.DecimalField("quantidade total quando foi salva", max_digits=14,
                                     decimal_places=3)
    # A parcela manual, que é o que a pessoa digita. Negativa quando ela quer comprar
    # menos do que o sistema pediu, sem chegar a tirar o produto do pedido.
    a_mais = models.DecimalField(
        "quantidade a mais", max_digits=14, decimal_places=3, default=0,
        help_text="Somada à quantidade sugerida pelo sistema. Negativa para comprar menos.",
    )
    nao_comprar = models.BooleanField(
        "não comprar agora", default=False,
        help_text="Tira o produto do pedido sem apagar a linha da lista.",
    )
    sugerida = models.DecimalField(
        "quantidade que o sistema sugeria", max_digits=14, decimal_places=3, default=0,
        help_text="Guardada no momento do ajuste, para a tela mostrar de onde veio o total.",
    )
    observacao = models.CharField("observação", max_length=200, blank=True)

    ajustado_em = models.DateTimeField(default=timezone.now)
    ajustado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="ajustes_de_compra",
    )

    class Meta:
        ordering = ["codigo"]
        verbose_name = "quantidade ajustada"
        verbose_name_plural = "quantidades ajustadas"
        permissions = [
            ("ajustar_compra", "Mudar a quantidade a comprar na lista"),
            # 1.44.0: a lista de compra deixou o `importacao.ver_painel`, que abria todo
            # número da loja, para um perfil de Compras ver a lista sem ver o lucro.
            ("ver_compras", "Ver a lista de compra e o que levar ao fornecedor"),
        ]

    def __str__(self):
        return f"{self.codigo}: {self.quantidade}"

    def total_com(self, sugerida_agora):
        """O que vai no pedido: a sugestão de hoje mais a parcela manual.

        Nunca abaixo de zero — parcela negativa maior que a sugestão quer dizer "não
        quero isso", e o resultado disso é não comprar, não comprar ao contrário.
        """
        if self.nao_comprar:
            return Decimal("0")
        sugerida = Decimal(sugerida_agora or 0)
        return max(Decimal("0"), sugerida + (self.a_mais or Decimal("0")))

    def mudou_desde(self, sugerida_agora):
        """A conta do sistema mudou depois que alguém mexeu neste item?

        Com a soma, isso deixou de ser um alerta e virou informação: o total acompanha
        a conta nova sozinho. A tela usa para dizer de quanto para quanto a sugestão
        andou, não para desconfiar do número escolhido.
        """
        if sugerida_agora is None:
            return False
        return Decimal(sugerida_agora) != (self.sugerida or Decimal("0"))


class DadosDaEmpresa(models.Model):
    """O cabeçalho que vai no pedido ao fornecedor. Uma linha só, sempre a de pk=1.

    A loja se chama Studio Industrial e a nota sai pela razão social, que é outra
    (Edson, 14/10/2026). O fornecedor precisa das duas: conhece a loja pelo nome da
    porta e fatura para o CNPJ.

    Tudo isto é campo de tela, e não valor escrito no código, porque endereço e CNPJ
    mudam sem avisar e ninguém vai esperar uma versão nova do sistema por causa de
    um telefone. O que o Edson já informou vem preenchido; o resto fica em branco e
    o pedido simplesmente não imprime a linha vazia.
    """

    nome_fantasia = models.CharField(
        "nome da loja", max_length=120, default="Studio Industrial",
        help_text="Como o fornecedor conhece a loja. É o que aparece grande no pedido.",
    )
    razao_social = models.CharField(
        "razão social", max_length=160, default="Essenza",
        help_text="O nome que vai na nota fiscal, escrito como está registrado.",
    )
    documento = models.CharField(
        "CNPJ", max_length=24, blank=True,
        help_text="Sem ele o fornecedor não emite a nota. Ex.: 00.000.000/0001-00",
    )
    inscricao_estadual = models.CharField("inscrição estadual", max_length=24, blank=True)
    # O endereço FISCAL é o que vai na nota: é para ele que o fornecedor fatura.
    endereco = models.CharField(
        "endereço fiscal", max_length=200, default="Largo do Jesuítas, 64",
        help_text="O endereço que consta no CNPJ. É para ele que a nota é emitida.",
    )
    bairro = models.CharField("bairro", max_length=80, blank=True)
    cidade = models.CharField("cidade", max_length=80, blank=True)
    estado = models.CharField("estado (UF)", max_length=2, blank=True)
    cep = models.CharField("CEP", max_length=12, blank=True)
    # O endereço FÍSICO é onde a mercadoria desce do caminhão, e na Cabana não é o
    # mesmo (Edson, 19/10/2026): a loja fica no Largo dos Jesuítas e o CNPJ está na
    # Rua Claudionor Assis Dias. Mandar a carga para o endereço da nota é mandar a
    # carga para o lugar errado, e é o tipo de erro que só aparece no dia da entrega.
    endereco_entrega = models.CharField(
        "endereço de entrega", max_length=200, blank=True,
        help_text="Onde a mercadoria é recebida, quando não é o mesmo da nota.",
    )
    bairro_entrega = models.CharField("bairro da entrega", max_length=80, blank=True)
    cidade_entrega = models.CharField("cidade da entrega", max_length=80, blank=True)
    estado_entrega = models.CharField("UF da entrega", max_length=2, blank=True)
    cep_entrega = models.CharField("CEP da entrega", max_length=12, blank=True)
    telefone = models.CharField("telefone", max_length=40, blank=True)
    email = models.EmailField("e-mail", max_length=160, blank=True)
    observacao = models.TextField(
        "recado que sai em todo pedido", blank=True,
        help_text="Ex.: horário de recebimento, condição de pagamento combinada.",
    )

    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "dados da empresa"
        verbose_name_plural = "dados da empresa"

    def __str__(self):
        return self.nome_fantasia

    @classmethod
    def atual(cls):
        """A única linha, criada com os padrões na primeira vez que alguém olha."""
        registro, _ = cls.objects.get_or_create(pk=1)
        return registro

    @staticmethod
    def _uma_linha(endereco, bairro, cidade, estado, cep):
        """Endereço, bairro, cidade/UF e CEP numa linha, pulando o que está em branco."""
        cidade_uf = " - ".join(p for p in (cidade, estado) if p)
        return " · ".join(p for p in (endereco, bairro, cidade_uf, cep) if p)

    @property
    def linha_do_endereco(self):
        """O endereço FISCAL, que é o do faturamento."""
        return self._uma_linha(self.endereco, self.bairro, self.cidade,
                               self.estado, self.cep)

    @property
    def linha_da_entrega(self):
        """O endereço de ENTREGA, só quando ele existe e é diferente do fiscal.

        Vazio quer dizer "entrega no mesmo endereço da nota": o pedido então imprime
        uma linha só, em vez de repetir o mesmo endereço com dois rótulos.
        """
        if not self.endereco_entrega.strip():
            return ""
        linha = self._uma_linha(self.endereco_entrega, self.bairro_entrega,
                                self.cidade_entrega or self.cidade,
                                self.estado_entrega or self.estado, self.cep_entrega)
        return "" if linha == self.linha_do_endereco else linha

    @property
    def linha_do_contato(self):
        partes = [p for p in (self.telefone, self.email) if p]
        return " · ".join(partes)

    @property
    def falta_preencher(self):
        """O que o fornecedor vai sentir falta no papel, para a tela cobrar."""
        faltando = []
        if not self.documento:
            faltando.append("CNPJ")
        if not self.cidade:
            faltando.append("cidade")
        if not self.telefone and not self.email:
            faltando.append("telefone ou e-mail")
        return faltando


class PoliticaDeCompra(models.Model):
    """Os dois números da compra que a gerência decide, e não a conta. Uma linha só, pk=1.

    Pedido do Edson em 22/10/2026: *"deixar como padrão alerta de 30% para cada produto
    no estoque e destacar para os produtos mais vendidos, carro chefe da loja"*.

    * `alerta_percentual`: o produto entra em ALERTA quando o que ele tem (mais o que
      está a caminho) cai a esta porcentagem do estoque ideal, que é o estoque-alvo da
      conta de reposição. O padrão é 30. A conta de reposição já manda comprar bem
      antes disso — no ponto de reposição, perto de três quartos do ideal —, então o
      alerta não muda QUANTO comprar: ele diz o que não pode mais esperar.
    * `carros_chefe`: quantos produtos, contados do que mais faturou em doze meses para
      baixo, são o carro-chefe da loja. O padrão é 100: na foto de 20/09/2026 os cem
      primeiros eram um terço do faturamento, entre peles, tapetes de couro e mantas.

    Campo de tela e não constante no código pelo mesmo motivo do timbre do pedido: é
    decisão de gestão, e ninguém deveria esperar uma versão nova para mudar de 30 para 25.
    """

    alerta_percentual = models.PositiveSmallIntegerField(
        "alertar quando o estoque cair a (%) do ideal", default=30,
    )
    carros_chefe = models.PositiveSmallIntegerField(
        "quantos produtos são o carro-chefe", default=100,
    )
    atualizado_em = models.DateTimeField(auto_now=True)
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )

    ALERTA_MINIMO, ALERTA_MAXIMO = 5, 90
    CARROS_MINIMO, CARROS_MAXIMO = 10, 500

    class Meta:
        verbose_name = "política de compra"
        verbose_name_plural = "política de compra"

    def __str__(self):
        return f"alerta em {self.alerta_percentual}%, {self.carros_chefe} carros-chefe"

    @classmethod
    def atual(cls):
        """A política em vigor. Sem nada gravado, vale o padrão que ele pediu."""
        registro, _ = cls.objects.get_or_create(pk=1)
        return registro


class CompraGuiada(models.Model):
    """Uma compra montada pelas perguntas da compra guiada, com as respostas guardadas.

    Pedido do Edson em 02/11/2026: *"fazer formato tipo apresentação, pop up, só que com
    perguntas fechadas ou abertas (...) para formatar um pedido de compra para o
    fornecedor assertivo (...) a funcionária que trabalhava com essa parte saiu da empresa
    e não deixou nenhuma informação registrada"*.

    As respostas ficam guardadas por isso: cada compra guiada é o registro de COMO a
    compra foi decidida — para quanto tempo, com que venda de base, quais tipos, que
    orçamento, quais encomendas, quem respondeu. A próxima pessoa que comprar deste
    fornecedor lê aqui o que a anterior pensou, em vez de começar do zero.

    É dado NOSSO, como o pedido: não tem `importacao`, a sincronização não o refaz e nada
    vai para o SET. O pedido gerado fica pelo número (`pedido_numero`), que nunca é
    reaproveitado, e não por chave estrangeira entre os dois aplicativos.
    """

    class Situacao(models.TextChoices):
        ANDAMENTO = "andamento", "Em andamento"
        CONCLUIDA = "concluida", "Pedido gerado"
        DEIXADA = "deixada", "Deixada de lado"

    fornecedor = models.CharField("fornecedor", max_length=200)
    situacao = models.CharField(max_length=20, choices=Situacao.choices,
                                default=Situacao.ANDAMENTO)
    # As respostas, pergunta a pergunta (apps/compras/guiada.py diz quais são as chaves).
    respostas = models.JSONField("respostas", default=dict, blank=True)

    criada_em = models.DateTimeField(default=timezone.now)
    criada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="compras_guiadas",
    )
    atualizada_em = models.DateTimeField(auto_now=True)
    concluida_em = models.DateTimeField(null=True, blank=True)

    # Preenchidos quando o pedido sai: de que foto vieram os números, qual pedido nasceu,
    # quanto ele somou e as decisões numa frase, para a lista das compras já feitas.
    data_corte = models.DateField("dados conferidos em", null=True, blank=True)
    pedido_numero = models.PositiveIntegerField("número do pedido gerado", null=True, blank=True)
    valor = models.DecimalField("valor do pedido", max_digits=14, decimal_places=2,
                                default=Decimal("0"))
    resumo = models.CharField("as decisões, numa frase", max_length=500, blank=True)

    class Meta:
        ordering = ["-criada_em"]
        verbose_name = "compra guiada"
        verbose_name_plural = "compras guiadas"
        indexes = [
            models.Index(fields=["criada_por", "situacao", "-criada_em"]),
            models.Index(fields=["fornecedor", "-criada_em"]),
        ]

    def __str__(self):
        return f"Compra guiada {self.pk} · {self.fornecedor}"

    @property
    def em_andamento(self):
        return self.situacao == self.Situacao.ANDAMENTO
