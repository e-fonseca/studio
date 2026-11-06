"""Quem pode abrir o sistema dentro de uma página: a intranet da loja, e mais ninguém.

Pedido do Edson em 06/11/2026: *"queria que o sistema aux studio abrisse ao lado do menu
dentro da pagina da intranet e não abrisse um outro link"*. A intranet
(`https://192.168.3.254/intranet/`) mostra o sistema num quadro (iframe), ao lado do menu
dela, na tela Gestão › Sistema aux SET.

Até a 2.1.0 todo pedido saía com `X-Frame-Options: DENY`, que proíbe qualquer quadro, e é
o certo para um sistema com dinheiro dentro: sem isso, um site qualquer abre o sistema
invisível por baixo de um botão dele e faz a pessoa clicar onde não queria (é o
"clickjacking"). O `X-Frame-Options` não sabe dizer "só aquele endereço", então quem passa
a falar é o `Content-Security-Policy: frame-ancestors`, que sabe, e que os navegadores
obedecem no lugar do outro quando os dois aparecem:

- `STUDIO_INTRANET_ORIGENS` vazio: nada muda. `frame-ancestors 'none'` e o mesmo `DENY`.
- com endereços (o padrão é `https://192.168.3.254`, a intranet): `frame-ancestors 'self'`
  e esses endereços, e o `X-Frame-Options` sai, porque um `DENY` ao lado faria navegador
  antigo recusar justamente o quadro permitido.

A intranet fica noutra origem (outra porta), e o navegador não deixa uma página ler a
outra: o quadro mostra o sistema, mas a intranet não enxerga nada do que está nele, nem ele
nela. É isso que mantém o dinheiro daqui separado da folha de lá, lado a lado na tela.

A política de cada resposta é acrescentada à que a tela já tiver posto (os anexos saem
com `default-src 'none'`), nunca trocada por ela.
"""

from django.conf import settings


def politica(origens):
    """O valor de frame-ancestors para estes endereços."""
    if not origens:
        return "frame-ancestors 'none'"
    return "frame-ancestors " + " ".join(["'self'", *origens])


class MolduraMiddleware:
    """Diz ao navegador quem pode emoldurar o sistema. Fica logo depois do XFrameOptions."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.origens = [o for o in getattr(settings, "INTRANET_ORIGENS", []) if o]
        self.politica = politica(self.origens)

    def __call__(self, request):
        resposta = self.get_response(request)
        atual = resposta.get("Content-Security-Policy", "")
        if "frame-ancestors" not in atual:
            resposta["Content-Security-Policy"] = f"{atual}; {self.politica}" if atual else self.politica
        if self.origens:
            # Lido pelo XFrameOptionsMiddleware, que roda depois deste na volta: com a
            # intranet autorizada, ele não põe o DENY.
            resposta.xframe_options_exempt = True
        return resposta
