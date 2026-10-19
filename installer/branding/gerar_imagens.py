#!/usr/bin/env python3
"""
Gera o ícone e as imagens do assistente do instalador (Inno Setup).

Ferramenta de desenvolvimento: o RESULTADO (os .bmp e o .ico desta pasta) é
versionado, então o build do instalador não precisa de Python nem de
navegador. Rode só quando mudar o desenho ou a logo:

    pip install pillow playwright
    python installer/branding/gerar_imagens.py

Precisa de um Chromium. O Playwright usa o dele; se já houver um instalado,
aponte com a variável CHROMIUM=/caminho/do/chrome. As imagens são desenhadas
em HTML/CSS (mesma fonte, cores e logo da dockpane) e fotografadas no tamanho
exato de cada resolução — nada de esticar um bitmap.

Por que tantos tamanhos: o Inno Setup escolhe, entre a lista de arquivos de
WizardImageFile/WizardSmallImageFile, o que mais se aproxima do tamanho
necessário na escala de DPI da tela. Com um tamanho só, o resto fica borrado.

Saída em installer/branding/:
    wizard-large-<escala>.bmp   lateral das telas de boas-vindas e conclusão
    wizard-small-<escala>.bmp   canto superior direito das demais telas
    fireutils.ico               ícone do instalador e do desinstalador
"""

import base64
import io
import os
import sys
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent.parent
LOGO = RAIZ / "Fire Utils.tab" / "lib" / "assets" / "fireutils-logo-h.png"
FONTE_600 = AQUI / "fonts" / "SpaceGrotesk-600.woff2"
FONTE_700 = AQUI / "fonts" / "SpaceGrotesk-700.woff2"

# Tamanhos recomendados pela documentação do Inno Setup para cada escala de
# DPI (largura, altura em pixels).
GRANDES = {100: (164, 314), 125: (192, 386), 150: (246, 459), 200: (328, 604), 250: (410, 797)}
PEQUENAS = {100: (55, 55), 125: (64, 68), 150: (83, 80), 200: (110, 106), 250: (138, 140)}
TAMANHOS_ICO = [16, 24, 32, 48, 64, 128, 256]

# O símbolo da marca (webapp/src/assets/icons/fireutils-logo.svg), em vetor:
# fica nítido em qualquer tamanho.
SIMBOLO = (
    '<svg viewBox="0 0 65 84" xmlns="http://www.w3.org/2000/svg" fill="currentColor">'
    '<path d="M65 0V60.0923H46.9802L46.9802 19.8121L65 0Z"/>'
    '<path d="M39.901 23.9077V84H22.5248L22.5248 43.7198L39.901 23.9077Z"/>'
    '<path d="M17.3762 43.9385H0V63.9692L17.3762 43.9385Z"/>'
    "</svg>"
)


def uri_de_arquivo(caminho: Path, tipo: str) -> str:
    return f"data:{tipo};base64," + base64.b64encode(caminho.read_bytes()).decode()


