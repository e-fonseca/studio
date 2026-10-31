"""O atalho na tela inicial do celular (PWA).

O Edson pediu um "app" do sistema para Android e iPhone. Loja de interior, um
sistema que só responde na rede local: publicar na Play Store e na App Store
custaria conta de desenvolvedor, revisão da Apple e um aplicativo para manter
além do sistema. O mesmo resultado prático sai do próprio navegador: com estes
dois arquivos o sistema ganha ícone na tela inicial e abre em tela cheia, sem
barra de endereço, como qualquer aplicativo.

São dois:

- o manifesto, que diz o nome, o ícone e que a janela abre sem barra;
- o operário (service worker), que guarda o CSS, o JavaScript e os ícones no
  aparelho para a tela abrir rápido no wifi da loja.

O operário é servido por este arquivo, e não como arquivo estático, por dois
motivos. O navegador só deixa um operário cuidar das páginas que ficam na pasta
dele ou abaixo, então ele tem que responder em /sistema/, não em
/sistema/static/. E o nome do depósito leva o número da versão: a cada
atualização o nome muda, o depósito antigo é apagado e ninguém fica vendo a
tela da versão passada.

Tudo isso só funciona em https (ou no localhost), igual à câmera: ver
docs/https-e-camera.md.
"""

from django.http import HttpResponse, JsonResponse
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.cache import cache_control

from apps.core import versao

NOME = "Cabana do Jacarandá"
NOME_CURTO = "Cabana"
# As cores do aplicativo no celular: a barra de cima do aparelho e a tela de abertura.
# Desde a 1.43.0 o sistema é escuro, e as duas acompanham (o topo e o fundo das telas);
# a barra marrom e a abertura creme de antes piscavam claro antes da tela escura.
COR_DA_MARCA = "#241f1a"
COR_DO_FUNDO = "#13110f"


def manifesto(request):
    """O cartão de identidade do atalho, lido quando a pessoa manda "adicionar à tela inicial"."""
    return JsonResponse({
        "name": f"{NOME} · Sistema auxiliar",
        "short_name": NOME_CURTO,
        "description": "Sistema auxiliar da Cabana do Jacarandá: compras, estoque, "
                       "financeiro e inventário.",
        "lang": "pt-BR",
        "dir": "ltr",
        "id": reverse("core:inicio"),
        "start_url": reverse("core:inicio"),
        "scope": reverse("core:inicio"),
        "display": "standalone",
        "orientation": "any",
        "theme_color": COR_DA_MARCA,
        "background_color": COR_DO_FUNDO,
        "icons": [
            {"src": static("img/icone-192.png"), "sizes": "192x192", "type": "image/png",
             "purpose": "any"},
            {"src": static("img/icone-512.png"), "sizes": "512x512", "type": "image/png",
             "purpose": "any"},
            # O Android recorta o ícone em círculo, folha ou quadrado arredondado,
            # conforme o aparelho. Esta versão tem margem de sobra para o recorte
            # não comer o logotipo.
            {"src": static("img/icone-512-recortavel.png"), "sizes": "512x512",
             "type": "image/png", "purpose": "maskable"},
        ],
        # Atalhos no toque longo do ícone, nas telas de quem está na loja com o
        # celular na mão.
        "shortcuts": [
            {"name": "Consulta de produto", "url": reverse("importacao:consulta")},
            {"name": "Inventário", "url": reverse("inventario:lista")},
            {"name": "Antes de comprar", "url": reverse("compras:antes_de_comprar")},
        ],
    }, json_dumps_params={"ensure_ascii": False},
       content_type="application/manifest+json")


def _codigo_do_operario(deposito, arquivos):
    guardados = ",\n      ".join(f'"{arquivo}"' for arquivo in arquivos)
    return f"""/* Operário do sistema da Cabana do Jacarandá. Gerado por apps/core/aplicativo.py;
   não editar à mão. O nome do depósito tem a versão, então atualizar o sistema
   troca o depósito e apaga o antigo. */
var DEPOSITO = "{deposito}";
var GUARDAR = [
      {guardados}
];

self.addEventListener("install", function (evento) {{
  // Guarda o visual de uma vez, para a primeira tela abrir rápido no wifi da loja.
  evento.waitUntil(
    caches.open(DEPOSITO).then(function (deposito) {{
      return deposito.addAll(GUARDAR);
    }}).then(function () {{
      return self.skipWaiting();
    }}).catch(function () {{
      // Faltou um arquivo: o sistema funciona sem depósito, então não travamos a instalação.
      return self.skipWaiting();
    }})
  );
}});

self.addEventListener("activate", function (evento) {{
  evento.waitUntil(
    caches.keys().then(function (nomes) {{
      return Promise.all(nomes.map(function (nome) {{
        if (nome !== DEPOSITO) {{ return caches.delete(nome); }}
        return null;
      }}));
    }}).then(function () {{
      return self.clients.claim();
    }})
  );
}});

self.addEventListener("fetch", function (evento) {{
  var pedido = evento.request;
  if (pedido.method !== "GET") {{ return; }}
  var endereco = new URL(pedido.url);
  if (endereco.origin !== self.location.origin) {{ return; }}

  // Dado da loja NUNCA sai do depósito: número velho na tela é pior do que tela
  // nenhuma. Só o visual (CSS, JavaScript, ícones) é guardado.
  var visual = endereco.pathname.indexOf("/static/") !== -1;
  if (!visual) {{ return; }}

  evento.respondWith(
    caches.match(pedido).then(function (guardado) {{
      if (guardado) {{ return guardado; }}
      return fetch(pedido).then(function (resposta) {{
        if (resposta && resposta.ok) {{
          var copia = resposta.clone();
          caches.open(DEPOSITO).then(function (deposito) {{
            deposito.put(pedido, copia);
          }});
        }}
        return resposta;
      }});
    }})
  );
}});
"""


# Sem cache no navegador: é por este arquivo que a atualização chega aos celulares.
@cache_control(no_cache=True, no_store=True, max_age=0)
def operario(request):
    """O service worker, com o número da versão no nome do depósito."""
    arquivos = [
        static("css/sistema.css"),
        static("js/leitor/zxing.min.js"),
        static("img/logo.png"),
        static("img/icone-192.png"),
        static("img/icone-512.png"),
    ]
    codigo = _codigo_do_operario(f"cabana-{versao.atual().numero}", arquivos)
    return HttpResponse(codigo, content_type="application/javascript; charset=utf-8")
