"""Cria (ou confere) o certificado da loja e diz em voz alta o que aconteceu.

O instalador roda este comando depois de atualizar. Antes, a criação do certificado só
acontecia quando o sistema subia, dentro de um try que engolia a falha para não derrubar
o HTTP — então um erro de permissão na pasta ficava invisível: a porta segura não subia,
o download da autoridade dava "Página não encontrada" e nada dizia por quê (08/10/2026).
Rodando aqui, o motivo aparece na tela da atualização, que é onde se está olhando.
"""

from django.core.management.base import BaseCommand

from apps.core import certificado


class Command(BaseCommand):
    help = "Confere (e cria, se faltar) o certificado da loja usado pela porta HTTPS."

    def handle(self, *args, **opcoes):
        pasta = certificado.pasta_padrao()
        enderecos = certificado.enderecos_configurados()
        self.stdout.write(f"Pasta do certificado: {pasta}")
        self.stdout.write(f"Endereços cobertos: {', '.join(enderecos) or '—'}")
        try:
            arquivo, _chave = certificado.garantir(pasta, enderecos)
        except Exception as erro:  # noqa: BLE001 - o que importa é dizer o motivo
            self.stdout.write(self.style.ERROR(
                f"NÃO consegui criar o certificado: {type(erro).__name__}: {erro}"))
            self.stdout.write(
                "A porta segura (HTTPS) não vai subir e o download da autoridade não vai "
                "funcionar. Quase sempre é permissão: a conta que roda o sistema precisa "
                f"poder gravar em {pasta}.")
            return
        ficha = certificado.descrever(pasta)
        self.stdout.write(self.style.SUCCESS(f"Certificado pronto em {arquivo}"))
        for nome, dados in (("autoridade da loja", ficha.get("autoridade")),
                            ("certificado do servidor", ficha.get("servidor"))):
            if dados:
                self.stdout.write(f"  {nome}: vence em {dados.get('vence_em') or '—'}")
