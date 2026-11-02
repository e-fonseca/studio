"""Registro das importações e a foto dos dados do SET que cada uma trouxe.

Plano A é a cópia do backup do banco do SET; plano B são os relatórios
exportados. As duas fontes gravam aqui no mesmo formato, então o painel não
precisa saber de onde o número veio. Nenhuma importação escreve no SET.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class Importacao(models.Model):
    """Uma execução da importação: o que entrou, quando e se deu certo."""

    class Origem(models.TextChoices):
        BANCO = "banco", "Cópia do backup do banco"
        RELATORIO = "relatorio", "Relatórios exportados"

    class Situacao(models.TextChoices):
        EM_ANDAMENTO = "em_andamento", "Em andamento"
        CONCLUIDA = "concluida", "Concluída"
        SEM_NOVIDADE = "sem_novidade", "Sem backup novo"
        FALHOU = "falhou", "Falhou"

    origem = models.CharField("origem dos dados", max_length=20, choices=Origem.choices)
    situacao = models.CharField(max_length=20, choices=Situacao.choices, default=Situacao.EM_ANDAMENTO)
    automatica = models.BooleanField("executada pela tarefa automática", default=False)
    # Importação pedida no botão "Forçar atualização com o último backup": releu o
    # backup mais recente mesmo sendo o mesmo da anterior. Fica registrado porque, no
    # histórico, é o que explica duas importações seguidas do mesmo arquivo.
    forcada = models.BooleanField("forçada com o último backup", default=False)
    acionada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="importacoes"
    )

    iniciada_em = models.DateTimeField(default=timezone.now)
    concluida_em = models.DateTimeField(null=True, blank=True)

    arquivo = models.CharField("arquivo de origem", max_length=500, blank=True)
    arquivo_modificado_em = models.DateTimeField("data do arquivo de origem", null=True, blank=True)
    arquivo_bytes = models.BigIntegerField(null=True, blank=True)

    # Até quando os dados vão. É isso que diz se a informação é de hoje ou de semanas atrás.
    data_corte = models.DateField("dados até", null=True, blank=True)
    # Desde quando esta foto guarda a venda mês a mês de cada produto, sempre no dia 1º.
    # Quem compara períodos precisa saber onde o histórico COMEÇA: sem isso, comparar doze
    # meses com os doze anteriores usaria um mês pela metade como se fosse inteiro. Fica
    # vazio nas fotos tiradas até a 1.29.0, e aí quem lê despreza o mês mais antigo, que
    # era justamente o pedaço (apps/compras/comparacao.py:_limites).
    mes_a_mes_desde = models.DateField("venda mês a mês desde", null=True, blank=True)
    produtos = models.IntegerField(default=0)
    dias_abertos_12m = models.IntegerField("dias com venda nos 12 meses", default=0)
    dias_abertos_90d = models.IntegerField("dias com venda nos 90 dias", default=0)

    etapa = models.CharField("etapa atual", max_length=60, blank=True)
    progresso = models.SmallIntegerField("progresso em porcentagem", default=0)
    mensagem = models.TextField(blank=True)
    detalhe = models.JSONField(default=dict, blank=True)

    # Log da execução: uma linha por passo, com hora. Fica no banco, e não em arquivo,
    # porque o serviço web e a tarefa agendada rodam separados e escreveriam o mesmo
    # arquivo ao mesmo tempo no Windows. Assim cada execução tem o seu próprio log,
    # visível na tela de importações e baixável como texto.
    log = models.TextField("log da execução", blank=True)
    versao_sistema = models.CharField("versão do sistema", max_length=40, blank=True)

    class Meta:
        ordering = ["-iniciada_em", "-id"]
        verbose_name = "importação"
        verbose_name_plural = "importações"
        # Até a 1.43.0 o `ver_painel` abria todo número da loja (37 pontos). Na 1.44.0 ele
        # ficou com os indicadores, e vendas, margem e importações ganharam permissão
        # própria, para um perfil de Compras ou de Estoque não levar o lucro da loja junto.
        # Quem tinha o `ver_painel` ganhou as três na migração contas.0008: ninguém perdeu
        # acesso. O nome em português de cada uma está em apps/contas/catalogo.py.
        permissions = [
            ("consultar_produtos", "Pode consultar produto e fornecedor no balcão"),
            ("executar_importacao", "Pode disparar a importação dos dados do SET"),
            ("ver_painel", "Pode ver os indicadores da loja"),
            ("ver_vendas", "Pode ver as vendas do dia e o ticket médio"),
            ("ver_margem", "Pode ver custo e margem dos produtos"),
            ("ver_importacoes", "Pode ver o histórico das importações"),
        ]
        indexes = [models.Index(fields=["situacao", "-iniciada_em"])]

    def __str__(self):
        return f"{self.get_origem_display()} em {timezone.localtime(self.iniciada_em):%d/%m/%Y %H:%M}"

    @property
    def duracao_segundos(self):
        if not self.concluida_em:
            return None
        return int((self.concluida_em - self.iniciada_em).total_seconds())

    @property
    def deu_certo(self):
        return self.situacao == self.Situacao.CONCLUIDA

    @property
    def linhas_do_log(self):
        return [linha for linha in self.log.splitlines() if linha.strip()]

    def anotar(self, texto):
        """Acrescenta uma linha ao log, com a hora local na frente."""
        agora = timezone.localtime()
        self.log = f"{self.log}[{agora:%d/%m/%Y %H:%M:%S}] {texto}\n"
        return self.log

    def idade_dos_dados(self, hoje=None):
        """Quantos dias separam a data de corte de hoje. None quando não há data."""
        if not self.data_corte:
            return None
        return ((hoje or timezone.localdate()) - self.data_corte).days


class ProdutoImportado(models.Model):
    """Foto de um produto no momento da importação: saldo, vendas e compras.

    Quantidades em unidades do produto e valores em reais. O saldo vem do SET e,
    enquanto a loja não fizer a contagem física, pode não bater com a prateleira.
    """

    importacao = models.ForeignKey(Importacao, on_delete=models.CASCADE, related_name="itens")
    codigo = models.CharField("código do produto", max_length=60)
    descricao = models.CharField(max_length=200, blank=True)
    grupo = models.CharField(max_length=100, blank=True)
    fornecedor = models.CharField("fornecedor da última compra", max_length=200, blank=True)
    # O SET gera um código de barras próprio para quase todo produto (11.268 de 11.274 na
    # cópia de 20/09/2026) e é ele que vai impresso na etiqueta da prateleira. É o que o
    # leitor devolve no balcão, então a consulta e a contagem procuram por aqui.
    codigo_barras = models.CharField("código de barras", max_length=40, blank=True, db_index=True)
    situacao_set = models.CharField("situação no SET", max_length=40, blank=True)

    estoque = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    reservado = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    custo = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    preco_venda = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    estoque_minimo_set = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    # O campo "% de lucro" do cadastro do SET (PLUCRO). É markup sobre o custo, apesar
    # do nome: fica guardado como está no SET para a tela poder comparar o que está
    # escrito lá com o que o preço de hoje realmente dá.
    markup_set = models.DecimalField(
        "% de lucro gravado no SET", max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="PLUCRO do SET. É markup sobre o custo, não margem sobre a venda.",
    )

    vendas_12m = models.DecimalField("unidades vendidas em 12 meses", max_digits=14, decimal_places=3, default=0)
    vendas_90d = models.DecimalField("unidades vendidas em 90 dias", max_digits=14, decimal_places=3, default=0)
    receita_12m = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    custo_vendido_12m = models.DecimalField(
        "custo do que foi vendido em 12 meses", max_digits=14, decimal_places=2, default=0,
        help_text="Soma de quantidade x custo gravado no item da venda, no dia da venda.",
    )
    receita_com_custo_12m = models.DecimalField(
        "receita dos itens que têm custo gravado", max_digits=14, decimal_places=2, default=0,
        help_text="Parte da receita de 12 meses comparável com o custo acima.",
    )
    compras_12m = models.DecimalField("unidades compradas em 12 meses", max_digits=14, decimal_places=3, default=0)
    valor_compras_12m = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    pedido_em_aberto = models.DecimalField(
        "unidades em pedido de compra ainda não recebido", max_digits=14, decimal_places=3, default=0,
        help_text="Mercadoria a caminho: compras do SET com situação Pendente.",
    )

    ultima_venda = models.DateField(null=True, blank=True)
    ultima_compra = models.DateField(null=True, blank=True)
    prazo_reposicao_dias = models.IntegerField(
        "prazo de reposição em dias", null=True, blank=True,
        help_text="Mediana entre pedido e entrega nas compras do fornecedor. Vazio quando não há histórico.",
    )
    prazo_estimado = models.BooleanField(
        "prazo vem da média da loja", default=False,
        help_text="Verdadeiro quando o fornecedor tem compras demais de menos para formar prazo próprio.",
    )

    class Meta:
        ordering = ["codigo"]
        verbose_name = "produto importado"
        verbose_name_plural = "produtos importados"
        constraints = [
            models.UniqueConstraint(fields=["importacao", "codigo"], name="produto_unico_por_importacao"),
        ]
        indexes = [models.Index(fields=["importacao", "grupo"])]

    def __str__(self):
        return f"{self.codigo} {self.descricao}".strip()


class CompraImportada(models.Model):
    """Uma compra do SET: a nota ou o pedido inteiro, com fornecedor, data e valor.

    O produto importado já guarda o total comprado em 12 meses; isto aqui é a compra em si,
    que é o que a gerência olha para responder "quando foi a última vez que compramos deste
    fornecedor e o que veio nela".
    """

    importacao = models.ForeignKey(Importacao, on_delete=models.CASCADE, related_name="compras")
    id_set = models.IntegerField("id no SET")
    numero = models.CharField("número da compra", max_length=40, blank=True)
    fornecedor = models.CharField(max_length=200, blank=True)
    comprador = models.CharField("quem comprou", max_length=200, blank=True)
    situacao = models.CharField("situação no SET", max_length=40, blank=True)
    # Pendente no SET é mercadoria a caminho, não compra feita. Fica separada na tela.
    pendente = models.BooleanField(default=False)

    data_pedido = models.DateField(null=True, blank=True)
    data_nota = models.DateField(null=True, blank=True)
    data_entrega = models.DateField(null=True, blank=True)

    valor_produtos = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    valor_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    nota_fiscal = models.CharField("nota fiscal", max_length=40, blank=True)
    itens = models.IntegerField("quantidade de itens", default=0)

    class Meta:
        # O id do SET cresce com o tempo, então a ordem decrescente já é da mais nova
        # para a mais velha; quem precisa da data exata ordena por ela na consulta.
        ordering = ["-id_set"]
        verbose_name = "compra importada"
        verbose_name_plural = "compras importadas"
        constraints = [
            models.UniqueConstraint(fields=["importacao", "id_set"], name="compra_unica_por_importacao"),
        ]
        indexes = [models.Index(fields=["importacao", "fornecedor"])]

    def __str__(self):
        return f"{self.numero} {self.fornecedor}".strip()

    @property
    def data(self):
        """A data que vale para a loja: a da nota quando existe, senão a do pedido."""
        return self.data_nota or self.data_pedido

    @property
    def dias_ate_entregar(self):
        if not self.data_entrega or not self.data_pedido:
            return None
        return (self.data_entrega - self.data_pedido).days


class ItemCompraImportada(models.Model):
    """Uma linha da compra: produto, quantidade e quanto custou."""

    compra = models.ForeignKey(CompraImportada, on_delete=models.CASCADE, related_name="linhas")
    codigo = models.CharField("código do produto", max_length=60)
    descricao = models.CharField(max_length=200, blank=True)
    quantidade = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    custo_unitario = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    custo_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        ordering = ["-custo_total", "id"]
        verbose_name = "item de compra importada"
        verbose_name_plural = "itens de compra importada"

    def __str__(self):
        return f"{self.codigo} {self.descricao}".strip()


class VendaImportada(models.Model):
    """Uma venda do SET, só com o que o ticket médio precisa.

    O produto importado já guarda quanto vendeu em 12 meses; isto aqui é a venda em
    si, que é o que responde "quanto o cliente gasta por compra". Guardar venda a
    venda, e não só a soma do mês, é o que deixa filtrar por forma de pagamento, por
    vendedor e por dia da semana sem precisar reimportar.

    LGPD: a tabela do SET tem nome do cliente, nome do comprador e CPF do comprador.
    Nada disso vem para cá. O que entra é data, hora, valor, desconto, forma de
    pagamento e o vendedor, que é gente da loja e não cliente. Há teste que falha se
    alguém acrescentar um campo de cliente aqui.
    """

    importacao = models.ForeignKey(Importacao, on_delete=models.CASCADE, related_name="vendas")
    id_set = models.IntegerField("id no SET")
    numero = models.CharField("número da venda", max_length=40, blank=True)
    data = models.DateField()
    hora = models.CharField("hora da venda", max_length=8, blank=True)
    # 0 é domingo, como no Firebird e como a tela mostra. Gravado na importação para a
    # consulta não ter que calcular dia da semana em 16 mil linhas a cada filtro.
    dia_da_semana = models.SmallIntegerField("dia da semana", default=0)
    valor = models.DecimalField("total da venda", max_digits=14, decimal_places=2, default=0)
    desconto = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    forma_pagamento = models.CharField("forma de pagamento", max_length=60, blank=True)
    vendedor = models.CharField(max_length=200, blank=True)

    # Os três de baixo entraram na 1.46.0, para o controle de desconto (pedido do Edson em
    # 02/11/2026: "controlar os descontos para que os funcionários não deem desconto sem
    # parâmetros só objetivando a premiação"). Venda importada antes fica com eles vazios
    # até a importação seguinte.
    #
    # O total dos produtos é o que a venda dava ANTES do desconto dado no fechamento
    # (VENDAS.TOTALPROD): é a base da porcentagem do desconto.
    total_produtos = models.DecimalField("total dos produtos, antes do desconto",
                                         max_digits=14, decimal_places=2, default=0)
    # Quem registrou o recebimento no caixa do SET (ICAIXA.USUARIO). O vendedor da venda
    # está vazio desde abril de 2026; o caixa tem o nome em todo recebimento, e é quem
    # fecha a venda que dá o desconto.
    recebido_por = models.CharField("quem recebeu no caixa", max_length=50, blank=True)
    # As partes do pagamento (FATVENDAS), {"PIX": "150.00", "CARTAO CREDITO": "50.00"}. A
    # venda paga parte no PIX e parte no cartão tem desconto permitido só na parte à vista.
    formas_pagas = models.JSONField("partes do pagamento", default=dict, blank=True)

    class Meta:
        ordering = ["-data", "-id_set"]
        verbose_name = "venda importada"
        verbose_name_plural = "vendas importadas"
        constraints = [
            models.UniqueConstraint(fields=["importacao", "id_set"], name="venda_unica_por_importacao"),
        ]
        indexes = [
            models.Index(fields=["importacao", "data"]),
            models.Index(fields=["importacao", "forma_pagamento"]),
        ]

    def __str__(self):
        return f"{self.numero} {self.data:%d/%m/%Y}".strip()


class ItemVendaImportada(models.Model):
    """Um produto dentro de uma venda: o que saiu, por quanto, e quanto custava no dia.

    Pedido do Edson em 11/10/2026: a relação dos produtos vendidos no dia, com custo,
    valor de venda, lucro em reais e em porcentagem. O produto importado não responde
    isso — ele guarda a soma de 12 meses, não o dia —, então o item da venda passou a
    ser importado junto do cabeçalho.

    O custo é o do DIA DA VENDA (IVENDAS.PRECOCUSTO), não o do cadastro de hoje: é o que
    torna o lucro do dia o lucro que a loja realizou. Quando o SET não o gravou, fica
    vazio de propósito; item sem custo não vira lucro cheio.

    **E o SET parou de gravar.** Na cópia de 20/09/2026, até 24/08/2026 faltava custo em
    0,5% dos itens; de 25/08/2026 em diante falta em 70% a 100% deles, todo dia. Com a
    regra "sem custo fica fora da conta", o dia que a loja abre na tela ficaria sem lucro
    nenhum. Então o item carrega DOIS custos:

    - `custo_unitario` / `custo_total`: o que o SET gravou na venda. É o custo realizado.
    - `custo_cadastro_unitario` / `custo_estimado_total`: o custo do produto no cadastro
      no momento da importação, que cobre 90% dos itens sem custo. É ESTIMATIVA, e a tela
      e o relatório marcam a linha como estimada.

    Quando o produto não está mais no cadastro, os dois ficam vazios e a linha aparece
    como sem custo, fora da conta do lucro.
    """

    venda = models.ForeignKey(VendaImportada, on_delete=models.CASCADE, related_name="itens")
    codigo = models.CharField("código do produto", max_length=60, db_index=True)
    # Descrição e grupo vêm copiados do cadastro no momento da importação: a foto do dia
    # é o que o relatório mostra, e evita uma consulta por item para escrever a linha.
    descricao = models.CharField(max_length=200, blank=True)
    grupo = models.CharField(max_length=100, blank=True)

    quantidade = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    valor_total = models.DecimalField("valor vendido", max_digits=14, decimal_places=2, default=0)
    custo_unitario = models.DecimalField(
        "custo no dia da venda", max_digits=14, decimal_places=4, null=True, blank=True,
        help_text="Vazio quando o SET não gravou o custo naquele item.",
    )
    custo_total = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    # O custo do cadastro, copiado na importação. Serve de estimativa quando o SET não
    # gravou o custo da venda, e fica vazio quando o produto saiu do cadastro.
    custo_cadastro_unitario = models.DecimalField(
        "custo do cadastro na importação", max_digits=14, decimal_places=4,
        null=True, blank=True,
        help_text="Usado como estimativa quando o SET não gravou o custo da venda.",
    )
    custo_estimado_total = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    # Desde a 1.46.0: o preço cobrado (IVENDAS.VALORPROD) e o de tabela. Mudar o preço do
    # produto no caixa é desconto que NÃO aparece no desconto da venda; é com os dois que
    # ele aparece. O SET parou de gravar o preço de tabela no item em julho de 2026
    # (IVENDAS.PRECOVENDA vazio em 3.563 dos 4.068 itens de julho): aí vale o do cadastro
    # no momento da importação, e a linha fica marcada como estimada, como o custo.
    preco_unitario = models.DecimalField("preço cobrado", max_digits=14, decimal_places=4,
                                         null=True, blank=True)
    preco_tabela = models.DecimalField("preço de tabela", max_digits=14, decimal_places=4,
                                       null=True, blank=True)
    preco_tabela_do_cadastro = models.BooleanField(
        "preço de tabela tirado do cadastro", default=False,
        help_text="O SET não gravou o preço de tabela na venda; vale o do cadastro na importação.",
    )

    class Meta:
        ordering = ["id"]
        verbose_name = "item de venda importado"
        verbose_name_plural = "itens de venda importados"
        indexes = [models.Index(fields=["venda", "codigo"])]

    def __str__(self):
        return f"{self.codigo} {self.descricao}".strip()

    @property
    def tem_custo(self):
        """Dá para dizer quanto custou, mesmo que por estimativa?"""
        return self.custo_total is not None or self.custo_estimado_total is not None

    @property
    def custo_do_dia(self):
        return self.custo_total is not None

    @property
    def custo_usado(self):
        """O melhor custo que existe para este item: o da venda, senão o do cadastro."""
        if self.custo_total is not None:
            return self.custo_total
        return self.custo_estimado_total

    @property
    def estimado(self):
        """O custo veio do cadastro de hoje, e não da venda."""
        return self.custo_total is None and self.custo_estimado_total is not None

    @property
    def lucro(self):
        """Quanto sobrou neste item. None quando não há custo nenhum para comparar."""
        custo = self.custo_usado
        if custo is None:
            return None
        return self.valor_total - custo


class VendaMensalDoProduto(models.Model):
    """Quanto cada produto vendeu em cada mês, dois anos para trás.

    Pedido do Edson em 14/10/2026: "análise de sugestão de compra de mercadorias precisa
    além dos últimos meses com filtros, também permitir comparar com o mesmo período do
    ano anterior".

    O produto importado guarda a soma de 12 meses, que não responde "e no mesmo período
    do ano passado?". O item da venda responderia, mas só traz 12 meses e sairia caro em
    toda consulta. Esta tabela é a soma pronta, por produto e por mês: 11 mil produtos
    vezes 24 meses são dezenas de milhares de linhas, e qualquer comparação de período
    vira uma consulta só.

    É foto do SET como qualquer outra: tem `importacao` e é refeita a cada sincronização,
    e a limpeza automática a apaga junto com o resto da foto antiga.
    """

    importacao = models.ForeignKey(Importacao, on_delete=models.CASCADE,
                                   related_name="vendas_por_mes")
    codigo = models.CharField("código do produto", max_length=60, db_index=True)
    ano = models.SmallIntegerField()
    mes = models.SmallIntegerField()
    unidades = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    receita = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        ordering = ["codigo", "ano", "mes"]
        verbose_name = "venda do produto no mês"
        verbose_name_plural = "vendas do produto por mês"
        constraints = [
            models.UniqueConstraint(fields=["importacao", "codigo", "ano", "mes"],
                                    name="venda_mensal_unica_por_importacao"),
        ]
        indexes = [models.Index(fields=["importacao", "ano", "mes"])]

    def __str__(self):
        return f"{self.codigo} {self.mes:02d}/{self.ano}"
