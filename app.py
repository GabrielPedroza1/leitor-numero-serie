
from flask import Flask, request, render_template_string
from PIL import Image, ImageOps, ImageEnhance
import pytesseract
import re

app = Flask(__name__)

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
body {
    font-family: Arial, sans-serif;
    max-width: 500px;
    margin: 30px auto;
    padding: 16px;
    background: #f2f4f7;
}
main {
    background: white;
    padding: 22px;
    border-radius: 14px;
}
button, input[type=file] {
    box-sizing: border-box;
    width: 100%;
    padding: 13px;
    margin: 10px 0;
}
button {
    background: #1769aa;
    color: white;
    border: 0;
    border-radius: 8px;
    cursor: pointer;
}
.resultado {
    background: #eaf4ff;
    padding: 12px;
    margin: 8px 0;
    overflow-wrap: anywhere;
}
</style>
</head>
<body>
<main>
<h2>Leitor de Número de Série</h2>
<p>Envie uma foto da etiqueta do equipamento.</p>

<form method="post" enctype="multipart/form-data">
<input type="file" name="foto" accept="image/*"
       capture="environment" required>
<button type="submit">Ler número de série</button>
</form>

{% if erro %}
<p>{{ erro }}</p>
{% endif %}

{% if candidatos %}
<h3>Confira o número identificado</h3>
<p>Selecione o número correto antes de copiar.</p>

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
function copiar() {
    const item = document.querySelector(
        'input[name="serie"]:checked'
    );
    if (!item) return;

    navigator.clipboard.writeText(item.value)
        .then(() => {
            document.getElementById("status").textContent =
                "Número copiado!";
        })
        .catch(() => {
            document.getElementById("status").textContent =
                "Cópia automática indisponível.";
        });
}
</script>
{% endif %}
</main>
</body>
</html>
"""

def localizar_series(texto):
    linhas = texto.splitlines()
    resultados = []

    for i, linha in enumerate(linhas):
        if re.search(
            r"serial|s/?n|numero de serie|número de série",
            linha,
            re.I
        ):
            trecho = " ".join(linhas[i:i + 2])
            resultados += re.findall(
                r"(?<![A-Z0-9])[A-Z0-9][A-Z0-9-]{5,23}(?![A-Z0-9])",
                trecho.upper()
            )

    if not resultados:
        resultados = re.findall(
            r"(?<![A-Z0-9])[A-Z0-9][A-Z0-9-]{7,19}(?![A-Z0-9])",
            texto.upper()
        )

    return list(dict.fromkeys(resultados))[:15]


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
                imagem = ImageOps.grayscale(imagem)
                imagem = ImageEnhance.Contrast(imagem).enhance(2)
                imagem = imagem.resize(
                    (imagem.width * 2, imagem.height * 2)
                )

                texto = pytesseract.image_to_string(
                    imagem,
                    config="--psm 6"
                )

                candidatos = localizar_series(texto)

                if not candidatos:
                    erro = (
                        "Número não encontrado. "
                        "Tente uma foto mais nítida."
                    )

            except Exception:
                app.logger.exception("Erro ao processar a foto")
                erro = (
                    "Não foi possível ler a foto. "
                    "Confira a instalação do Tesseract."
                )

    return render_template_string(
        PAGINA,
        candidatos=candidatos,
        erro=erro
    )


if __name__ == "__main__":
    app.run(debug=False, port=5000)
