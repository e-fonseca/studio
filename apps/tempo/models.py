"""O tempo que fez em cada dia, para cruzar com o que a loja vendeu.

Pedido do Edson em 14/10/2026: "as mudanças climáticas têm impacto no nosso negócio na
loja física, portanto queremos que grave de alguma forma no sistema a condição climática
do dia para fazer uma avaliação mais analítica dos impactos".

A loja é física e vende quase tudo no fim de semana e em feriado. Dia de chuva num
sábado não é o mesmo prejuízo que dia de chuva numa terça, e sem o tempo gravado dia a
dia essa diferença não dá para medir — ninguém se lembra, meses depois, de que choveu.

Dois caminhos para o mesmo lugar, porque um só não se sustenta:

- **O servidor busca sozinho**, uma vez por dia, num serviço de meteorologia aberto que
  não pede cadastro nem chave. Precisa das coordenadas da loja, que são campo de tela.
- **Alguém escreve na tela.** É o que vale quando a internet falha e é o que o serviço
  nunca sabe: "choveu só de manhã", "feriado", "teve evento na praça". O que a pessoa
  escreve nunca é apagado pela busca automática.

Isto é dado NOSSO: não tem `importacao`, não vem do SET e a sincronização não o refaz.
A chave é a data, que é o que liga ao que a loja vendeu no dia.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


def _numero(valor):
    """12,0 vira "12" e 17,5 vira "17,5": aqui se escreve número como em português.

    O f-string de um Decimal sai "12.0 mm" e "19.0 a 30.0 graus", que ninguém escreve
    assim — e a casa decimal de um milímetro de chuva não muda decisão nenhuma.
    """
    texto = f"{valor:f}".rstrip("0").rstrip(".")
    return (texto or "0").replace(".", ",")


class TempoDoDia(models.Model):
    """O tempo de um dia. Uma linha por data, venha ela da internet ou da tela."""

    class Condicao(models.TextChoices):
        SOL = "sol", "Sol"
        NUBLADO = "nublado", "Nublado"
        CHUVA = "chuva", "Chuva"
        CHUVA_FORTE = "chuva_forte", "Chuva forte"
        TEMPESTADE = "tempestade", "Tempestade"

    class Origem(models.TextChoices):
        AUTOMATICA = "automatica", "Buscado pelo sistema"
        PESSOA = "pessoa", "Escrito por alguém da loja"

    data = models.DateField(unique=True)
    condicao = models.CharField("condição", max_length=20, choices=Condicao.choices, blank=True)
    temperatura_minima = models.DecimalField("temperatura mínima", max_digits=5, decimal_places=1,
                                             null=True, blank=True)
    temperatura_maxima = models.DecimalField("temperatura máxima", max_digits=5, decimal_places=1,
                                             null=True, blank=True)
    chuva_mm = models.DecimalField("chuva em milímetros", max_digits=6, decimal_places=1,
                                   null=True, blank=True)
    feriado = models.BooleanField("feriado ou data especial", default=False)
    observacao = models.CharField(
        "o que mais aconteceu no dia", max_length=200, blank=True,
        help_text="O que o serviço de meteorologia não sabe: feriado, evento na cidade, "
                  "rua interditada, loja fechada.",
    )

    origem = models.CharField(max_length=20, choices=Origem.choices, default=Origem.PESSOA)
    # Marcado quando alguém da loja escreveu: a busca automática não passa por cima disso.
    escrito_a_mao = models.BooleanField(default=False)
    # Dia que ainda não aconteceu (ou está acontecendo): é previsão, não medição. Fica
    # guardado porque é com ele que a loja se prepara para o fim de semana, mas NUNCA
    # entra na conta de quanto a chuva custa — média de previsão não mede nada. A busca
    # do dia seguinte troca a previsão pelo dia fechado e a marca cai sozinha.
    previsao = models.BooleanField("é previsão, o dia ainda não fechou", default=False)
    atualizado_em = models.DateTimeField(default=timezone.now)
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="dias_de_tempo",
    )

    class Meta:
        ordering = ["-data"]
        verbose_name = "tempo do dia"
        verbose_name_plural = "tempo dos dias"
        permissions = [("anotar_tempo", "Escrever o tempo do dia na tela")]
        indexes = [models.Index(fields=["condicao"])]

    def __str__(self):
        return f"{self.data:%d/%m/%Y} {self.get_condicao_display()}".strip()

    @property
    def choveu(self):
        """Choveu a ponto de mudar o movimento da loja?

        Um milímetro é garoa e não esvazia loja; a conta usa o que a pessoa marcou como
        condição e, quando não há condição, o volume de chuva.
        """
        if self.condicao in (self.Condicao.CHUVA, self.Condicao.CHUVA_FORTE,
                             self.Condicao.TEMPESTADE):
            return True
        if self.condicao:
            return False
        return (self.chuva_mm or Decimal("0")) >= Decimal("1")

    @property
    def resumo(self):
        """Uma linha para a tabela: "Chuva forte · 18 mm · 17 a 22 graus".

        Não diz que é previsão: quem mostra dia previsto é sempre um quadro que já
        avisa isso em cima, e repetir a palavra em cada linha só gasta a largura do
        celular, onde cada dia é uma faixa de 390 px.
        """
        partes = []
        if self.condicao:
            partes.append(self.get_condicao_display())
        if self.chuva_mm:
            partes.append(f"{_numero(self.chuva_mm)} mm")
        if self.temperatura_minima is not None and self.temperatura_maxima is not None:
            partes.append(f"{_numero(self.temperatura_minima)} a "
                          f"{_numero(self.temperatura_maxima)} graus")
        if self.feriado:
            partes.append("feriado")
        return " · ".join(partes) or "sem registro"


class ConfiguracaoDoTempo(models.Model):
    """Onde fica a loja e se o sistema pode buscar o tempo sozinho. Uma linha só, pk=1.

    Até a 1.28.0 isto só funcionava com a latitude e a longitude digitadas à mão, pegas
    no Google Maps. Era pedir a alguém que não é técnico dois números de seis casas
    decimais para a busca começar a existir, e por isso ela não começou.

    Desde a 1.29.0 basta o NOME DA CIDADE: o sistema pergunta as coordenadas ao serviço
    aberto de geografia da mesma casa que dá a previsão (pedido do Edson, 14/10/2026:
    "configurar api de previsão do tempo automática"). As coordenadas continuam no
    cadastro, agora preenchidas pelo sistema, e dá para corrigi-las à mão quando a loja
    fica longe do centro da cidade. O que o sistema achou fica escrito em
    `lugar_encontrado`, para alguém poder ver que não é a cidade homônima de outro
    estado: errar o lugar faria a chuva de outra cidade entrar na conta desta.
    """

    ativo = models.BooleanField(
        "buscar o tempo sozinho, todo dia", default=True,
        help_text="Desligado, o tempo só entra pelo que alguém escrever na tela.",
    )
    cidade = models.CharField(
        "cidade da loja", max_length=120, blank=True,
        help_text="Só o nome da cidade. O sistema descobre as coordenadas a partir dela.",
    )
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True,
                                   help_text="Ex.: -22.906847")
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True,
                                    help_text="Ex.: -43.172896")
    # "Sorocaba, São Paulo, Brasil": o que o serviço entendeu por aquele nome de cidade.
    lugar_encontrado = models.CharField(max_length=200, blank=True)
    ultima_busca = models.DateTimeField(null=True, blank=True)
    ultimo_erro = models.CharField(max_length=300, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "configuração do tempo"
        verbose_name_plural = "configuração do tempo"
        permissions = [("configurar_tempo", "Configurar a busca do tempo")]

    def __str__(self):
        return self.cidade or "loja"

    @classmethod
    def atual(cls):
        registro, _ = cls.objects.get_or_create(pk=1)
        return registro

    @property
    def tem_lugar(self):
        return self.latitude is not None and self.longitude is not None

    @property
    def da_para_buscar(self):
        """Dá para buscar o tempo: ou já há coordenadas, ou há cidade para descobri-las."""
        return self.tem_lugar or bool(self.cidade.strip())

    @property
    def o_que_falta(self):
        if not self.da_para_buscar:
            return ["a cidade da loja"]
        return []

    @property
    def pronta(self):
        return self.ativo and self.da_para_buscar
