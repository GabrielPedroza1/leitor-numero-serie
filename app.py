
import os
import io
import re

from flask import Flask, request, render_template_string
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import pytesseract
from pytesseract import TesseractError

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

if os.name == "nt":
    caminho = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(caminho):
        pytesseract.pytesseract.tesseract_cmd = caminho


HTML = """
<!DOCTYPE html>
<html lang="pt-br">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Leitor de Número de Série</title>
<style>
* { box-sizing: border-box; }
body {
    margin: 0; padding: 14px; background: #f1f5f9;
    font-family: Arial, sans-serif; color: #172033;
}
main {
    max-width: 500px; margin: 12px auto; padding: 22px;
    background: white; border-radius: 16px;
}
h1 { font-size: 24px; margin-top: 0; }
p { color: #586174; line-height: 1.5; }
button, input {
    width: 100%; padding: 14px; border-radius: 9px;
    font-size: 16px;
}
button {
    margin-top: 10px; border: 0; background: #1769e0;
    color: white; font-weight: bold; cursor: pointer;
}
button:disabled { opacity: .6; }
.dark { background: #263244; }
.green { background: #15803d; }
label { display: block; margin: 16px 0 8px; font-weight: bold; }
input { border: 1px solid #cbd5e1; background: white; }
.camera {
    display: none; position: relative; width: 100%;
    margin-top: 14px; overflow: hidden;
    background: #111; border-radius: 12px;
}
.camera video {
    display: block; width: 100%; height: auto;
    aspect-ratio: 3 / 4; object-fit: contain;
    background: #111;
}
.close {
    position: absolute; right: 8px; top: 8px; z-index: 3;
    width: 42px; height: 42px; padding: 0; margin: 0;
    border-radius: 50%; background: #111c; color: white;
    font-size: 27px;
}
.overlay {
    position: absolute; inset: 0; pointer-events: none;
    display: flex; align-items: center; justify-content: center;
}
.frame {
    width: 92%; height: 27%; border: 3px solid #22e477;
    border-radius: 9px; box-shadow: 0 0 0 999px #0003;
    display: flex; align-items: end; justify-content: center;
}
.frame span {
    background: #10251b; color: white; padding: 6px 8px;
    font-size: 12px; border-radius: 5px;
    transform: translateY(25px);
}
.result { background: #eaf3ff; padding: 14px; border-radius: 12px; margin-top: 20px; }
.status { white-space: pre-line; }
.small { font-size: 13px; }
hr { border: 0; border-top: 1px solid #e2e8f0; margin: 22px 0; }
</style>
</head>
<body>
<main>
<h1>Leitor de Número de Série</h1>
<p>Enquadre a etiqueta na moldura verde para ler o SN.</p>

<button type="button" id="abrir" class="dark">Abrir câmera</button>

<div class="camera" id="camera">
    <video id="video" autoplay playsinline muted></video>
    <div class="overlay">
        <div class="frame"><span>POSICIONE O SN AQUI</span></div>
    </div>
    <button type="button" id="fechar" class="close" aria-label="Fechar câmera">×</button>
</div>

<button type="button" id="capturar" class="green" style="display:none">
    Tirar foto e ler SN
</button>
<p id="status" class="status" aria-live="polite"></p>

<hr>
<p><b>Ou escolha uma foto da galeria</b></p>
<form method="POST" enctype="multipart/form-data">
    <label for="foto">Foto da etiqueta</label>
    <input id="foto" type="file" name="foto" accept="image/*" required>
    <button type="submit">Ler foto selecionada</button>
</form>

{% if resultado is not none %}
<div class="result">
    <label for="sn">SN reconhecido — confira antes de copiar</label>
    <input id="sn" value="{{ resultado }}" autocomplete="off">
    <button type="button" onclick="copiarSN()">Copiar SN</button>
    <p id="aviso" aria-live="polite"></p>
    {% if not resultado %}
    <p>Não encontrei o SN. Tente uma foto mais próxima, nítida e sem reflexo.</p>
    {% endif %}
</div>
{% endif %}
<p class="small">Confira o número antes de utilizá-lo.</p>
</main>

<script>
const video = document.getElementById("video");
const camera = document.getElementById("camera");
const abrir = document.getElementById("abrir");
const capturar = document.getElementById("capturar");
const fechar = document.getElementById("fechar");
const statusEl = document.getElementById("status");
let stream = null;
let ocupado = false;

function pararCamera() {
    if (stream) {
        stream.getTracks().forEach(track => track.stop());
        stream = null;
    }
    video.srcObject = null;
    camera.style.display = "none";
    capturar.style.display = "none";
    abrir.style.display = "block";
    ocupado = false;
    capturar.disabled = false;
}

abrir.addEventListener("click", async () => {
    abrir.disabled = true;
    statusEl.textContent = "Abrindo câmera...";

    try {
        if (!navigator.mediaDevices?.getUserMedia) {
            throw new Error("Câmera não disponível neste navegador.");
        }

        stream = await navigator.mediaDevices.getUserMedia({
            audio: false,
            video: {
                facingMode: { ideal: "environment" },
                width: { ideal: 1280 },
                height: { ideal: 1600 }
            }
        });

        video.srcObject = stream;
        camera.style.display = "block";
        await new Promise((resolve, reject) => {
            if (video.readyState >= 1 && video.videoWidth) {
                resolve();
                return;
            }
            video.onloadedmetadata = resolve;
            video.onerror = reject;
        });
        await video.play();

        abrir.style.display = "none";
        capturar.style.display = "block";
        statusEl.textContent = "Centralize a etiqueta e toque em Tirar foto e ler SN.";
    } catch (e) {
        pararCamera();
        statusEl.textContent = "Não consegui abrir a câmera. Autorize o acesso e tente novamente.";
    } finally {
        abrir.disabled = false;
    }
});

fechar.addEventListener("click", () => {
    pararCamera();
    statusEl.textContent = "Câmera fechada.";
});

capturar.addEventListener("click", async () => {
    if (ocupado) return;

    if (!video.videoWidth || !video.videoHeight || video.readyState < 2) {
        statusEl.textContent = "A imagem ainda está carregando. Aguarde um instante.";
        return;
    }

    ocupado = true;
    capturar.disabled = true;
    statusEl.textContent = "Capturando foto...";

    try {
        const canvas = document.createElement("canvas");
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const contexto = canvas.getContext("2d");
        contexto.drawImage(video, 0, 0, canvas.width, canvas.height);

        const blob = await new Promise(resolve =>
            canvas.toBlob(resolve, "image/jpeg", 0.92)
        );

        if (!blob) throw new Error("Falha ao criar a foto.");

        statusEl.textContent = "Foto capturada! Enviando para leitura...";

        // Envio normal do navegador: o servidor retorna a página com o resultado.
        const form = document.createElement("form");
        form.method = "POST";
        form.action = "/";
        form.enctype = "multipart/form-data";
        form.style.display = "none";

        const campo = document.createElement("input");
        campo.type = "file";
        campo.name = "foto";

        const transferencia = new DataTransfer();
        transferencia.items.add(new File([blob], "captura.jpg", {
            type: "image/jpeg"
        }));
        campo.files = transferencia.files;
        form.appendChild(campo);
        document.body.appendChild(form);

        pararCamera();
        statusEl.textContent = "Lendo SN... aguarde.";
        form.submit();
    } catch (e) {
        statusEl.textContent = "Não consegui capturar a foto. Tente novamente.";
        ocupado = false;
        capturar.disabled = false;
    }
});

async function copiarSN() {
    const campo = document.getElementById("sn");
    const aviso = document.getElementById("aviso");
    if (!campo || !campo.value.trim()) {
        if (aviso) aviso.textContent = "Nenhum SN para copiar.";
        return;
    }
    try {
        await navigator.clipboard.writeText(campo.value.trim());
        aviso.textContent = "SN copiado!";
    } catch (e) {
        campo.select();
        const ok = document.execCommand("copy");
        aviso.textContent = ok ? "SN copiado!" : "Selecione e copie manualmente.";
    }
}

window.addEventListener("pagehide", pararCamera);
</script>
</body>
</html>
"""


