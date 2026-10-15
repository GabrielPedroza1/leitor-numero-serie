
import os
import re
import base64

from flask import Flask, request, jsonify, render_template_string
from openai import OpenAI, AuthenticationError, RateLimitError, APIConnectionError

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

    <input
        id="sn"
        type="text"
        placeholder="Número de série"
        autocomplete="off"
        aria-label="Número de série"
    >

    <button id="copy">📋 Copiar número</button>

    <p id="status">Iniciando câmera...</p>

    <p class="footer">
        Confira o número antes de utilizá-lo.
    </p>

</div>

<canvas id="canvas" hidden></canvas>

<script>
const video = document.getElementById("video");
const canvas = document.getElementById("canvas");
const captureButton = document.getElementById("capture");
const startButton = document.getElementById("startCamera");
const copyButton = document.getElementById("copy");
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
        if (!navigator.mediaDevices ||
            !navigator.mediaDevices.getUserMedia) {
            throw new Error("Câmera indisponível neste navegador.");
        }

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
            "Não foi possível abrir a câmera. Verifique as permissões do navegador.";
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
    startButton.classList.add("hidden");
    snInput.value = "";
    statusText.textContent = "Capturando foto...";

    try {
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
            canvas.toBlob(resolve, "image/jpeg", 0.95);
        });

        if (!blob) {
            throw new Error("Não foi possível capturar a foto.");
        }

        // Desliga a câmera assim que a foto estiver capturada.
        // A imagem continua no canvas e pode ser enviada normalmente.
        desligarCamera();

        statusText.textContent = "Foto capturada. A IA está lendo...";

        const formData = new FormData();
        formData.append("foto", blob, "etiqueta.jpg");

        const response = await fetch("/", {
            method: "POST",
            body: formData
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(
                data.erro || "Não foi possível processar a foto."
            );
        }

        snInput.value = data.sn || "";

        statusText.textContent = data.sn
            ? "Leitura concluída! Confira o número antes de copiar."
            : "A IA não conseguiu identificar o número. Ligue a câmera e tente novamente.";

    } catch (error) {
        console.error("Erro na leitura:", error);
        statusText.textContent =
            error.message || "Falha ao processar a foto.";
    } finally {
        processando = false;
        captureButton.disabled = false;
        startButton.classList.remove("hidden");
    }
});

startButton.addEventListener("click", iniciarCamera);

copyButton.addEventListener("click", async function () {
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

        try {
            const copiou = document.execCommand("copy");
            statusText.textContent = copiou
                ? "Número copiado!"
                : "Selecione o número e copie manualmente.";
        } catch (erro) {
            statusText.textContent =
                "Selecione o número e copie manualmente.";
        }
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

    api_key = os.environ.get("OPENAI_API_KEY")

    if not api_key:
        return jsonify({
            "erro": "A chave OPENAI_API_KEY não está configurada no Railway."
        }), 500

    try:
        imagem_base64 = base64.b64encode(
            imagem_bytes
        ).decode("utf-8")

        data_url = "data:image/jpeg;base64," + imagem_base64

        cliente = OpenAI(api_key=api_key)

        resposta = cliente.responses.create(
            model="gpt-4.1-mini",
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Leia o número de série impresso na etiqueta, "
                                "preferencialmente próximo de SN ou S/N. Não "
                                "leia o código de barras. Preserve exatamente "
                                "as letras e os números. Diferencie 3 de 9, "
                                "0 de O, 1 de I e 5 de S. Não invente "
                                "caracteres. Responda somente com o número "
                                "de série. Se não conseguir ler com segurança, "
                                "responda UNKNOWN."
                            )
                        },
                        {
                            "type": "input_image",
                            "image_url": data_url,
                            "detail": "high"
                        }
                    ]
                }
            ],
            max_output_tokens=50
        )

        texto = (resposta.output_text or "").strip().upper()

        if not texto or "UNKNOWN" in texto:
            return jsonify({"sn": ""})

        numero = re.sub(r"[^A-Z0-9]", "", texto)

        if len(numero) < 5:
            return jsonify({"sn": ""})

        return jsonify({"sn": numero})

    except AuthenticationError:
        print("OpenAI: chave da API inválida ou não autorizada.", flush=True)
        return jsonify({
            "erro": "A chave da API da OpenAI é inválida. Confira OPENAI_API_KEY no Railway."
        }), 502

    except RateLimitError:
        print("OpenAI: limite de uso ou créditos indisponíveis.", flush=True)
        return jsonify({
            "erro": "A API atingiu um limite de uso ou está sem créditos. Confira o faturamento da OpenAI."
        }), 502

    except APIConnectionError:
        print("OpenAI: falha de conexão com a API.", flush=True)
        return jsonify({
            "erro": "Não foi possível conectar à OpenAI. Tente novamente."
        }), 502

    except Exception as erro:
        print("Erro na leitura com IA:", repr(erro), flush=True)
        return jsonify({
            "erro": "A IA falhou ao processar a foto. Consulte os logs do Railway para identificar a causa."
        }), 502


if __name__ == "__main__":
    porta = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=porta)
