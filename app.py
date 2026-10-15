
import io
import re
import os
from collections import Counter

import pytesseract
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)

# No Railway, o Tesseract deve estar instalado pelo Dockerfile.
TESSERACT_CONFIGS = [
    "--oem 3 --psm 6",
    "--oem 3 --psm 11",
    "--oem 3 --psm 7",
]

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
    padding: 20px 14px;
    background: #f0f3f9;
    color: #202b3d;
    font-family: Arial, sans-serif;
}
.card {
    max-width: 650px;
    margin: 20px auto;
    padding: 26px 22px;
    background: white;
    border-radius: 26px;
}
h1 { font-size: 27px; margin: 8px 0 24px; }
p { color: #5d6675; font-size: 18px; line-height: 1.5; }
button {
    width: 100%;
    border: 0;
    border-radius: 12px;
    padding: 17px 12px;
    margin-top: 12px;
    font-size: 18px;
    font-weight: bold;
    cursor: pointer;
}
.primary { background: #1767df; color: white; }
.dark { background: #263244; color: white; }
button:disabled { opacity: .55; }
#cameraArea { display: none; margin-top: 18px; }
.videoBox {
    position: relative;
    width: 100%;
    overflow: hidden;
    background: #111827;
    border-radius: 14px;
}
video {
    display: block;
    width: 100%;
    max-height: 65vh;
    object-fit: contain;
}
.frame {
    position: absolute;
    left: 5%;
    top: 30%;
    width: 90%;
    height: 40%;
    border: 3px solid #22e56b;
    border-radius: 10px;
    pointer-events: none;
    box-shadow: 0 0 0 999px rgba(0,0,0,.13);
}
.hint { font-size: 15px; text-align: center; }
#status { font-size: 16px; margin-top: 14px; }
#result {
    display: none;
    background: #eaf2ff;
    border-radius: 18px;
    padding: 20px;
    margin-top: 24px;
}
label { display: block; font-weight: bold; margin-bottom: 12px; }
input[type=text] {
    width: 100%;
    padding: 17px;
    font-size: 23px;
    border: 1px solid #cbd5e1;
    border-radius: 12px;
    background: white;
    color: #111827;
}
#message { font-size: 15px; margin-top: 12px; }
.small { font-size: 14px; color: #687386; }
</style>
</head>
<body>
<div class="card">
    <h1>Leitor de Número de Série</h1>
    <p>Enquadre a etiqueta na moldura verde, tire uma foto e confira o SN reconhecido.</p>

    <button id="openBtn" class="dark" onclick="abrirCamera()">
        Abrir câmera
    </button>

    <div id="cameraArea">
        <div class="videoBox">
            <video id="video" autoplay playsinline muted></video>
            <div class="frame"></div>
        </div>
        <p class="hint">Aproxime a etiqueta, mantenha o celular firme e deixe o SN bem iluminado.</p>
        <button id="captureBtn" class="primary" onclick="tirarFoto()">
            Tirar foto e ler SN
        </button>
        <button class="dark" onclick="fecharCamera()">Fechar câmera</button>
    </div>

    <div id="status" role="status"></div>

    <div id="result">
        <label for="sn">SN reconhecido — confira antes de copiar</label>
        <input id="sn" type="text" autocomplete="off" spellcheck="false">
        <button class="primary" onclick="copiarSN()">Copiar SN</button>
        <button class="dark" onclick="novaFoto()">Tirar outra foto</button>
        <div id="message"></div>
    </div>

    <p class="small">Confira todos os caracteres antes de utilizar o número.</p>
</div>

<script>
let stream = null;
let ocupado = false;

const video = document.getElementById("video");
const openBtn = document.getElementById("openBtn");
const cameraArea = document.getElementById("cameraArea");
const captureBtn = document.getElementById("captureBtn");
const statusBox = document.getElementById("status");
const resultBox = document.getElementById("result");
const snInput = document.getElementById("sn");
const message = document.getElementById("message");

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
        await new Promise(resolve => {
            if (video.readyState >= 1) return resolve();
            video.onloadedmetadata = resolve;
        });
        await video.play();

        cameraArea.style.display = "block";
        openBtn.style.display = "none";
        resultBox.style.display = "none";
        statusBox.textContent = "";
    } catch (e) {
        statusBox.textContent =
            "Não foi possível abrir a câmera. Permita o acesso à câmera no navegador e tente novamente.";
    }
}

function fecharCamera() {
    if (stream) {
        stream.getTracks().forEach(track => track.stop());
        stream = null;
    }
    video.srcObject = null;
    cameraArea.style.display = "none";
    openBtn.style.display = "block";
}

async function tirarFoto() {
    if (ocupado) return;

    if (!video.videoWidth || !video.videoHeight) {
        statusBox.textContent = "A câmera ainda está carregando. Tente novamente.";
        return;
    }

    ocupado = true;
    captureBtn.disabled = true;
    resultBox.style.display = "none";
    statusBox.textContent = "Lendo a etiqueta...";

    try {
        const canvas = document.createElement("canvas");
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        canvas.getContext("2d").drawImage(
            video, 0, 0, canvas.width, canvas.height
        );

        const blob = await new Promise(resolve =>
            canvas.toBlob(resolve, "image/jpeg", 0.95)
        );

        if (!blob) throw new Error("Não foi possível capturar a foto.");

        const data = new FormData();
        data.append("foto", blob, "etiqueta.jpg");

        const response = await fetch("/", {
            method: "POST",
            body: data
        });
        const resultado = await response.json();

        if (!response.ok) {
            throw new Error(resultado.erro || "Falha ao ler a imagem.");
        }

        snInput.value = resultado.sn || "";
        resultBox.style.display = "block";

        if (resultado.sn) {
            message.textContent =
                "Confira se cada letra e número corresponde à etiqueta.";
            snInput.focus();
            snInput.select();
            statusBox.textContent = "Leitura concluída.";
        } else {
            message.textContent =
                "Não consegui identificar o SN com segurança. Aproxime a câmera e tente outra foto.";
            statusBox.textContent = "Número não identificado.";
        }
    } catch (e) {
        statusBox.textContent = e.message || "Erro ao processar a foto.";
    } finally {
        ocupado = false;
        captureBtn.disabled = false;
    }
}

async function copiarSN() {
    const valor = snInput.value.trim();
    if (!valor) {
        message.textContent = "Nenhum SN para copiar. Tire outra foto.";
        return;
    }

    try {
        await navigator.clipboard.writeText(valor);
        message.textContent = "SN copiado!";
    } catch (e) {
        snInput.focus();
        snInput.select();
        message.textContent =
            "Não foi possível copiar automaticamente. Selecione o número e copie manualmente.";
    }
}

function novaFoto() {
    resultBox.style.display = "none";
    statusBox.textContent = "";
    if (!stream) abrirCamera();
}
</script>
</body>
</html>
"""


def preparar_imagens(imagem):
    """Cria versões da foto para o Tesseract tentar ler melhor."""
    imagem = ImageOps.exif_transpose(imagem).convert("RGB")
    largura, altura = imagem.size

    # Mantém a foto inteira e cria uma versão ampliada.
    if largura < 1400:
        escala = 1400 / largura
        imagem = imagem.resize(
            (int(largura * escala), int(altura * escala)),
            Image.Resampling.LANCZOS
        )

    cinza = ImageOps.grayscale(imagem)
    cinza = ImageEnhance.Contrast(cinza).enhance(2.0)
    nitida = cinza.filter(ImageFilter.SHARPEN)

    # Duas versões: tons de cinza e preto/branco.
    limiar = nitida.point(lambda p: 255 if p > 155 else 0)

    return [nitida, limiar]


def limpar_candidato(texto):
    texto = texto.upper().strip()
    texto = re.sub(r"[^A-Z0-9]", "", texto)

    # Não transforma letras em números automaticamente:
    # isso poderia inventar um serial que não está na etiqueta.
    if len(texto) < 6 or len(texto) > 24:
        return ""
    if not any(c.isdigit() for c in texto):
        return ""
    return texto


def extrair_sn(texto):
    texto = texto.upper().replace("\n", " ")

    # Procura primeiro um número imediatamente associado a SN/S/N.
    padroes = [
        r"(?:S\s*/\s*N|S\.?\s*N\.?|SERIAL\s*(?:NO|NUMBER|NUMERO)?)[\s:#-]*([A-Z0-9][A-Z0-9 -]{5,23})",
        r"(?:N[ÚU]MERO\s*DE\s*S[ÉE]RIE)[\s:#-]*([A-Z0-9][A-Z0-9 -]{5,23})",
    ]

    for padrao in padroes:
        encontrados = re.findall(padrao, texto)
        for encontrado in encontrados:
            candidato = limpar_candidato(encontrado)
            if candidato:
                return candidato

    # Se não identificou o rótulo SN, tenta sequências longas isoladas.
    sequencias = re.findall(r"\b[A-Z0-9][A-Z0-9-]{7,23}\b", texto)
    candidatos = [limpar_candidato(s) for s in sequencias]
    candidatos = [c for c in candidatos if c]

    if candidatos:
        return max(candidatos, key=len)

    return ""


def reconhecer_sn(arquivo):
    imagem = Image.open(io.BytesIO(arquivo))
    versoes = preparar_imagens(imagem)
    leituras = []

    for versao in versoes:
        for config in TESSERACT_CONFIGS:
            texto = pytesseract.image_to_string(versao, config=config)
            if texto.strip():
                leituras.append(texto)

    # Dá prioridade às leituras em que o OCR encontrou SN/S/N.
    candidatos_rotulados = []
    candidatos_gerais = []

    for texto in leituras:
        achou_rotulo = re.search(
            r"S\s*/\s*N|S\.?\s*N\.?|SERIAL|N[ÚU]MERO\s*DE\s*S[ÉE]RIE",
            texto.upper()
        )
        candidato = extrair_sn(texto)
        if candidato:
            if achou_rotulo:
                candidatos_rotulados.append(candidato)
            else:
                candidatos_gerais.append(candidato)

    candidatos = candidatos_rotulados or candidatos_gerais
    if not candidatos:
        return ""

    # Escolhe a leitura mais repetida entre as tentativas.
    contagem = Counter(candidatos)
    mais_comum, repeticoes = contagem.most_common(1)[0]

    # Não promete certeza: o campo continua editável para conferência.
    return mais_comum


@app.route("/", methods=["GET", "POST"])
def inicio():
    if request.method == "POST":
        if "foto" not in request.files:
            return jsonify({"erro": "Nenhuma foto recebida."}), 400

        foto = request.files["foto"]
        if not foto.filename:
            return jsonify({"erro": "Foto vazia."}), 400

        try:
            sn = reconhecer_sn(foto.read())
            return jsonify({"sn": sn})
        except Exception as erro:
            app.logger.exception("Erro no OCR")
            return jsonify({
                "erro": "Não foi possível processar a foto. Tente novamente."
            }), 500

    return render_template_string(HTML)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
