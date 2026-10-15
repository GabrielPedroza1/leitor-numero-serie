
import io
import os
import re
from collections import Counter

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
    padding: 16px 12px;
    background: #f0f3f9;
    color: #202b3d;
    font-family: Arial, sans-serif;
}

.card {
    max-width: 650px;
    margin: 12px auto;
    padding: 22px 18px;
    background: white;
    border-radius: 22px;
}

h1 { font-size: 26px; }

p {
    color: #596579;
    font-size: 17px;
    line-height: 1.5;
}

button {
    width: 100%;
    padding: 16px 10px;
    margin-top: 12px;
    border: 0;
    border-radius: 12px;
    font-size: 18px;
    font-weight: bold;
    cursor: pointer;
}

.primary { background: #1767df; color: white; }
.dark { background: #263244; color: white; }
button:disabled { opacity: .55; }

#cameraArea {
    display: none;
    margin-top: 18px;
}

.videoBox {
    position: relative;
    width: 100%;
    overflow: hidden;
    background: #111;
    border-radius: 12px;
}

video {
    display: block;
    width: 100%;
    max-height: 65vh;
    object-fit: contain;
}

/* Esta moldura também define a região capturada. */
.frame {
    position: absolute;
    left: 10%;
    top: 38%;
    width: 80%;
    height: 20%;
    border: 3px solid #22e56b;
    border-radius: 8px;
    pointer-events: none;
}

.zoomArea {
    margin-top: 18px;
}

.zoomArea label {
    display: block;
    font-weight: bold;
}

input[type=range] {
    width: 100%;
    margin-top: 12px;
}

#result {
    display: none;
    margin-top: 22px;
    padding: 18px;
    border-radius: 16px;
    background: #eaf2ff;
}

#sn {
    width: 100%;
    padding: 16px;
    font-size: 23px;
    border: 1px solid #bdc9d9;
    border-radius: 10px;
}

#status, #message {
    margin-top: 12px;
    font-size: 15px;
}

.small { font-size: 14px; }
</style>
</head>

<body>
<div class="card">

    <h1>Leitor de Número de Série</h1>

    <p>
        Coloque a etiqueta branca dentro da moldura verde.
        Espere a imagem ficar nítida e tire uma foto.
    </p>

    <button id="openBtn" class="dark" onclick="abrirCamera()">
        Abrir câmera
    </button>

    <div id="cameraArea">

        <div class="videoBox">
            <video id="video" autoplay playsinline muted></video>
            <div class="frame"></div>
        </div>

        <div class="zoomArea">
            <label for="zoom">Zoom da câmera</label>
            <input
                id="zoom"
                type="range"
                min="1"
                max="1"
                step="0.1"
                value="1"
                oninput="mudarZoom(this.value)"
            >
            <div id="zoomInfo" class="small">
                Ajuste o zoom se necessário.
            </div>
        </div>

        <p class="small">
            Mantenha todo o número S/N dentro da moldura verde.
        </p>

        <button id="captureBtn" class="primary" onclick="tirarFoto()">
            Tirar foto e ler SN
        </button>

        <button class="dark" onclick="fecharCamera()">
            Fechar câmera
        </button>

    </div>

    <div id="status" role="status"></div>

    <div id="result">
        <label for="sn">SN reconhecido — confira antes de copiar</label>

        <input
            id="sn"
            type="text"
            autocomplete="off"
            spellcheck="false"
        >

        <button class="primary" onclick="copiarSN()">
            Copiar SN
        </button>

        <button class="dark" onclick="novaFoto()">
            Tirar outra foto
        </button>

        <div id="message"></div>
    </div>

    <p class="small">
        Confira todos os caracteres antes de utilizar o número.
    </p>

</div>

<script>
let stream = null;
let track = null;
let ocupado = false;

const video = document.getElementById("video");
const openBtn = document.getElementById("openBtn");
const cameraArea = document.getElementById("cameraArea");
const captureBtn = document.getElementById("captureBtn");
const statusBox = document.getElementById("status");
const resultBox = document.getElementById("result");
const snInput = document.getElementById("sn");
const message = document.getElementById("message");
const zoomControl = document.getElementById("zoom");
const zoomInfo = document.getElementById("zoomInfo");

