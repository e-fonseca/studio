"""Guarda a senha do e-mail sem deixá-la em texto puro no banco.

Honestidade sobre o que isto é e o que não é: a chave sai da `SECRET_KEY` do
próprio sistema, que mora no `cabana.env` ao lado do banco. Então isto **não**
protege contra alguém que já tem o servidor — essa pessoa tem as duas coisas.

O que protege: quem abre a tabela num cliente de banco, quem recebe um backup do
PostgreSQL por e-mail, quem lê um dump num pen drive. Sem isto, a senha da caixa de e-mail da
loja estaria legível em todos esses lugares, e senha de e-mail é a chave para
redefinir senha de todo o resto.

Dois cuidados que o formato carrega:

- **Guardado errado se parece com guardado certo.** Decifrar o que não é texto
  nosso levanta `InvalidToken`, e aí a função devolve vazio em vez de explodir numa
  tela — é o que acontece se alguém trocar a SECRET_KEY depois de gravar a senha.
  Nesse caso a senha some e a tela pede de novo, que é o certo.
- **Vazio é vazio.** Nunca cifrar string vazia e guardar lixo: o modelo distingue
  "sem senha" de "com senha" por esse campo estar vazio.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _chave():
    # Fernet quer 32 bytes em base64 url-safe; a SECRET_KEY é texto de tamanho livre.
    bruto = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(bruto)


def cifrar(texto):
    if not texto:
        return ""
    return Fernet(_chave()).encrypt(texto.encode("utf-8")).decode("ascii")


def decifrar(guardado):
    if not guardado:
        return ""
    try:
        return Fernet(_chave()).decrypt(guardado.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError):
        # SECRET_KEY trocada ou campo estragado: melhor pedir a senha de novo do que
        # derrubar a tela de configuração, que é justamente onde se conserta isso.
        return ""
