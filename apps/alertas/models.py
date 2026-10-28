"""Alertas por e-mail: a configuração do envio e o registro do que já saiu.

Pedido do Edson em 08/10/2026: "quero que envie os relatórios de alertas e
notificações por e-mail", para cabanadojacaranda@gmail.com — contas a pagar todo
dia, estoque e sugestão de compra toda semana. Em 10/10/2026 ele definiu por onde
sai: a caixa naoresponder@cabanadojacaranda.com.br, do próprio domínio da loja, na
Hostinger.

Duas decisões que o modelo carrega:

- **A configuração é uma linha só** (`pk=1`). A loja tem um servidor e uma caixa de
  e-mail; uma tabela com várias configurações só criaria a pergunta "qual delas está
  valendo", que ninguém sabe responder olhando a tela.
- **Todo envio fica registrado**, inclusive o que falhou e por quê. Sem isso, "não
  recebi o e-mail de ontem" não tem resposta: ninguém sabe se o sistema não mandou,
  se o servidor recusou ou se o e-mail chegou e está no spam. O registro responde as
  duas primeiras e deixa só a terceira para a pessoa conferir.
"""

from datetime import time

from django.db import models
from django.utils import timezone

from apps.alertas import cifra


class Rotina(models.TextChoices):
    """Cada relatório que o sistema manda, e com que frequência."""

    CONTAS = "contas", "Contas a pagar (todo dia)"
    VENDAS = "vendas", "Vendas do dia (todo dia)"
    ESTOQUE = "estoque", "Estoque (toda semana)"
    COMPRA = "compra", "Sugestão de compra (toda semana)"
    # Vigia do backup no GitHub (1.33.0). Diária, e calada quando está tudo bem: ela
    # existe para a cópia fora do servidor não parar em silêncio.
    BACKUP = "backup", "Cópia do programa no GitHub (todo dia)"
    TESTE = "teste", "Teste de configuração"


class Canal(models.TextChoices):
    """Por onde o relatório sai. Pedido do Edson em 11/10/2026: e-mail e Telegram.

    Os dois são independentes: o Telegram sai mesmo com o e-mail desligado, e vice-versa.
    Juntar os dois num interruptor só faria o aviso do celular depender de uma senha de
    caixa de e-mail que nada tem a ver com ele.
    """

    EMAIL = "email", "E-mail"
    TELEGRAM = "telegram", "Telegram"


DIARIAS = (Rotina.CONTAS, Rotina.VENDAS, Rotina.BACKUP)
SEMANAIS = (Rotina.ESTOQUE, Rotina.COMPRA)