async function abrirCamera() {
    try {
        statusBox.textContent = "Abrindo câmera...";

        stream = await navigator.mediaDevices.getUserMedia({
            audio: false,
            video: {
                facingMode: { ideal: "environment" },
                width: { ideal: 1920 },
                height: { ideal: 1080 }
            }
        });

        video.srcObject = stream;
        track = stream.getVideoTracks()[0];

        await new Promise(resolve => {
            if (video.readyState >= 1) return resolve();
            video.onloadedmetadata = resolve;
        });

        await video.play();

        try {
            const capacidades = track.getCapabilities();
            const ajustes = {};

            if (
                capacidades.focusMode &&
                capacidades.focusMode.includes("continuous")
            ) {
                ajustes.focusMode = "continuous";
            }

            if (Object.keys(ajustes).length) {
                await track.applyConstraints({
                    advanced: [ajustes]
                });
            }

            if (capacidades.zoom) {
                zoomControl.min = capacidades.zoom.min || 1;
                zoomControl.max = capacidades.zoom.max || 1;
                zoomControl.step = capacidades.zoom.step || 0.1;
                zoomControl.value = Math.max(
                    Number(zoomControl.min),
                    Math.min(1, Number(zoomControl.max))
                );

                zoomControl.disabled =
                    Number(zoomControl.max) <=
                    Number(zoomControl.min);

                zoomInfo.textContent = zoomControl.disabled
                    ? "Zoom não disponível neste aparelho."
                    : "Deslize para aproximar ou afastar.";
            } else {
                zoomControl.min = 1;
                zoomControl.max = 1;
                zoomControl.value = 1;
                zoomControl.disabled = true;
                zoomInfo.textContent =
                    "O navegador não permite controlar o zoom.";
            }

        } catch (erro) {
            console.log("Foco ou zoom indisponível", erro);
        }

        cameraArea.style.display = "block";
        openBtn.style.display = "none";
        resultBox.style.display = "none";
        statusBox.textContent = "";

    } catch (erro) {
        fecharCamera();
        statusBox.textContent =
            "Não foi possível abrir a câmera. Confira a permissão do navegador.";
    }
}

async function mudarZoom(valor) {
    if (!track || zoomControl.disabled) return;

    try {
        await track.applyConstraints({
            advanced: [{ zoom: Number(valor) }]
        });

        zoomInfo.textContent =
            "Zoom: " + Number(valor).toFixed(1) + "x";

    } catch (erro) {
        zoomInfo.textContent =
            "Não foi possível alterar o zoom.";
    }
}

function fecharCamera() {
    if (stream) {
        stream.getTracks().forEach(t => t.stop());
    }

    stream = null;
    track = null;
    video.srcObject = null;
    cameraArea.style.display = "none";
    openBtn.style.display = "block";
}

async function tirarFoto() {
    if (ocupado) return;

    if (!video.videoWidth || !video.videoHeight) {
        statusBox.textContent = "Aguarde a câmera carregar.";
        return;
    }

    ocupado = true;
    captureBtn.disabled = true;
    resultBox.style.display = "none";
    statusBox.textContent = "Lendo a etiqueta...";

    try {
        const largura = video.videoWidth;
        const altura = video.videoHeight;

        /*
         * Recorta a região da moldura verde.
         * As proporções são iguais às usadas no CSS.
         */
        const x = Math.round(largura * 0.10);
        const y = Math.round(altura * 0.38);
        const w = Math.round(largura * 0.80);
        const h = Math.round(altura * 0.20);

        const canvas = document.createElement("canvas");

        // Amplia o recorte antes de enviar para o OCR.
        const escala = 3;
        canvas.width = w * escala;
        canvas.height = h * escala;

        const contexto = canvas.getContext("2d");

        contexto.imageSmoothingEnabled = true;
        contexto.imageSmoothingQuality = "high";

        contexto.drawImage(
            video,
            x, y, w, h,
            0, 0, canvas.width, canvas.height
        );

        const blob = await new Promise(resolve => {
            canvas.toBlob(resolve, "image/jpeg", 0.98);
        });

        if (!blob) {
            throw new Error("Não foi possível capturar a foto.");
        }

        const dados = new FormData();
        dados.append("foto", blob, "etiqueta.jpg");

        const resposta = await fetch("/", {
            method: "POST",
            body: dados
        });

        const resultado = await resposta.json();

        if (!resposta.ok) {
            throw new Error(resultado.erro || "Falha na leitura.");
        }

        snInput.value = resultado.sn || "";
        resultBox.style.display = "block";

        if (resultado.sn) {
            statusBox.textContent = "Leitura concluída.";
            message.textContent =
                "Confira o número na etiqueta antes de copiar.";
            snInput.focus();
            snInput.select();
        } else {
            statusBox.textContent = "SN não identificado.";
            message.textContent =
                "Confira se a etiqueta inteira está dentro da moldura e tente novamente.";
        }

    } catch (erro) {
        statusBox.textContent =
            erro.message || "Erro ao processar a foto.";

    } finally {
        ocupado = false;
        captureBtn.disabled = false;
    }
}

