
from flask import Flask, request, render_template_string
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import pytesseract
import re
import os

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

# No Windows usa o caminho instalado; no Render, usa o Tesseract do sistema.
if os.name == "nt":
    pytesseract.pytesseract.tesseract_cmd = (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    )

PAGINA = """
<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Leitor de Número de Série</title>
<style>
* { box-sizing: border-box; }
body {
    font-family: Arial, sans-serif;
    max-width: 500px;
    margin: 25px auto;
    padding: 16px;
    background: #f2f4f7;
}
main {
    background: white;
    padding: 22px;
    border-radius: 16px;
}
input[type=file] { width: 100%; margin: 15px 0; }
button {
    width: 100%;
    padding: 16px;
    margin: 10px 0;
    background: #1769aa;
    color: white;
    border: 0;
    border-radius: 9px;
    font-size: 17px;
    font-weight: bold;
}
button:disabled { opacity: .65; }
.resultado {
    background: #eaf4ff;
    border-radius: 12px;
    padding: 15px;
    margin-top: 20px;
}
#serie {
    width: 100%;
    padding: 14px;
    font-size: 22px;
    border: 1px solid #bbb;
    border-radius: 8px;
}
#status { overflow-wrap: anywhere; }
</style>
</head>
<body>
<main>
<h2>Leitor de Número de Série</h2>
<p>Envie uma foto da etiqueta para identificar o SN.</p>

<form id="formulario" method="post" enctype="multipart/form-data">
<input type="file" name="foto" accept="image/*"
       capture="environment" required>
<button id="enviar" type="submit">Enviar foto e ler SN</button>
<p id="espera" hidden>Processando a foto. Aguarde...</p>
</form>

{% if erro %}
<p>{{ erro }}</p>
{% endif %}

{% if sn %}
<div class="resultado">
<label for="serie">Número identificado (confira antes de copiar)</label>
<input id="serie" value="{{ sn }}" autocomplete="off">
<button type="button" onclick="copiar()">Copiar SN</button>
<p id="status"></p>
</div>
{% endif %}

<script>
document.getElementById("formulario").addEventListener("submit", () => {
    document.getElementById("enviar").disabled = true;
    document.getElementById("enviar").textContent = "Lendo etiqueta...";
    document.getElementById("espera").hidden = false;
});

async function copiar() {
    const campo = document.getElementById("serie");
    const status = document.getElementById("status");
    try {
        await navigator.clipboard.writeText(campo.value);
        status.textContent = "SN copiado!";
    } catch (e) {
        campo.select();
        status.textContent = "Selecione e copie o número manualmente.";
    }
}
</script>
</main>
</body>
</html>
"""

def localizar_series(texto):
    linhas = texto.splitlines()

    # Dá prioridade ao texto próximo de S/N ou SERIAL.
    for i, linha in enumerate(linhas):
        if re.search(
            r"S\s*/\s*N|S\.?\s*N\.?|SERIAL|N[ÚU]MERO\s+DE\s+S[ÉE]RIE",
            linha,
            re.IGNORECASE
        ):
            trecho = " ".join(linhas[i:i + 2])
            numeros = re.findall(
                r"(?<![A-Z0-9])[A-Z0-9][A-Z0-9-]{5,23}(?![A-Z0-9])",
                trecho.upper()
            )
            numeros = [
                n for n in numeros
                if re.search(r"\d", n) and len(n) >= 7
            ]
            if numeros:
                return numeros[0]

    # Alternativa: procura sequências que parecem números de série.
    numeros = re.findall(
        r"(?<![A-Z0-9])[A-Z0-9][A-Z0-9-]{7,19}(?![A-Z0-9])",
        texto.upper()
    )
    numeros = [
        n for n in numeros
        if re.search(r"\d", n)
    ]

    return numeros[0] if numeros else None


@app.route("/", methods=["GET", "POST"])
def inicio():
    sn = None
    erro = None

    if request.method == "POST":
        foto = request.files.get("foto")

        if not foto or not foto.filename:
            erro = "Selecione uma foto da etiqueta."
        else:
            try:
                imagem = Image.open(foto.stream)
                imagem = ImageOps.exif_transpose(imagem)
                imagem.thumbnail((1400, 1400))
                imagem = ImageOps.grayscale(imagem)
                imagem = ImageEnhance.Contrast(imagem).enhance(1.8)
                imagem = imagem.filter(ImageFilter.SHARPEN)

                # Limita o tempo para evitar processamento interminável.
                texto = pytesseract.image_to_string(
                    imagem,
                    config="--oem 3 --psm 6",
                    timeout=12
                )

                sn = localizar_series(texto)

                if not sn:
                    erro = (
                        "Não encontrei o SN. Tente uma foto mais próxima, "
                        "nítida e sem reflexos."
                    )

            except RuntimeError:
                erro = (
                    "A leitura demorou demais. Recorte a foto para mostrar "
                    "principalmente a etiqueta e tente novamente."
                )
            except Exception:
                app.logger.exception("Erro ao processar a foto")
                erro = "Falha ao ler a imagem. Tente outra foto."

    return render_template_string(PAGINA, sn=sn, erro=erro)


@app.errorhandler(413)
def arquivo_grande(e):
    return render_template_string(
        PAGINA,
        sn=None,
        erro="A foto é muito grande. Envie uma imagem de até 8 MB."
    ), 413


if __name__ == "__main__":
    app.run(debug=False, port=5000)