class ConfiguracaoDeEmail(models.Model):
    """Como o sistema manda e-mail. Uma linha só, sempre a de pk=1."""

    class DiaDaSemana(models.IntegerChoices):
        SEGUNDA = 0, "Segunda-feira"
        TERCA = 1, "Terça-feira"
        QUARTA = 2, "Quarta-feira"
        QUINTA = 3, "Quinta-feira"
        SEXTA = 4, "Sexta-feira"
        SABADO = 5, "Sábado"
        DOMINGO = 6, "Domingo"

    ativo = models.BooleanField(
        "mandar os relatórios por e-mail", default=False,
        help_text="Desligado, o sistema não manda e-mail. As telas continuam iguais.",
    )
    # Os padrões são os da Cabana, ditos pelo Edson em 10/10/2026: a caixa do próprio
    # domínio da loja, hospedada na Hostinger. Tudo isto é campo de tela: quem trocar de
    # provedor um dia troca aqui, sem mexer no código.
    servidor = models.CharField(
        "servidor de saída (SMTP)", max_length=120, default="smtp.hostinger.com")
    porta = models.PositiveIntegerField(
        default=465, help_text="Na Hostinger é 465. Em outros provedores costuma ser 587.")
    usar_tls = models.BooleanField(
        "conexão segura", default=True,
        help_text="Deixe ligado. Na porta 465 a conexão é SSL; na 587, TLS.",
    )
    usuario = models.CharField(
        "usuário (o e-mail que envia)", max_length=200, blank=True,
        default="naoresponder@cabanadojacaranda.com.br")
    # Guardada cifrada; o formulário nunca a mostra de volta. Ver apps/alertas/cifra.py.
    senha_guardada = models.TextField(blank=True, default="")
    remetente = models.CharField(
        "nome de quem envia", max_length=120, default="Sistema da Cabana",
        help_text="O nome que aparece na caixa de entrada antes do endereço.",
    )
    destinatarios = models.TextField(
        "para quem mandar", blank=True, default="cabanadojacaranda@gmail.com",
        help_text="Um e-mail por linha.",
    )

    # time() e não "07:00": get_or_create devolve a linha recém-criada sem ler o banco de
    # volta, então o padrão em texto chegaria como str em quem faz conta com a hora
    # (datetime.combine) e estouraria na primeira vez que a tela abrisse.
    hora_diaria = models.TimeField("hora do relatório diário", default=time(7, 0))
    dia_semanal = models.IntegerField(
        "dia dos relatórios semanais", choices=DiaDaSemana.choices, default=DiaDaSemana.SEGUNDA
    )
    hora_semanal = models.TimeField("hora dos relatórios semanais", default=time(7, 10))

    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "configuração de e-mail"
        verbose_name_plural = "configuração de e-mail"
        permissions = [("configurar_email", "Pode configurar o envio de relatórios por e-mail")]

    def __str__(self):
        return f"E-mail por {self.servidor}:{self.porta}"

    @classmethod
    def atual(cls):
        """A configuração, criando a linha vazia na primeira vez."""
        configuracao, _nova = cls.objects.get_or_create(pk=1)
        return configuracao

    @property
    def senha(self):
        return cifra.decifrar(self.senha_guardada)

    @senha.setter
    def senha(self, texto):
        self.senha_guardada = cifra.cifrar(texto)

    @property
    def tem_senha(self):
        return bool(self.senha_guardada)

    @property
    def lista_de_destinatarios(self):
        """Um e-mail por linha, sem linha em branco e sem espaço sobrando."""
        return [linha.strip() for linha in (self.destinatarios or "").splitlines() if linha.strip()]

    @property
    def porta_de_ssl(self):
        """A 465 fala TLS desde o primeiro byte; a 587 começa aberta e sobe com STARTTLS.

        São dois jeitos diferentes de dizer "seguro", e trocar um pelo outro não dá erro
        de senha: dá conexão que trava ou que o servidor derruba. Quem decide é a porta,
        para a tela não ter mais uma pergunta que ninguém sabe responder.
        """
        return self.porta == 465

    @property
    def pronta(self):
        """Dá para mandar e-mail com o que está preenchido?"""
        return bool(self.servidor and self.usuario and self.tem_senha and self.lista_de_destinatarios)

    @property
    def o_que_falta(self):
        """O que ainda impede o envio, em palavras, para a tela dizer."""
        faltas = []
        if not self.servidor:
            faltas.append("o servidor de saída")
        if not self.usuario:
            faltas.append("o e-mail que envia")
        if not self.tem_senha:
            faltas.append("a senha da caixa de e-mail")
        if not self.lista_de_destinatarios:
            faltas.append("para quem mandar")
        return faltas