def preparar_imagem(imagem):
    imagem = ImageOps.exif_transpose(imagem).convert("RGB")
    imagem.thumbnail((1600, 1600))
    return imagem


def localizar_sn(textos):
    rotulo = re.compile(
        r"(?:S\s*/\s*N|S\.?\s*N\.?|SERIAL\s*(?:NUMBER|NO\.?|NUMERO|N[ÚU]MERO)?)",
        re.IGNORECASE
    )

    for texto in textos:
        linhas = [linha.strip() for linha in texto.splitlines() if linha.strip()]
        for i, linha in enumerate(linhas):
            marca = rotulo.search(linha)
            if not marca:
                continue

            trecho = linha[marca.end():]
            candidatos = re.findall(
                r"[A-Z0-9][A-Z0-9-]{7,19}", trecho, re.IGNORECASE
            )

            if not candidatos and i + 1 < len(linhas):
                candidatos = re.findall(
                    r"[A-Z0-9][A-Z0-9-]{7,19}",
                    linhas[i + 1],
                    re.IGNORECASE
                )

            for candidato in candidatos:
                candidato = candidato.upper().strip("-")
                if len(candidato) >= 8 and any(c.isdigit() for c in candidato):
                    return candidato

    return ""


def reconhecer_sn(imagem):
    cinza = ImageOps.grayscale(imagem)
    cinza = ImageEnhance.Contrast(cinza).enhance(2.0)
    cinza = cinza.filter(ImageFilter.SHARPEN)

    ampliada = cinza.resize(
        (cinza.width * 2, cinza.height * 2),
        Image.Resampling.LANCZOS
    )
    preto_branco = ampliada.point(lambda p: 255 if p > 155 else 0)

    textos = []
    for variante in (cinza, ampliada, preto_branco):
        for psm in (6, 11):
            try:
                texto = pytesseract.image_to_string(
                    variante,
                    config=f"--oem 3 --psm {psm}",
                    timeout=8
                )
                textos.append(texto)
            except TesseractError:
                continue

        resultado = localizar_sn(textos)
        if resultado:
            return resultado

    return ""


@app.route("/", methods=["GET", "POST"])
def inicio():
    resultado = None

    if request.method == "POST":
        arquivo = request.files.get("foto")
        if arquivo and arquivo.filename:
            try:
                imagem = Image.open(io.BytesIO(arquivo.read()))
                imagem = preparar_imagem(imagem)
                resultado = reconhecer_sn(imagem)
            except Exception:
                resultado = ""

    return render_template_string(HTML, resultado=resultado)


@app.errorhandler(413)
def arquivo_grande(_erro):
    return "A foto ultrapassou 8 MB. Tente uma foto menor.", 413


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