async function copiarSN() {
    const valor = snInput.value.trim();

    if (!valor) {
        message.textContent = "Não há número para copiar.";
        return;
    }

    try {
        await navigator.clipboard.writeText(valor);
        message.textContent = "SN copiado!";

    } catch (erro) {
        snInput.focus();
        snInput.select();
        message.textContent =
            "Selecione o número e copie manualmente.";
    }
}

function novaFoto() {
    resultBox.style.display = "none";
    statusBox.textContent = "";

    if (!stream) {
        abrirCamera();
    }
}
</script>
</body>
</html>
"""


def preparar_imagens(imagem):
    imagem = ImageOps.exif_transpose(imagem).convert("RGB")

    # Amplia a imagem recortada para ajudar na leitura.
    if imagem.width < 1800:
        escala = 1800 / imagem.width
        imagem = imagem.resize(
            (1800, int(imagem.height * escala)),
            Image.Resampling.LANCZOS
        )

    cinza = ImageOps.grayscale(imagem)
    cinza = ImageEnhance.Contrast(cinza).enhance(2.0)
    cinza = cinza.filter(ImageFilter.SHARPEN)

    binaria = cinza.point(
        lambda p: 255 if p > 150 else 0
    )

    return [cinza, binaria]


def limpar_candidato(texto):
    texto = texto.upper().strip()
    texto = re.sub(r"[^A-Z0-9]", "", texto)

    if len(texto) < 6 or len(texto) > 24:
        return ""

    if not any(c.isdigit() for c in texto):
        return ""

    return texto


def extrair_sn(texto):
    texto = texto.upper().replace("\n", " ")

    padroes = [
        r"(?:S\s*/\s*N|S\.?\s*N\.?|SERIAL\s*(?:NO|NUMBER|NUMERO)?)[\s:#-]*([A-Z0-9][A-Z0-9 -]{5,23})",
        r"N[ÚU]MERO\s*DE\s*S[ÉE]RIE[\s:#-]*([A-Z0-9][A-Z0-9 -]{5,23})"
    ]

    for padrao in padroes:
        for achado in re.findall(padrao, texto):
            candidato = limpar_candidato(achado)
            if candidato:
                return candidato

    # Plano alternativo quando o rótulo S/N não é reconhecido.
    sequencias = re.findall(
        r"\b[A-Z0-9][A-Z0-9-]{7,23}\b",
        texto
    )

    candidatos = [
        limpar_candidato(item) for item in sequencias
    ]
    candidatos = [item for item in candidatos if item]

    return max(candidatos, key=len) if candidatos else ""


def reconhecer_sn(arquivo):
    imagem = Image.open(io.BytesIO(arquivo))
    versoes = preparar_imagens(imagem)

    candidatos_rotulados = []
    candidatos_gerais = []

    configs = [
        "--oem 3 --psm 6",
        "--oem 3 --psm 11",
        "--oem 3 --psm 7",
        "--oem 3 --psm 13"
    ]

    for versao in versoes:
        for config in configs:
            texto = pytesseract.image_to_string(
                versao,
                config=config
            )

            candidato = extrair_sn(texto)

            if not candidato:
                continue

            rotulo_encontrado = re.search(
                r"S\s*/\s*N|S\.?\s*N\.?|SERIAL|N[ÚU]MERO\s*DE\s*S[ÉE]RIE",
                texto.upper()
            )

            if rotulo_encontrado:
                candidatos_rotulados.append(candidato)
            else:
                candidatos_gerais.append(candidato)

    candidatos = (
        candidatos_rotulados
        if candidatos_rotulados
        else candidatos_gerais
    )

    if not candidatos:
        return ""

    # Escolhe a leitura que apareceu mais vezes.
    contagem = Counter(candidatos)
    return contagem.most_common(1)[0][0]


@app.route("/", methods=["GET", "POST"])
def inicio():
    if request.method == "POST":
        foto = request.files.get("foto")

        if not foto or not foto.filename:
            return jsonify({
                "erro": "Nenhuma foto recebida."
            }), 400

        try:
            sn = reconhecer_sn(foto.read())
            return jsonify({"sn": sn})

        except Exception:
            app.logger.exception("Erro no OCR")

            return jsonify({
                "erro": "Não foi possível processar a imagem."
            }), 500

    return render_template_string(HTML)


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )

