import os
import re
import base64
from flask import Flask, request, jsonify, render_template_string
from openai import OpenAI

app = Flask(__name__)

HTML = """
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
    max-width: 600px;
    margin: auto;
}

h1 {
    font-size: 25px;
    margin-bottom: 12px;
}

.hint {
    color: #b8c5d6;
    font-size: 14px;
    line-height: 1.5;
}

.camera {
    position: relative;
    width: 100%;
    overflow: hidden;
    border-radius: 16px;
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
    border: 3px solid #1767df;
    border-radius: 6px;
    pointer-events: none;
}

button {
    width: 100%;
    min-height: 56px;
    padding: 16px;
    margin-top: 12px;
    border: none;
    border-radius: 9px;
    background: #1767df;
    color: white;
    font-size: 17px;
    font-weight: bold;
    cursor: pointer;
}

button:active {
    background: #0f4eb5;
}

button:disabled {
    opacity: 0.6;
    cursor: wait;
}

#sn {
    display: block;
    width: 100%;
    margin-top: 16px;
    padding: 15px;
    border: 2px solid #1767df;
    border-radius: 9px;
    background: #202b3a;
    color: white;
    font-size: 22px;
    text-align: center;
    outline: none;
}

#sn:focus {
    border-color: #60a5fa;
}

#status {
    min-height: 24px;
    margin-top: 12px;
    color: #d6d6d6;
    font-size: 14px;
    line-height: 1.5;
    overflow-wrap: anywhere;
}
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

    <button id="capture">Tirar foto</button>

    <input
        id="sn"
        type="text"
        placeholder="Número de série"
        autocomplete="off"
        aria-label="Número de série"
    >

    <button id="copy">Copiar número</button>

    <p id="status">Iniciando câmera...</p>
</div>

<canvas id="canvas" hidden></canvas>

<script>
const video = document.getElementById("video");
const canvas = document.getElementById("canvas");
const captureButton = document.getElementById("capture");
const snInput = document.getElementById("sn");
const statusText = document.getElementById("status");

async function iniciarCamera() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            audio: false,
            video: {
                facingMode: { ideal: "environment" },
                width: { ideal: 3840 },
                height: { ideal: 2160 },
                frameRate: { ideal: 30 }
            }
        });

        video.srcObject = stream;
        await video.play();

        statusText.textContent =
            "Câmera pronta. Enquadre a etiqueta e tire a foto.";
    } catch (error) {
        statusText.textContent =
            "Não foi possível abrir a câmera. Verifique a permissão do navegador.";
    }
}

captureButton.addEventListener("click", async () => {
    if (!video.videoWidth || !video.videoHeight) {
        statusText.textContent = "A câmera ainda não está pronta.";
        return;
    }

    captureButton.disabled = true;
    statusText.textContent = "Analisando a foto...";
    snInput.value = "";

    try {
        // Mantém o enquadramento original da câmera.
        const largura = Math.round(video.videoWidth * 0.80);
        const altura = Math.round(video.videoHeight * 0.20);
        const x = Math.round(video.videoWidth * 0.10);
        const y = Math.round(video.videoHeight * 0.38);

        canvas.width = largura;
        canvas.height = altura;

        const ctx = canvas.getContext("2d");
        ctx.drawImage(
            video,
            x, y, largura, altura,
            0, 0, largura, altura
        );

        const blob = await new Promise(resolve => {
            canvas.toBlob(resolve, "image/jpeg", 0.98);
        });

        if (!blob) {
            throw new Error("Não foi possível tirar a foto.");
        }

        const formData = new FormData();
        formData.append("foto", blob, "etiqueta.jpg");

        const response = await fetch("/", {
            method: "POST",
            body: formData
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.erro || "Falha ao processar a foto.");
        }

        snInput.value = data.sn || "";

        statusText.textContent = data.sn
            ? "Leitura concluída. Confira o número antes de copiar."
            : "Não consegui identificar o número. Aproxime a câmera e tente novamente.";

    } catch (error) {
        statusText.textContent =
            error.message || "Erro ao processar a foto.";
    } finally {
        captureButton.disabled = false;
    }
});

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


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_template_string(HTML)

    if "foto" not in request.files:
        return jsonify({"erro": "Nenhuma foto foi recebida."}), 400

    imagem_bytes = request.files["foto"].read()

    if not imagem_bytes:
        return jsonify({"erro": "A foto está vaz