class EnvioDeRelatorio(models.Model):
    """O que o sistema tentou mandar, quando, para quem, e se deu certo."""

    quando = models.DateTimeField(default=timezone.now, db_index=True)
    rotina = models.CharField(max_length=20, choices=Rotina.choices)
    # Por onde saiu. Os registros de antes da 1.24.0 são todos de e-mail, que é o que o
    # padrão grava neles na migração.
    canal = models.CharField(max_length=10, choices=Canal.choices, default=Canal.EMAIL)
    assunto = models.CharField(max_length=250, blank=True)
    destinatarios = models.TextField(blank=True)
    deu_certo = models.BooleanField(default=False)
    # Dia sem novidade não é falha, e mostrá-lo como falha na tela faria a gerência
    # procurar defeito onde não há. Os três estados: entregue, sem novidade, não saiu.
    sem_noticia = models.BooleanField("não havia notícia para mandar", default=False)
    # Em linguagem de loja, não a exceção crua: é esta frase que a tela mostra.
    erro = models.TextField(blank=True)
    resumo = models.CharField(
        "o que o relatório dizia", max_length=300, blank=True,
        help_text="A manchete do e-mail, para conferir sem abrir a caixa de entrada.",
    )
    disparado_por = models.CharField(
        "quem mandou", max_length=60, blank=True,
        help_text="A tarefa agendada, ou o usuário que apertou o botão.",
    )

    class Meta:
        ordering = ["-quando", "-id"]
        verbose_name = "envio de relatório"
        verbose_name_plural = "envios de relatório"

    def __str__(self):
        return f"{self.get_rotina_display()} em {self.quando:%d/%m/%Y %H:%M}"

    @property
    def por_telegram(self):
        return self.canal == Canal.TELEGRAM

    @property
    def situacao(self):
        """A palavra que a tela mostra, em vez de um booleano cru."""
        if self.deu_certo:
            return "entregue"
        return "sem novidade" if self.sem_noticia else "não saiu"


class ConfiguracaoDeTelegram(models.Model):
    """Como o sistema avisa pelo Telegram. Uma linha só, sempre a de pk=1.

    Pedido do Edson em 11/10/2026: "quero junto ao e-mail também seja enviado
    notificação pelo telegram". O Telegram é o aviso que chega no bolso, então o que
    sai por aqui é curto: a manchete e os números, com o link da tela. O relatório
    inteiro continua indo por e-mail.

    Duas coisas moram aqui e em nenhum outro lugar:

    - **O token do robô**, cifrado como a senha do e-mail (apps/alertas/cifra.py). Quem
      tem o token manda mensagem no nome da loja, então ele não fica em texto puro no
      banco nem volta para a tela depois de gravado.
    - **O chat**, que é para onde a mensagem vai: a conversa com a pessoa, ou o grupo da
      loja. O robô não consegue escrever para quem nunca falou com ele primeiro, e é por
      isso que a tela tem o botão que descobre o chat em vez de pedir um número que
      ninguém sabe de cabeça.
    """

    ativo = models.BooleanField(
        "mandar aviso no Telegram", default=False,
        help_text="Desligado, nada é enviado pelo Telegram. O e-mail não muda.",
    )
    # Guardado cifrado; o formulário nunca o mostra de volta.
    token_guardado = models.TextField(blank=True, default="")
    chat_id = models.CharField(
        "conversa ou grupo", max_length=40, blank=True, default="",
        help_text="O número do chat. Use o botão abaixo para descobrir, depois de falar "
                  "com o robô no Telegram.",
    )
    chat_nome = models.CharField(
        "nome da conversa", max_length=120, blank=True, default="",
        help_text="Só para a tela mostrar para quem está indo o aviso.",
    )
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "configuração do Telegram"
        verbose_name_plural = "configuração do Telegram"

    def __str__(self):
        return f"Telegram para {self.chat_nome or self.chat_id or 'ninguém ainda'}"

    @classmethod
    def atual(cls):
        configuracao, _nova = cls.objects.get_or_create(pk=1)
        return configuracao

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
    def pronta(self):
        return bool(self.tem_token and self.chat_id)

    @property
    def o_que_falta(self):
        faltas = []
        if not self.tem_token:
            faltas.append("o token do robô")
        if not self.chat_id:
            faltas.append("a conversa para onde mandar")
        return faltas

    @property
    def para_quem(self):
        """Como a tela e o registro de envio chamam o destino."""
        if self.chat_nome and self.chat_id:
            return f"{self.chat_nome} ({self.chat_id})"
        return self.chat_id or ""
