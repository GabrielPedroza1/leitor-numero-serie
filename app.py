
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
    margin: 0; padding: 16px; background: #f1f5f9;
    font-family: Arial, sans-serif; color: #172033;
}
main {
    max-width: 520px; margin: 12px auto; padding: 22px;
    background: white; border-radius: 16px;
}
h1 { font-size: 24px; }
p { color: #586174; line-height: 1.5; }
button, input, select {
    width: 100%; padding: 14px; border-radius: 9px;
    font-size: 16px;
}
button {
    margin-top: 10px; border: 0; background: #1769e0;
    color: white; font-weight: bold; cursor: pointer;
}
button.dark { background: #263244; }
button.green { background: #15803d; }
button:disabled { opacity: .55; }
label { display: block; margin: 18px 0 8px; font-weight: bold; }
input, select { border: 1px solid #cbd5e1; background: white; }
.camera {
    display: none; position: relative; width: 100%;
    overflow: hidden; background: #101010;
    border-radius: 12px; margin-top: 12px;
}
.camera video {
    display: block; width: 100%; height: auto;
    aspect-ratio: 3 / 4; object-fit: cover;
}
.overlay {
    position: absolute; inset: 0; pointer-events: none;
    display: flex; align-items: center; justify-content: center;
}
.frame {
    width: 90%; height: 28%;
    border: 3px solid #22e477; border-radius: 10px;
    box-shadow: 0 0 0 999px #0006;
    display: flex; align-items: end; justify-content: center;
}
.frame span {
    background: #10251b; color: white; padding: 6px 9px;
    font-size: 12px; border-radius: 5px;
    transform: translateY(28px);
}
#status { white-space: pre-line; }
.result { background: #eaf3ff; padding: 14px; border-radius: 12px; margin-top: 20px; }
.small { font-size: 13px; }
</style>
</head>
<body>
<main>
<h1>Leitor de Número de Série</h1>
<p>Abra a câmera e coloque a etiqueta dentro da moldura verde.</p>

<button type="button" id="abrir" class="dark">Abrir câmera</button>

<div class="camera" id="camera">
    <video id="video" autoplay playsinline muted></video>
    <div class="overlay">
        <div class="frame">
            <span>ENQUADRE A ETIQUETA / SN</span>
        </div>
    </div>
</div>

<button type="button" id="capturar" class="green" style="display:none">
    Tirar foto e ler SN
</button>
<button type="button" id="fechar" class="dark" style="display:none">
    Fechar câmera
</button>

<p id="status" aria-live="polite"></p>

<hr style="border:0;border-top:1px solid #e2e8f0;margin:22px 0">
<p><b>Ou envie uma foto da galeria</b></p>
<form id="formulario" method="POST" enctype="multipart/form-data">
    <input type="hidden" name="origem" value="galeria">
    <label for="foto">Escolher foto</label>
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
    <p>Não consegui localizar o SN com segurança. Tente enquadrar a etiqueta mais de perto.</p>
    {% endif %}
</div>
{% endif %}
<p class="small">A moldura ajuda no enquadramento. Confira o código antes de utilizar.</p>
</main>

<script>
const video = document.getElementById("video");
const camera = document.getElementById("camera");
const abrir = document.getElementById("abrir");
const capturar = document.getElementById("capturar");
const fechar = document.getElementById("fechar");
const statusEl = document.getElementById("status");
let stream = null;

function pararCamera() {
    if (stream) {
        stream.getTracks().forEach(track => track.stop());
        stream = null;
    }
    video.srcObject = null;
    camera.style.display = "none";
    capturar.style.display = "none";
    fechar.style.display = "none";
    abrir.style.display = "block";
}

abrir.addEventListener("click", async () => {
    try {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            statusEl.textContent = "Câmera indisponível neste navegador. Use HTTPS ou envie uma foto da galeria.";
            return;
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
        await video.play();
        camera.style.display = "block";
        capturar.style.display = "block";
        fechar.style.display = "block";
        abrir.style.display = "none";
        statusEl.textContent = "Posicione o SN dentro da moldura verde.";
    } catch (e) {
        statusEl.textContent = "Não consegui abrir a câmera. Autorize o acesso ou envie uma foto da galeria.";
        pararCamera();
    }
});

fechar.addEventListener("click", () => {
    pararCamera();
    statusEl.textContent = "Câmera fechada.";
});

capturar.addEventListener("click", async () => {
    if (!video.videoWidth || !video.videoHeight) {
        statusEl.textContent = "A câmera ainda está iniciando. Tente novamente.";
        return;
    }

    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);

    canvas.toBlob(async blob => {
        if (!blob) {
            statusEl.textContent = "Não foi possível capturar a foto.";
            return;
        }

        const dados = new FormData();
        dados.append("foto", blob, "captura.jpg");
        dados.append("origem", "camera");

        capturar.disabled = true;
        statusEl.textContent = "Lendo a etiqueta... aguarde.";

        try {
            const resposta = await fetch("/", { method: "POST", body: dados });
            const html = await resposta.text();
            document.open();
            document.write(html);
            document.close();
        } catch (e) {
            statusEl.textContent = "Erro ao enviar a foto. Tente novamente.";
            capturar.disabled = false;
        }
    }, "image/jpeg", 0.92);
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
        aviso.textContent = ok ? "SN copiado!" : "Selecione o código e copie manualmente.";
    }
}

window.addEventListener("pagehide", () => {
    if (stream) stream.getTracks().forEach(track => track.stop());
});
</script>
</body>
</html>
"""


def preparar_imagem(imagem):
    imagem = ImageOps.exif_transpose(imagem).convert("RGB")
    imagem.thumbnail((1600, 1600))
    return imagem


def preparar_variantes(imagem):
    cinza = ImageOps.grayscale(imagem)
    cinza = ImageEnhance.Contrast(cinza).enhance(2.0)
    cinza = cinza.filter(ImageFilter.SHARPEN)

    ampliada = cinza.resize(
        (cinza.width * 2, cinza.height * 2),
        Image.Resampling.LANCZOS
    )
    preto_branco = ampliada.point(lambda p: 255 if p > 155 else 0)

    return [cinza, ampliada, preto_branco]


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

            # Procura primeiro depois do rótulo na mesma linha.
            trecho = linha[marca.end():]
            candidatos = re.findall(
                r"[A-Z0-9][A-Z0-9-]{7,19}",
                trecho,
                re.IGNORECASE
            )

            # Se o rótulo estiver sozinho, tenta a próxima linha.
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
    textos = []
    for variante in preparar_variantes(imagem):
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
    return "A foto ultrapassou o limite de 8 MB. Tente uma foto menor.", 413


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))




if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
