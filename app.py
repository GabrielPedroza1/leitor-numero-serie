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
    color: #ffffff;
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
    margin: 8px 0 12px;
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
    background: #05080c;
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
    border: 3px solid #22c55e;
    border-radius: 8px;
    pointer-events: none;
}

button {
    width: 100%;
    min-height: 56px;
    margin-top: 14px;
    padding: 15px;
    border: none;
    border-radius: 11px;
    background: #1767df;
    color: #ffffff;
    font-size: 17px;
    font-weight: bold;
    cursor: pointer;
    transition: background 0.2s;
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
    margin-top: 18px;
    padding: 17px 12px;
    border: 2px solid #1767df;
    border-radius: 11px;
    background: #202b3a;
    color: #ffffff;
    font-size: 22px;
    text-align: center;
    outline: none;
}

#sn:focus {
    border-color: #60a5fa;
}

#status {
    min-height: 24px;
    margin: 15px 4px 5px;
    color: #d4deeb;
    font-size: 14px;
    line-height: 1.5;
    overflow-wrap: anywhere;
}

.footer {
    color: #91a1b5;
    font-size: 12px;
    margin-top: 18px;
}
</style>
</head>
<body>
<div class="container">
    <h1>Leitor de Número de Série</h1>
    <p class="hint">
        Posicione o número de série dentro da moldura verde.
    </p>

    <div class="camera">
        <video id="video" autoplay playsinline muted></video>
        <div class="frame"></div>
    </div>

    <button id="capture">📷 Tirar foto e ler com IA</button>

    <input
        id="sn"
        type="text"
        placeholder="Número de série"
        autocomplete="off"
        aria-label="Número de série"
    >

    <button id="copy">📋 Copiar número</button>

    <p id="status">Iniciando câmera...</p>
    <p class="footer">Confira o número antes de utilizá-lo.</p>
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
                height: { ideal: 2160 }
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
    statusText.textContent = "Enviando a foto para a IA...";
    snInput.value = "";

    try {
        // Recorta a região correspondente à moldura verde.
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

        const blob = await new Promise(resolve =>
            canvas.toBlob(resolve, "image/jpeg", 0.98)
        );

        if (!blob) {
            throw new Error("Não foi possível capturar a foto.");
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

        if (data.sn) {
            statusText.textContent =
                "Leitura concluída! Confira o número antes de copiar.";
        } else {
            statusText.textContent =
                "Não consegui confirmar o número. Aproxime a câmera e tente novamente.";
        }
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
        statusText.textContent = "Número copiado com sucesso!";
    } catch (error) {
        snInput.select();
        statusText.textContent =
            "Não foi possível copiar automaticamente. Selecione o número e copie manualmente.";
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
        return jsonify({"erro": "A foto está vazia."}), 400

    api_key = os.environ.get("OPENAI_API_KEY")

    if not api_key:
        return jsonify({
            "erro": "OPENAI_API_KEY não está configurada no Railway."
        }), 500

    imagem_base64 = base64.b64encode(imagem_bytes).decode("utf-8")
    data_url = "data:image/jpeg;base64," + imagem_base64

    try:
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
                                "normalmente ao lado de SN ou S/N. Não leia o "
                                "código de barras. Preserve exatamente letras "
                                "e números visíveis. Diferencie cuidadosamente "
                                "3 de 9, 0 de O, 1 de I e 5 de S. Não invente "
                                "caracteres. Responda somente com o número "
                                "de série, sem espaços ou explicações. Se não "
                                "conseguir ler com segurança, responda UNKNOWN."
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

    except Exception as erro:
        # O detalhe fica nos logs do Railway, não exposto ao visitante.
        print("Erro na leitura com IA:", repr(erro), flush=True)

        return jsonify({
            "erro": (
                "A IA não conseguiu processar a foto. "
                "Vamos verificar os logs do Railway para descobrir o motivo."
            )
        }), 502


if __name__ == "__main__":
    porta = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=porta)
