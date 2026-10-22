"""Monta os vídeos de câmera de mentira usados por conferir-leitura-de-barras.js.

Desenha o EAN-13 real de um produto da loja com o mesmo código que o sistema usa para
imprimir etiqueta (apps/core/barras.py), põe num fundo escuro parecido com a peça em
que a etiqueta fica colada, e gera três cenas conforme o tamanho que a etiqueta ocupa
no quadro de 1920x1080:

    perto  - as barras ocupam 900 px (quase meio quadro): lê na hora
    medio  - 480 px (um quarto do quadro): é a distância de quem conta de pé
    longe  - 260 px (um sétimo): NÃO é lida, e é por isso que a tela manda encostar

Precisa de Pillow e ffmpeg. Uso:

    python3 docs/ferramentas/montar-etiqueta-falsa.py /tmp/camfalsa
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

from apps.core.barras import _modulos  # noqa: E402

CODIGO = "0000000047463"  # VASO GARRAFA M JUNCO, o da foto que o Edson mandou
CENAS = (("perto", 900, 0.8), ("medio", 480, 1.0), ("longe", 260, 1.2))
LARGURA, ALTURA = 1920, 1080


def quadro(modulos, barras_px, desfoque):
    """Um quadro como a câmera veria: peça escura, etiqueta branca, barras do tamanho pedido."""
    imagem = Image.new("L", (LARGURA, ALTURA), 45)
    escala = barras_px / len(modulos)
    altura_barra = max(8, int(barras_px * 0.26))
    etiqueta_l, etiqueta_a = int(barras_px * 1.35), int(altura_barra * 2.4)
    etiqueta = Image.new("L", (etiqueta_l, etiqueta_a), 246)
    pincel = ImageDraw.Draw(etiqueta)
    x0 = (etiqueta_l - barras_px) / 2
    y0 = (etiqueta_a - altura_barra) / 2
    for i, modulo in enumerate(modulos):
        if modulo == "1":
            pincel.rectangle([x0 + i * escala, y0,
                              x0 + (i + 1) * escala - 0.01, y0 + altura_barra], fill=15)
    imagem.paste(etiqueta, ((LARGURA - etiqueta_l) // 2, (ALTURA - etiqueta_a) // 2))
    return imagem.filter(ImageFilter.GaussianBlur(desfoque)).convert("RGB")


def main(destino):
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    modulos = _modulos(CODIGO)
    for nome, barras_px, desfoque in CENAS:
        png = destino / f"{nome}.png"
        quadro(modulos, barras_px, desfoque).save(png)
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(png),
             "-t", "3", "-r", "15", "-pix_fmt", "yuv420p", "-s", f"{LARGURA}x{ALTURA}",
             str(destino / f"{nome}.y4m")],
            check=True,
        )
        print(f"{nome}: barras com {barras_px} px de {LARGURA}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/camfalsa")
