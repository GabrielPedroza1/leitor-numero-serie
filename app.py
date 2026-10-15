import os
import re

from flask import Flask, request, render_template_string
from PIL import Image, ImageOps, ImageEnhance
import pytesseract

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

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
    max-width: 520px;
    margin: 24px auto;
    padding: 16px;
    background: #f2f4f7;
    color: #202124;
}
main {
    background: white;
    padding: 22px;
    border-radius: 16px;
}
input[type=file] {
    width: 100%;
    margin: 18px 0;
}
button {
    width: 100%;
    padding: 15px;
    margin: 10px 0;
    background: #1769aa;
    color: white;
    border: 0;
    border-radius: 8px;
    font-size: 16px;
}
.resultado {
    background: #eaf4ff;
    padding: 14px;
    margin: 10px 0;
    border-radius: 8px;
    overflow-wrap: anywhere;
}
.aviso { color: #555; font-size: 14px; }
</style>
</head>
<body>
<main>
<h2>Leitor de Número de Série</h2>
<p>Envie uma foto da etiqueta do equipamento.</p>

<form method="post" enctype="multipart/form-data"
      onsubmit="document.getElementById('ler').disabled=true;
      document.getElementById('ler').textContent='Lendo etiqueta...';">
<input type="file" name="foto" accept="image/*"
       capture="environment" required>
<button id="ler" type="submit">Ler número de série</button>
</form>

{% if erro %}
<p>{{ erro }}</p>
{% endif %}

{% if candidatos %}
<h3>Confira o número identificado</h3>
<p class="aviso">Selecione o número correto antes de copiar.</p>

{% for c in candidatos %}
<div class="resultado">
<label>
<input type="radio" name="serie" value="{{ c }}"
{% if loop.first %}checked{% endif %}>
<strong>{{ c }}</strong>
</label>
</div>
{% endfor %}

<button type="button" onclick="copiar()">Copiar selecionado</button>
<p id="status"></p>
<script>
async function copiar() {
    const item = document.querySelector('input[name="serie"]:checked');
    const status = document.getElementById('status');
    if (!item) return;

    try {
        await navigator.clipboard.writeText(item.value);
        status.textContent = 'Número copiado: ' + item.value;
    } catch (e) {
        const campo = document.createElement('textarea');
        campo.value = item.value;
        document.body.appendChild(campo);
        campo.select();
        const ok = document.execCommand('copy');
        campo.remove();
        status.textContent = ok
            ? 'Número copiado: ' + item.value
            : 'Copie manualmente: ' + item.value;
    }
}
</script>
{% endif %}
</main>
</body>
</html>
"""


def localizar_series(texto):
    linhas = texto.upper().splitlines()
    encontrados = {}

    padrao = re.compile(
        r"(?<![A-Z0-9])[A-Z0-9][A-Z0-9-]{5,23}(?![A-Z0-9])"
    )
    rotulo = re.compile(
        r"\bS\s*/?\s*N\b|SERIAL|N[ÚU]MERO\s+DE\s+S[ÉE]RIE",
        re.IGNORECASE
    )

    for i, linha in enumerate(linhas):
        if rotulo.search(linha):
            trecho = " ".join(linhas[i:min(i + 2, len(linhas))])
            for codigo in padrao.findall(trecho):
                if any(ch.isdigit() for ch in codigo):
                    encontrados[codigo] = encontrados.get(codigo, 0) + 10

    # Se não encontrou perto de S/N, usa os códigos encontrados no texto.
    if not encontrados:
        for codigo in padrao.findall(texto.upper()):
            if any(ch.isdigit() for ch in codigo):
                encontrados[codigo] = encontrados.get(codigo, 0) + 1

    return [
        codigo for codigo, pontos in
        sorted(encontrados.items(), key=lambda item: item[1], reverse=True)
        if 7 <= len(codigo) <= 24
    ][:10]


@app.errorhandler(413)
def arquivo_grande(_erro):
    return render_template_string(
        PAGINA, candidatos=[],
        erro="A foto ultrapassa 8 MB. Envie uma imagem menor."
    ), 413


@app.route("/", methods=["GET", "POST"])
def inicio():
    candidatos = []
    erro = None

    if request.method == "POST":
        foto = request.files.get("foto")

        if not foto or not foto.filename:
            erro = "Selecione uma foto."
        else:
            try:
                imagem = Image.open(foto.stream)
                imagem = ImageOps.exif_transpose(imagem)
                imagem.thumbnail((1200, 1200))
                imagem = ImageOps.grayscale(imagem)
                imagem = ImageOps.autocontrast(imagem)
                imagem = ImageEnhance.Contrast(imagem).enhance(1.4)

                # Uma única execução do OCR para reduzir o uso de memória.
                texto = pytesseract.image_to_string(
                    imagem,
                    config="--oem 3 --psm 11"
                )

                candidatos = localizar_series(texto)

                if not candidatos:
                    erro = (
                        "Não encontrei o número. Tente aproximar a câmera "
                        "da etiqueta, melhorar a iluminação e evitar reflexos."
                    )

            except Exception:
                app.logger.exception("Erro ao processar a foto")
                erro = (
                    "Falha ao ler a foto. Tente uma imagem mais nítida "
                    "e confira os logs se o problema continuar."
                )

    return render_template_string(
        PAGINA, candidatos=candidatos, erro=erro
    )


if __name__ == "__main__":
    app.run(debug=False, port=5000)

if __name__ == "__main__":
    app.run(debug=False, port=5000)
