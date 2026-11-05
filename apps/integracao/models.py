"""A ponte com o agente da casa do Edson, que opera o Trello e o Kommo.

Pedido do Edson, 05/11/2026: *"vou usar um desktop na minha casa para manusear o trello e
kommo / o agente claude desse computador fara as integracoes"*.

O servidor da loja não fala com a internet em nome do Trello nem do Kommo, e não guarda a
senha de nenhum dos dois. Quem fala é o agente, que entra pela VPN com uma chave própria:

- **para fora** (Trello): cada mudança que importa vira um `Evento` numa fila. O agente
  busca os pendentes, faz a parte dele no Trello e devolve "entregue", com o número do
  cartão quando criou um;
- **para dentro** (Kommo): o agente lê os leads do Kommo e manda para cá. O lead entra uma
  vez só, pelo número dele no Kommo, e as conversas viram contatos marcados como trazidos.

A chave fica guardada só como resumo (SHA-256): quem lê o banco não consegue usá-la. Ela é
mostrada uma vez, na hora de criar, pelo comando `criar_chave_integracao`.
"""

import hashlib
import secrets

from django.db import models
from django.utils import timezone


def resumo_da_chave(chave):
    return hashlib.sha256(chave.encode("utf-8")).hexdigest()


class ChaveDeIntegracao(models.Model):
    nome = models.CharField(max_length=80, unique=True, help_text="Ex.: agente-da-casa")
    resumo = models.CharField(max_length=64, unique=True, editable=False)
    ativa = models.BooleanField(default=True)
    criada_em = models.DateTimeField(default=timezone.now)
    usada_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "chave de integração"
        verbose_name_plural = "chaves de integração"

    def __str__(self):
        return self.nome

    @classmethod
    def criar(cls, nome):
        """Cria a chave e devolve (registro, chave em texto). A chave não fica guardada."""
        chave = "studio_" + secrets.token_urlsafe(32)
        return cls.objects.create(nome=nome, resumo=resumo_da_chave(chave)), chave

    @classmethod
    def conferir(cls, chave):
        if not chave:
            return None
        return cls.objects.filter(resumo=resumo_da_chave(chave), ativa=True).first()


class Evento(models.Model):
    """Uma mudança que o agente tem de levar para fora (hoje, para o Trello)."""

    class Tipo(models.TextChoices):
        PROJETO_CRIADO = "projeto.criado", "Projeto criado"
        PROJETO_ALTERADO = "projeto.alterado", "Projeto alterado"
        PROJETO_ETAPA = "projeto.etapa", "Projeto mudou de etapa"
        LEAD_CRIADO = "lead.criado", "Lead criado"
        LEAD_ETAPA = "lead.etapa", "Lead mudou de etapa"

    tipo = models.CharField(max_length=40, choices=Tipo.choices)
    recurso_tipo = models.CharField(max_length=40)
    recurso_id = models.CharField(max_length=40)
    dados = models.JSONField(default=dict)
    criado_em = models.DateTimeField(default=timezone.now, db_index=True)
    entregue_em = models.DateTimeField(null=True, blank=True, db_index=True)
    tentativas = models.PositiveIntegerField(default=0)
    ultimo_erro = models.TextField(blank=True)

    class Meta:
        ordering = ["criado_em", "id"]
        verbose_name = "evento para o agente"
        verbose_name_plural = "eventos para o agente"

    def __str__(self):
        return f"{self.tipo} {self.recurso_tipo}#{self.recurso_id}"
