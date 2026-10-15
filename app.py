import os
import re
from flask import Flask, request, render_template_string
from PIL import Image, ImageOps, ImageEnhance
import pytesseract

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

# Caminho do Tesseract no Windows.
# No Render/Linux, usa o executável instalado pelo Dockerfile.
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
<meta name="theme-color" content="#1769aa">
<title>Leitor de SN</title>
<style>
* { box-sizing: border-box; }
body {
    font-family: Arial, sans-serif;
    max-width: 500px;
    margin: 20px auto;
    padding: 16px;
    background: #f2f4f7;
    color: #202124;
}
main {
    background: white;
    padding: 22px;
    border-radius: 16px;
    box-shadow: 0 3px 14px #0000000b;
}
h2 { margin-top: 0; }
input[type=file] {
    display: block;
    width: 100%;
    padding: 12px 0;
    margin: 16px 0;
}
button {
    width: 100%;
    padding: 16px;
    margin: 10px 0;
    background: #1769aa;
    color: white;
    border: 0;
    border-radius: 10px;
    font-size: 17px;
    font-weight: bold;
    cursor: pointer;
}
button:disabled { opacity: 0.65; }
.resultado {
    background: #eaf4ff;
    border: 1px solid #c6e1ff;
    border-radius: 12px;
    padding: 16px;
    margin-top: 20px;
}
.numero {
    font-size: 28px;
    font-weight: bold;
    text-align: center;
    overflow-wrap: anywhere;
    margin: 14px 0;
}
label { font-size: 14px; }
input[type=text] {
    width: 100%;
    padding: 13px;
    border: 1px solid #bbb;
    border-radius: 8px;
    font-size: 18px;
    margin-top: 8px;
}
.aviso { font-size: 14px; color: #555; line-height: 1.5; }
.erro {
    background: #fff0f0;
    color: #8b1e1e;
    border-radius: 8px;
    padding: 12px;
}
</style>
</head>
<body>
<main>
<h2>Leitor de Número de Série</h2>
<p>Envie uma foto da etiqueta para identificar o SN.</p>

<form method="post" enctype="multipart/form-data" id="formulario">
<input type="file" name="foto" accept="image/*"
       capture="environment" required>
<button type="submit" id="ler">Enviar foto e ler SN</button>
<p id="aguarde" class="aviso" hidden>
Lendo a etiqueta... aguarde.
</p>
</form>

{% if erro %}
<p class="erro">{{ erro }}</p>
{% endif %}

{% if sn %}
<div class="resultado">
<label for="sn">Número de série identificado (confira antes de copiar)</label>
<input type="text" id="sn" value="{{ sn }}" autocomplete="off">
<button type="button" onclick="copiarSN()">Copiar SN</button>
<p id="status" class="aviso" role="status"></p>
</div>
{% endif %}

<script>
document.getElementById("formulario").addEventListener("submit", function() {
    document.getElementById("ler").disabled = true;
    document.getElementById("ler").textContent = "Lendo etiqueta...";
    document.getElementById("aguarde").hidden = false;
});

async function copiarSN() {
    const campo = document.getElementById("sn");
    const status = document.getElementById("status");
    const valor = campo.value.trim();

    if (!valor) {
        status.textContent = "Nenhum SN para copiar.";
        return;
    }

    try {
        await navigator.clipboard.writeText(valor);
        status.textContent = "SN copiado! Pode colar no sistema.";
    } catch (e) {
        campo.focus();
        campo.select();
        const sucesso = document.execCommand("copy");
        status.textContent = sucesso
            ? "SN copiado! Pode colar no sistema."
            : "Selecione o número e copie manualmente.";
    }
}
</script>
</main>
</body>
</html>
"""


ROTULO = re.compile(
    r"S\\s*/\\s*N|S\\.\\s*N\\.?|SERIAL(?:\\s+NUMBER)?|"
    r"N[ÚU]MERO\\s+(?:DE\\s+)?S[ÉE]RIE",
    re.IGNORECASE
)

CODIGO = re.compile(
    r"(?<![A-Z0-9])[A-Z0-9][A-Z0-9-]{5,23}(?![A-Z0-9])"
)


def preparar_imagem(imagem):
    imagem = ImageOps.exif_transpose(imagem)
    imagem.thumbnail((1200, 1200))
    imagem = ImageOps.grayscale(imagem)
    imagem = ImageOps.autocontrast(imagem)
    imagem = ImageEnhance.Contrast(imagem).enhance(1.5)
    return imagem


def extrair_sn(texto):
    linhas = texto.upper().splitlines()
    candidatos = []

    # Primeiro, procura códigos próximos ao rótulo S/N ou Serial.
    for i, linha in enumerate(linhas):
        if ROTULO.search(linha):
            trecho = " ".join(linhas[i:min(i + 3, len(linhas))])
            for codigo in CODIGO.findall(trecho):
                if any(c.isdigit() for c in codigo):
                    candidatos.append(codigo.strip("-"))

    # Se não encontrou rótulo, usa os códigos alfanuméricos encontrados.
    if not candidatos:
        for codigo in CODIGO.findall(texto.upper()):
            if any(c.isdigit() for c in codigo):
                candidatos.append(codigo.strip("-"))

    # Remove duplicados mantendo a ordem.
    candidatos = list(dict.fromkeys(candidatos))

    # Prefere números com 8 a 16 dígitos, comuns em etiquetas.
    candidatos.sort(
        key=lambda c: (
            0 if c.isdigit() and 8 <= len(c) <= 16 else 1,
            -len(c)
        )
    )

    return candidatos[0] if candidatos else None


@app.errorhandler(413)
def arquivo_grande(_erro):
    return render_template_string(
        PAGINA, sn=None,
        erro="A foto ultrapassa 8 MB. Envie uma imagem menor."
    ), 413


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
                imagem.load()
                imagem = preparar_imagem(imagem)

                # Uma única leitura OCR para reduzir o uso de memória.
                texto = pytesseract.image_to_string(
                    imagem,
                    config="--oem 3 --psm 11"
                )

                sn = extrair_sn(texto)

                if not sn:
                    erro = (
                        "Não encontrei o SN. Tente uma foto mais próxima, "
                        "bem iluminada e sem reflexos."
                    )

            except Exception:
                app.logger.exception("Erro ao processar a foto")
                erro = (
                    "Não consegui processar a foto. Tente outra imagem."
                )

    return render_template_string(PAGINA, sn=sn, erro=erro)


if __name__ == "__main__":
    app.run(debug=False, port=5000)

if __name__ == "__main__":
    app.run(debug=False, port=5000)
