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
            background: #101418;
            color: white;
            font-family: Arial, sans-serif;
            text-align: center;
        }
        .container {
            max-width: 600px;
            margin: auto;
        }
        h1 { font-size: 25px; }
        .camera {
            position: relative;
            width: 100%;
            overflow: hidden;
            border-radius: 12px;
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
            border: 3px solid #00ff75;
            border-radius: 6px;
            box-shadow: 0 0 0 9999px rgba(0,0,0,.15);
            pointer-events: none;
        }
        button {
            width: 100%;
            padding: 15px;
            margin-top: 12px;
            border: 0;
            border-radius: 8px;
            background: #00c853;
            color: #07130a;
            font-size: 17px;
            font-weight: bold;
            cursor: pointer;
        }
        button:disabled { opacity: .55; cursor: wait; }
        #sn {
            width: 100%;
            margin-top: 16px;
            padding: 15px;
            border: 2px solid #00c853;
            border-radius: 8px;
            background: #20272e;
            color: white;
            font-size: 22px;
            text-align: center;
        }
        #status {
            min-height: 24px;
            margin-top: 12px;
            color: #d6d6d6;
            overflow-wrap: anywhere;
        }
        .hint { color: #b8c0c8; font-size: 14px; }
    </style>
</head>
<body>
<div class="container">
    <h1>Leitor de Número de Série</h1>
    <p class="hint">Enquadre o número de série dentro do retângulo verde.</p>

    <div class="camera">
        <video id="video" autoplay playsinline muted></video>
        <div class="frame"></div>
    </div>

    <button id="capture">Fotografar e ler com IA</button>

    <input id="sn" type="text" placeholder="Número de série" autocomplete="off">

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
        statusText.textContent = "Câmera pronta. Enquadre a etiqueta.";
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
    statusText.textContent = "A IA está analisando a etiqueta...";
    snInput.value = "";

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

        const blob = await new Promise(resolve =>
            canvas.toBlob(resolve, "image/jpeg", 0.98)
        );

        if (!blob) throw new Error("Não foi possível capturar a imagem.");

        const formData = new FormData();
        formData.append("foto", blob, "etiqueta.jpg");

        const response = await fetch("/", {
            method: "POST",
            body: formData
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.erro || "Erro ao reconhecer a etiqueta.");
        }

        snInput.value = data.sn || "";
        statusText.textContent = data.sn
            ? "Leitura concluída. Confira o número antes de copiar."
            : "A IA não conseguiu confirmar o número. Tente aproximar a câmera e fotografar novamente.";
    } catch (error) {
        statusText.textContent = error.message || "Erro ao processar a imagem.";
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
        return jsonify({"erro": "Nenhuma imagem foi recebida."}), 400

    foto = request.files["foto"]
    imagem_bytes = foto.read()

    if not imagem_bytes:
        return jsonify({"erro": "A imagem está vazia."}), 400

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return jsonify({
            "erro": "A chave OPENAI_API_KEY não está configurada no Railway."
        }), 500

    imagem_base64 = base64.b64encode(imagem_bytes).decode("utf-8")
    data_url = f"data:image/jpeg;base64,{imagem_base64}"

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
                                "Você é um leitor rigoroso de etiquetas de "
                                "equipamentos eletrônicos. Leia o número de "
                                "série impresso na etiqueta, geralmente próximo "
                                "de SN, S/N ou Serial Number. Leia os caracteres "
                                "visíveis exatamente como estão impressos. "
                                "Não leia o código de barras. Não invente nem "
                                "complete caracteres por suposição. Diferencie "
                                "cuidadosamente 3 de 9, 0 de O, 1 de I e 5 de S. "
                                "Responda somente com o número de série, usando "
                                "letras maiúsculas e números, sem espaços ou "
                                "explicações. Se não conseguir identificar com "
                                "segurança, responda apenas UNKNOWN."
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

        if "UNKNOWN" in texto or not texto:
            return jsonify({"sn": ""})

        # Mantém somente letras e números.
        numero = re.sub(r"[^A-Z0-9]", "", texto)

        if not numero or len(numero) < 5:
            return jsonify({"sn": ""})

        return jsonify({"sn": numero})

    except Exception as erro:
        print("Erro na leitura com IA:", repr(erro))
        return jsonify({
            "erro": (
                "Falha na leitura com IA. Verifique os logs do Railway "
                "e se a API da OpenAI tem créditos disponíveis."
            )
        }), 502


if __name__ == "__main__":
    porta = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=porta)
