
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

.camera {
    position: relative;
    width: 100%;
    overflow: hidden;
    border-radius: 18px;
    background: #000;
}

video {
    display: block;
    width: 100%;
    height: auto;
}

.frame {
    position: absolute;
    left: 10%;
    top: 38%;
    width: 80%;
    height: 20%;
    border: 4px solid #1767df;
    border-radius: 12px;
    pointer-events: none;
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

.hidden { display: none !important; }
</style>
</head>
<body>
<div class="container">
    <h1>Leitor de Número de Série</h1>
    <p class="hint">
        Posicione o número de série dentro da moldura azul.
    </p>

    <div class="camera">
        <video id="video" autoplay playsinline muted></video>
        <div class="frame"></div>
    </div>

    <button id="capture">📷 Tirar foto</button>
    <button id="startCamera" class="hidden">
        📷 Ligar câmera novamente
    </button>

    <input id="sn" type="text"
           placeholder="Número de série"
           autocomplete="off"
           aria-label="Número de série">

    <button id="copy">📋 Copiar número</button>

    <p id="status">Iniciando câmera...</p>
    <p class="footer">Confira o número antes de utilizá-lo.</p>
</div>

<canvas id="canvas" hidden></canvas>

<script>
const video = document.getElementById("video");
const canvas = document.getElementById("canvas");
const captureButton = document.getElementById("capture");
const startButton = document.getElementById("startCamera");
const snInput = document.getElementById("sn");
const statusText = document.getElementById("status");

let cameraStream = null;
let processando = false;

function desligarCamera() {
    if (cameraStream) {
        cameraStream.getTracks().forEach(track => track.stop());
        cameraStream = null;
    }

    video.srcObject = null;
    captureButton.classList.add("hidden");
    startButton.classList.remove("hidden");
}

async function iniciarCamera() {
    if (processando) return;

    startButton.disabled = true;
    statusText.textContent = "Ligando câmera...";

    try {
        cameraStream = await navigator.mediaDevices.getUserMedia({
            audio: false,
            video: {
                facingMode: { ideal: "environment" },
                width: { ideal: 3840 },
                height: { ideal: 2160 }
            }
        });

        video.srcObject = cameraStream;
        await video.play();

        startButton.classList.add("hidden");
        captureButton.classList.remove("hidden");
        statusText.textContent =
            "Câmera pronta. Enquadre a etiqueta.";

    } catch (error) {
        desligarCamera();
        statusText.textContent =
            "Não foi possível abrir a câmera. Verifique as permissões.";
    } finally {
        startButton.disabled = false;
    }
}

captureButton.addEventListener("click", async function () {
    if (processando) return;

    if (!video.videoWidth || !video.videoHeight) {
        statusText.textContent = "A câmera ainda não está pronta.";
        return;
    }

    processando = true;
    captureButton.disabled = true;
    snInput.value = "";
    statusText.textContent = "Capturando foto...";

    try {
        const largura = Math.round(video.videoWidth * 0.80);
        const altura = Math.round(video.videoHeight * 0.20);
        const x = Math.round(video.videoWidth * 0.10);
        const y = Math.round(video.videoHeight * 0.38);

        canvas.width = largura;
        canvas.height = altura;

        canvas.getContext("2d").drawImage(
            video, x, y, largura, altura,
            0, 0, largura, altura
        );

        const blob = await new Promise(resolve => {
            canvas.toBlob(resolve, "image/jpeg", 0.95);
        });

        if (!blob) {
            throw new Error("Não foi possível capturar a foto.");
        }

        // Desliga a câmera enquanto o OCR trabalha.
        desligarCamera();

        statusText.textContent = "Lendo número de série...";

        const formData = new FormData();
        formData.append("foto", blob, "etiqueta.jpg");

        const response = await fetch("/", {
            method: "POST",
            body: formData
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.erro || "Erro ao ler a foto.");
        }

        snInput.value = data.sn || "";
        statusText.textContent = data.sn
            ? "Leitura concluída! Confira o número antes de copiar."
            : "Não consegui identificar o número. Tente outra foto.";

    } catch (error) {
        console.error(error);
        statusText.textContent =
            error.message || "Falha na leitura.";
    } finally {
        processando = false;
        captureButton.disabled = false;
        startButton.classList.remove("hidden");
    }
});

startButton.addEventListener("click", iniciarCamera);

document.getElementById("copy").addEventListener("click", async () => {
    const numero = snInput.value.trim();

    if (!numero) {
        statusText.textContent = "Não há número para copiar.";
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
});

iniciarCamera();
</script>
</body>
</html>
"""


def reconhecer_numero(imagem_bytes):
    imagem = Image.open(io.BytesIO(imagem_bytes)).convert("RGB")

    # Aumenta a imagem para ajudar a leitura dos caracteres pequenos.
    imagem = imagem.resize(
        (imagem.width * 3, imagem.height * 3),
        Image.Resampling.LANCZOS
    )

    cinza = ImageOps.grayscale(imagem)
    cinza = ImageOps.autocontrast(cinza)
    cinza = ImageEnhance.Contrast(cinza).enhance(2.0)
    cinza = cinza.filter(ImageFilter.SHARPEN)

    configuracoes = [
        "--oem 1 --psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        "--oem 1 --psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
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
        # Segunda tentativa com imagem binarizada.
        binaria = cinza.point(
            lambda pixel: 255 if pixel > 150 else 0
        )

        texto = pytesseract.image_to_string(
            binaria,
            lang="eng",
            config=(
                "--oem 1 --psm 7 "
                "-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
            )
        )

        resultados = re.findall(r"[A-Z0-9]{5,}", texto.upper())

    if not resultados:
        return ""

    # Prefere o maior trecho alfanumérico reconhecido.
    return max(resultados, key=len)


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_template_string(HTML)

    arquivo = request.files.get("foto")

    if arquivo is None:
        return jsonify({"erro": "Nenhuma foto foi recebida."}), 400

    imagem_bytes = arquivo.read()

    if not imagem_bytes:
        return jsonify({"erro": "A foto está vazia."}), 400

    try:
        numero = reconhecer_numero(imagem_bytes)
        return jsonify({"sn": numero})

    except pytesseract.TesseractNotFoundError:
        app.logger.exception("Executável Tesseract não encontrado")
        return jsonify({
            "erro": "O Tesseract não está instalado no servidor."
        }), 500

    except Exception:
        app.logger.exception("Falha no reconhecimento OCR")
        return jsonify({
            "erro": "Não foi possível processar a imagem."
        }), 500


if __name__ == "__main__":
    porta = int(__import__("os").environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=porta)
