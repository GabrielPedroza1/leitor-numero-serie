
import os
import re
import io
import unicodedata

from flask import Flask, request, render_template_string
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import pytesseract
from pytesseract import TesseractError


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

# No Windows, configure o caminho do Tesseract se necessário.
if os.name == "nt":
    caminho = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(caminho):
        pytesseract.pytesseract.tesseract_cmd = caminho


PAGINA = """
<!DOCTYPE html>
<html lang="pt-br">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Leitor de Número de Série</title>
<style>
* { box-sizing: border-box; }
body {
    font-family: Arial, sans-serif;
    background: #f1f5f9;
    margin: 0;
    padding: 20px;
    color: #172033;
}
main {
    max-width: 520px;
    margin: 20px auto;
    background: white;
    padding: 24px;
    border-radius: 16px;
    box-shadow: 0 5px 24px #00000012;
}
h1 { font-size: 24px; margin-top: 0; }
p { color: #586174; line-height: 1.5; }
label { display: block; font-weight: bold; margin: 16px 0 8px; }
select, input[type=file], input[type=text] {
    width: 100%;
    padding: 13px;
    border: 1px solid #cbd5e1;
    border-radius: 9px;
    background: white;
    font-size: 16px;
}
button {
    width: 100%;
    padding: 14px;
    margin-top: 12px;
    border: 0;
    border-radius: 9px;
    background: #1769e0;
    color: white;
    font-size: 16px;
    font-weight: bold;
    cursor: pointer;
}
button.secondary { background: #172033; }
.status { margin-top: 16px; font-weight: bold; }
.small { font-size: 13px; }
</style>
</head>
<body>
<main>
<h1>Leitor de Número de Série</h1>
<p>Envie uma foto da etiqueta ou da tela do equipamento.</p>

<form method="POST" enctype="multipart/form-data"
      onsubmit="document.getElementById('status').textContent='Lendo imagem... aguarde.';">
    <label for="modo">Tipo de leitura</label>
    <select id="modo" name="modo">
        <option value="etiqueta" {% if modo == 'etiqueta' %}selected{% endif %}>
            Etiqueta do equipamento
        </option>
        <option value="tela" {% if modo == 'tela' %}selected{% endif %}>
            Máquina ligada — SN na tela
        </option>
    </select>

    <label for="foto">Foto do equipamento</label>
    <input id="foto" type="file" name="foto"
           accept="image/*" capture="environment" required>

    <button type="submit">Ler SN</button>
</form>

{% if resultado is not none %}
    <label for="serie">Número de série (SN)</label>
    <input type="text" id="serie" value="{{ resultado }}" autocomplete="off">
    <button type="button" onclick="copiarSN()">Copiar SN</button>
    <p id="copia" class="status" aria-live="polite"></p>
    {% if not resultado %}
    <p>Não consegui identificar o SN com segurança. Tente uma foto mais próxima,
    nítida e sem reflexos.</p>
    {% endif %}
{% endif %}

<p id="status" class="status" aria-live="polite"></p>
<p class="small">Confira o número reconhecido antes de utilizá-lo.</p>
</main>
<script>
async function copiarSN() {
    const campo = document.getElementById("serie");
    const aviso = document.getElementById("copia");
    const valor = campo.value.trim();

    if (!valor) {
        aviso.textContent = "Nenhum SN para copiar.";
        return;
    }

    try {
        await navigator.clipboard.writeText(valor);
        aviso.textContent = "SN copiado!";
    } catch (e) {
        campo.select();
        const ok = document.execCommand("copy");
        aviso.textContent = ok ? "SN copiado!" : "Selecione e copie o código.";
    }
}
</script>
</body>
</html>
"""


def preparar_imagem(imagem):
    imagem = ImageOps.exif_transpose(imagem)
    imagem.thumbnail((1600, 1600))
    imagem = imagem.convert("RGB")

    cinza = ImageOps.grayscale(imagem)
    cinza = ImageEnhance.Contrast(cinza).enhance(1.8)
    cinza = cinza.filter(ImageFilter.SHARPEN)

    # Amplia moderadamente para ajudar na leitura de códigos pequenos.
    if cinza.width < 1200:
        fator = min(2, 1200 / cinza.width)
        cinza = cinza.resize(
            (int(cinza.width * fator), int(cinza.height * fator)),
            Image.Resampling.LANCZOS
        )

    return cinza