def logo_para_fundo_escuro() -> str:
    """
    A logo tem o nome em cinza-escuro, que some sobre fundo escuro (é o que
    se vê no assistente atual). Mantém o vermelho da marca e passa o resto
    para branco, preservando a transparência das bordas.
    """
    imagem = Image.open(LOGO).convert("RGBA")
    pixels = imagem.load()
    for y in range(imagem.height):
        for x in range(imagem.width):
            r, g, b, a = pixels[x, y]
            if a == 0:
                continue
            vermelho = r > 120 and r > g * 2 and r > b * 2
            if not vermelho:
                pixels[x, y] = (255, 255, 255, a)
    buffer = io.BytesIO()
    imagem.save(buffer, "PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def base_html(css: str, corpo: str, unidades_por_largura: float, fundo: str) -> str:
    """
    Moldura comum. `--u` é a unidade de desenho: 1/N da largura da imagem
    (N = largura base), então o layout escala sozinho entre os tamanhos.
    """
    return f"""<!doctype html><meta charset="utf-8"><style>
@font-face {{ font-family: SG; font-weight: 600; src: url({uri_de_arquivo(FONTE_600, 'font/woff2')}) }}
@font-face {{ font-family: SG; font-weight: 700; src: url({uri_de_arquivo(FONTE_700, 'font/woff2')}) }}
:root {{ --u: calc(100vw / {unidades_por_largura}); --accent: #C0152A; }}
html, body {{ margin: 0; width: 100vw; height: 100vh; overflow: hidden; background: {fundo};
  font-family: SG, "Segoe UI", sans-serif; color: #fff; -webkit-font-smoothing: antialiased; }}
* {{ box-sizing: border-box; }}
{css}
</style>
{corpo}"""


def html_grande(logo_uri: str) -> str:
    css = f"""
.p {{ position: relative; width: 100%; height: 100%; overflow: hidden;
  background:
    radial-gradient(135% 46% at 8% 106%, rgba(192, 21, 42, .62), rgba(192, 21, 42, 0) 72%),
    radial-gradient(100% 38% at 105% -4%, rgba(255, 255, 255, .06), rgba(255, 255, 255, 0) 65%),
    linear-gradient(180deg, #131318 0%, #0d0d11 100%); }}
.marca {{ position: absolute; width: calc(var(--u) * 170); right: calc(var(--u) * -52);
  bottom: calc(var(--u) * 46); color: var(--accent); opacity: .13; transform: rotate(0deg); }}
.logo {{ position: absolute; left: calc(var(--u) * 17); top: calc(var(--u) * 30); width: calc(var(--u) * 126); }}
.base {{ position: absolute; left: calc(var(--u) * 17); right: calc(var(--u) * 14); bottom: calc(var(--u) * 24); }}
.linha {{ width: calc(var(--u) * 24); height: calc(var(--u) * 2.4); border-radius: calc(var(--u) * 2);
  background: var(--accent); margin-bottom: calc(var(--u) * 11); }}
.rotulo {{ font-size: calc(var(--u) * 6.4); font-weight: 600; letter-spacing: .13em; text-transform: uppercase;
  color: rgba(255, 255, 255, .56); margin-bottom: calc(var(--u) * 7); }}
.titulo {{ font-size: calc(var(--u) * 12.6); font-weight: 700; line-height: 1.2; letter-spacing: -.005em; }}
"""
    corpo = f"""<div class="p">
  <div class="marca">{SIMBOLO}</div>
  <img class="logo" src="{logo_uri}">
  <div class="base">
    <div class="linha"></div>
    <div class="rotulo">Plugin para Autodesk Revit</div>
    <div class="titulo">Proteção contra incêndio, direto no seu projeto.</div>
  </div>
</div>"""
    return base_html(css, corpo, 164, "#0d0d11")


def html_pequena() -> str:
    # O assistente é todo escuro (WizardBackColor=#0d0d11 no .iss): o desenho
    # é um "ícone de app" com cantos arredondados sobre essa mesma cor.
    css = f"""
.q {{ position: absolute; inset: calc(var(--u) * 2.6); border-radius: calc(var(--u) * 11);
  background:
    radial-gradient(120% 70% at 50% 118%, rgba(192, 21, 42, .50), rgba(192, 21, 42, 0) 70%),
    linear-gradient(160deg, #1d1d23, #0e0e12);
  display: flex; align-items: center; justify-content: center; }}
.q svg {{ height: 50%; color: var(--accent); margin-left: calc(var(--u) * -.6); }}
"""
    return base_html(css, f'<div class="q">{SIMBOLO}</div>', 55, "#0d0d11")


def html_icone() -> str:
    css = f"""
html, body {{ background: transparent; }}
.q {{ position: absolute; inset: 3%; border-radius: 22%;
  background:
    radial-gradient(120% 70% at 50% 118%, rgba(192, 21, 42, .55), rgba(192, 21, 42, 0) 70%),
    linear-gradient(160deg, #1f1f26, #0e0e12);
  box-shadow: inset 0 0 0 max(1px, 1.1%) rgba(255, 255, 255, .13);
  display: flex; align-items: center; justify-content: center; }}
.q svg {{ height: 52%; color: var(--accent); margin-left: -1%; }}
"""
    return base_html(css, f'<div class="q">{SIMBOLO}</div>', 100, "transparent")


def fotografar(pagina, html: str, largura: int, altura: int, transparente: bool = False) -> Image.Image:
    pagina.set_viewport_size({"width": largura, "height": altura})
    pagina.set_content(html)
    pagina.evaluate("document.fonts.ready")
    pagina.wait_for_timeout(120)
    png = pagina.screenshot(omit_background=transparente)
    return Image.open(io.BytesIO(png))


def main() -> int:
    logo_uri = logo_para_fundo_escuro()
    previa = Path(sys.argv[sys.argv.index("--previa") + 1]) if "--previa" in sys.argv else None
    if previa:
        previa.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        navegador = p.chromium.launch(
            executable_path=os.environ.get("CHROMIUM") or None, args=["--no-sandbox"]
        )
        pagina = navegador.new_page()

        for escala, (largura, altura) in GRANDES.items():
            imagem = fotografar(pagina, html_grande(logo_uri), largura, altura).convert("RGB")
            imagem.save(AQUI / f"wizard-large-{escala}.bmp", "BMP")
            if previa:
                imagem.save(previa / f"wizard-large-{escala}.png")

        for escala, (largura, altura) in PEQUENAS.items():
            imagem = fotografar(pagina, html_pequena(), largura, altura).convert("RGB")
            imagem.save(AQUI / f"wizard-small-{escala}.bmp", "BMP")
            if previa:
                imagem.save(previa / f"wizard-small-{escala}.png")

        icones = [
            fotografar(pagina, html_icone(), lado, lado, transparente=True).convert("RGBA")
            for lado in TAMANHOS_ICO
        ]
        navegador.close()

    maior = icones[-1]
    maior.save(
        AQUI / "fireutils.ico",
        format="ICO",
        sizes=[(i.width, i.height) for i in icones],
        append_images=icones[:-1],
    )
    if previa:
        maior.save(previa / "icone-256.png")

    print("Imagens geradas em", AQUI)
    return 0


if __name__ == "__main__":
    sys.exit(main())
