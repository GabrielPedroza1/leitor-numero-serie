
import io
import re

import pytesseract
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)

HTML = r"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Leitor de Número de Série</title>
<style>
* { box-sizing: border-box; }

body {
    margin: 0;
    padding: 20px;
    background: #101827;
    color: white;
    font-family: Arial, sans-serif;
    text-align: center;
}

.container {
    width: 100%;
    max-width: 650px;
    margin: auto;
}

h1 { font-size: 25px; }

.hint {
    color: #cbd5e1;
    font-size: 14px;
    line-height: 1.5;
}

button {
    display: block;
    width: 100%;
    min-height: 60px;
    margin-top: 12px;
    padding: 15px;
    border: none;
    border-radius: 12px;
    background: #1767df;
    color: white;
    font-size: 18px;
    font-weight: bold;
    cursor: pointer;
}

button:disabled {
    opacity: .6;
    cursor: wait;
}

#sn {
    display: block;
    width: 100%;
    margin-top: 16px;
    padding: 18px 10px;
    border: 3px solid #1767df;
    border-radius: 12px;
    background: #202b3a;
    color: white;
    font-size: 22px;
    text-align: center;
}

#status {
    margin-top: 16px;
    color: #e2e8f0;
    font-size: 15px;
    line-height: 1.5;
    overflow-wrap: anywhere;
}

.footer {
    margin-top: 20px;
    color: #94a3b8;
    font-size: 13px;
}
</style>
</head>

<body>
<div class="container">
    <h1>Leitor de Número de Série</h1>

    <p class="hint">
        Tire uma foto nítida da etiqueta do equipamento.
    </p>

    <input
        id="cameraInput"
        type="file"
        accept="image/*"
        capture="environment"
        hidden
    >

    <button id="capture">📷 Tirar foto</button>

    <input
        id="sn"
        type="text"
        placeholder="Número de série"
        autocomplete="off"
        aria-label="Número de série"
    >

    <button id="copy">📋 Copiar número</button>

    <p id="status">Pronto para fotografar.</p>

    <p class="footer">
        Confira o número antes de utilizá-lo.
    </p>
</div>

<script>
const cameraInput = document.getElementById("cameraInput");
const captureButton = document.getElementById("capture");
const snInput = document.getElementById("sn");
const statusText = document.getElementById("status");

let processando = false;

captureButton.addEventListener("click", () => {
    if (processando) return;

    // Solicita a câmera traseira do celular.
    cameraInput.click();
});

cameraInput.addEventListener("change", async () => {
    const foto = cameraInput.files[0];

    if (!foto || processando) return;

    processando = true;
    captureButton.disabled = true;
    snInput.value = "";

    statusText.textContent = "Enviando foto para leitura...";

    try {
        const formData = new FormData();
        formData.append("foto", foto, "etiqueta.jpg");

        statusText.textContent = "Lendo número de série...";

        const response = await fetch("/", {
            method: "POST",
            body: formData
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(
                data.erro || "Erro ao processar a foto."
            );
        }

        snInput.value = data.sn || "";

        statusText.textContent = data.sn
            ? "Leitura concluída! Confira o número antes de copiar."
            : "Não consegui identificar o número. Tente outra foto.";

    } catch (error) {
        console.error(error);
        statusText.textContent =
            error.message || "Falha ao enviar a foto.";

    } finally {
        processando = false;
        captureButton.disabled = false;

        // Permite tirar outra foto, inclusive do mesmo equipamento.
        cameraInput.value = "";
    }
});

document.getElementById("copy").addEventListener(
    "click",
    async () => {
        const numero = snInput.value.trim();

        if (!numero) {
            statusText.textContent =
                "Não há número para copiar.";
            return;
        }

        try {
            await navigator.clipboard.writeText(numero);
            statusText.textContent = "Número copiado!";
        } catch (error) {
            snInput.select();
            statusText.textContent =
                "Selecione o número e copie manualmente.";
        }
    }
);
</script>
</body>
</html>
"""


def reconhecer_numero(imagem_bytes):
    imagem = Image.open(
        io.BytesIO(imagem_bytes)
    ).convert("RGB")

    # Evita consumir memória excessiva em fotos de alta resolução.
    imagem.thumbnail((2400, 2400), Image.Resampling.LANCZOS)

    # Amplia para ajudar a leitura de caracteres pequenos.
    imagem = imagem.resize(
        (imagem.width * 2, imagem.height * 2),
        Image.Resampling.LANCZOS
    )

    cinza = ImageOps.grayscale(imagem)
    cinza = ImageOps.autocontrast(cinza)
    cinza = ImageEnhance.Contrast(cinza).enhance(1.8)
    cinza = cinza.filter(ImageFilter.SHARPEN)

    configuracoes = [
        "--oem 1 --psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        "--oem 1 --psm 11 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        "--oem 1 --psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    ]

    resultados = []

    for config in configuracoes:
        texto = pytesseract.image_to_string(
            cinza,
            lang="eng",
            config=config
        )

        candidatos = re.findall(
            r"[A-Z0-9]{5,}",
            texto.upper()
        )

        resultados.extend(candidatos)

    if not resultados:
        binaria = cinza.point(
            lambda pixel: 255 if pixel > 150 else 0
        )

        texto = pytesseract.image_to_string(
            binaria,
            lang="eng",
            config=(
                "--oem 1 --psm 11 "
                "-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
            )
        )

        resultados = re.findall(
            r"[A-Z0-9]{5,}",
            texto.upper()
        )

    if not resultados:
        return ""

    # Remove duplicatas e prefere o maior trecho reconhecido.
    resultados = list(dict.fromkeys(resultados))
    return max(resultados, key=len)


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_template_string(HTML)

    arquivo = request.files.get("foto")

    if arquivo is None:
        return jsonify({
            "erro": "Nenhuma foto foi recebida."
        }), 400

    imagem_bytes = arquivo.read()

    if not imagem_bytes:
        return jsonify({
            "erro": "A foto está vazia."
        }), 400

    try:
        numero = reconhecer_numero(imagem_bytes)
        return jsonify({"sn": numero})

    except pytesseract.TesseractNotFoundError:
        app.logger.exception("Tesseract não encontrado")
        return jsonify({
            "erro": "O Tesseract não está instalado no servidor."
        }), 500

    except Exception:
        app.logger.exception("Erro no reconhecimento OCR")
        return jsonify({
            "erro": "Não foi possível processar a imagem."
        }), 500


if __name__ == "__main__":
    import os
    porta = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=porta)