def executar_ocr(imagem, config):
    return pytesseract.image_to_string(
        imagem,
        config=config,
        timeout=12
    )


def normalizar_linha(texto):
    return unicodedata.normalize("NFKC", texto).strip()


def limpar_codigo(codigo):
    codigo = codigo.strip(" \t:;,.|[](){}")
    codigo = re.sub(r"[^A-Za-z0-9-]", "", codigo)
    return codigo.upper()


def encontrar_sn(texto, modo):
    linhas = [
        normalizar_linha(linha)
        for linha in texto.splitlines()
        if linha.strip()
    ]

    # Rótulos explícitos têm prioridade.
    rotulo = re.compile(
        r"(?:S\s*/\s*N|S\.?\s*N\.?|SERIAL\s*(?:NO\.?|NUMBER|NUMERO|N[ÚU]MERO)?)",
        re.IGNORECASE
    )

    padrao_codigo = re.compile(
        r"(?<![A-Za-z0-9])[A-Za-z0-9][A-Za-z0-9-]{7,23}(?![A-Za-z0-9])"
    )

    for i, linha in enumerate(linhas):
        if rotulo.search(linha):
            trecho = linha[rotulo.search(linha).end():]
            candidatos = padrao_codigo.findall(trecho)

            if not candidatos and i + 1 < len(linhas):
                candidatos = padrao_codigo.findall(linhas[i + 1])

            for candidato in candidatos:
                codigo = limpar_codigo(candidato)
                if len(codigo) >= 8 and re.search(r"\d", codigo):
                    return codigo

    # No modo tela, não escolhe qualquer número aleatório.
    # Procura termos que costumam identificar a informação.
    if modo == "tela":
        rotulo_tela = re.compile(
            r"(?:SERIAL|S/N|SN|NUMERO DE SERIE|NÚMERO DE SÉRIE)",
            re.IGNORECASE
        )
        for i, linha in enumerate(linhas):
            if rotulo_tela.search(linha):
                candidatos = padrao_codigo.findall(linha)
                if not candidatos and i + 1 < len(linhas):
                    candidatos = padrao_codigo.findall(linhas[i + 1])

                for candidato in candidatos:
                    codigo = limpar_codigo(candidato)
                    if len(codigo) >= 8 and re.search(r"\d", codigo):
                        return codigo

    return ""


@app.route("/", methods=["GET", "POST"])
def inicio():
    resultado = None
    modo = "etiqueta"

    if request.method == "POST":
        modo = request.form.get("modo", "etiqueta")
        arquivo = request.files.get("foto")

        if arquivo and arquivo.filename:
            try:
                imagem = Image.open(io.BytesIO(arquivo.read()))
                imagem = preparar_imagem(imagem)

                # Primeira tentativa: leitura normal, preservando letras.
                config = (
                    "--oem 3 --psm 11 "
                    "-c load_system_dawg=false "
                    "-c load_freq_dawg=false"
                )
                texto = executar_ocr(imagem, config)

                resultado = encontrar_sn(texto, modo)

                # Segunda tentativa com segmentação diferente.
                if not resultado:
                    texto2 = executar_ocr(
                        imagem,
                        "--oem 3 --psm 6 "
                        "-c load_system_dawg=false "
                        "-c load_freq_dawg=false"
                    )
                    resultado = encontrar_sn(texto2, modo)

            except (OSError, ValueError):
                resultado = ""
            except TesseractError:
                resultado = ""
            except Exception:
                resultado = ""

    return render_template_string(
        PAGINA,
        resultado=resultado,
        modo=modo
    )


@app.errorhandler(413)
def arquivo_grande(_erro):
    return "A foto é muito grande. Envie uma imagem de até 8 MB.", 413


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))


if __name__ == "__main__":
    app.run(debug=False, port=5000)
