
import os
import re
import base64

from flask import Flask, request, jsonify, render_template_string
from openai import OpenAI

app = Flask(__name__)

HTML = r"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Leitor de Número de Série</title>

<style>
* {
    box-sizing: border-box;
}

body {
    margin: 0;
    padding: 20px;
    background: #101418;
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
    margin: 8px 0 12px;
}

.hint {
    color: #b8c0c8;
    font-size: 14px;
    line-height: 1.5;
}

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
    left: 5%;
    top: 35%;
    width: 90%;
    height: 30%;
    border: 3px solid #22c55e;
    border-radius: 6px;
    box-shadow: 0 0 0 9999px rgba(0, 0, 0, .15);
    pointer-events: none;
}

button {
    width: 100%;
    min-height: 56px;
    padding: 15px;
    margin-top: 12px;
    border: 0;
    border-radius: 9px;
    background: #1767df;
    color: #fff;
    font-size: 17px;
    font-weight: bold;
    cursor: pointer;
}

button:active {
    background: #0f4eb5;
}

button:disabled {
    opacity: .55;
    cursor: wait;
}

#sn {
    display: block;
    width: 100%;
    margin-top: 16px;
    padding: 15px;
    border: 2px solid #1767df;
    border-radius: 9px;
    background: #20272e;
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
    margin: 12px 4px 5px;
    color: #d6d6d6;
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
        Posicione o S/N e o número de série dentro da moldura verde.
    </p>

    <div class="camera">
        <video id="video" autoplay playsinline muted></video>
        <div class="frame"></div>
    </div>

    <button id="capture">Ler número de série</button>

    <input
        id="sn"
        type="text"
        placeholder="Número de série"
        autocomplete="off"
        aria-label="Número de série"
    >

    <button id="copy">Copiar número</button>

    <p id="status">Iniciando câmera...</p>

    <p class="footer">
        Confira o número reconhecido antes de copiar.
    </p>

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
            "Câmera pronta. Enquadre o S/N e o número completo.";

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
    statusText.textContent = "A IA está procurando o S/N...";
    snInput.value = "";

    try {
        // Recorta a região interna da moldura verde.
        const largura = Math.round(video.videoWidth * 0.90);
        const altura = Math.round(video.videoHeight * 0.30);
        const x = Math.round(video.videoWidth * 0.05);
        const y = Math.round(video.videoHeight * 0.35);

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
            throw new Error("Não foi possível capturar a imagem.");
        }

        const formData = new FormData();
        formData.append("foto", blob, "etiqueta.jpg");

        const response = await fetch("/", {
            method: "POST",
            body: formData
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(
                data.erro || "Falha ao processar a imagem."
            );
        }

        snInput.value = data.sn || "";

        statusText.textContent = data.sn
            ? "Número reconhecido! Confira antes de copiar."
            : "S/N não identificado. Aproxime a câmera e tente novamente.";

    } catch (error) {
        statusText.textContent =
            error.message || "Erro ao processar a imagem.";

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


def extrair_numero_serie(texto):
    """
    Procura o número depois de rótulos como:
    S/N:, SN:, S.N., Serial Number e Número de série.
    """

    texto = texto.strip().upper()

    # Remove cercas de código, caso a IA as retorne.
    texto = re.sub(r"```.*?\n|```", "", texto, flags=re.DOTALL)

    padrao_rotulo = (
        r"(?:S\s*[/\\]\s*N|S\.?\s*N\.?|"
        r"SERIAL\s*(?:NUMBER|NO\.?|#)?|"
        r"N[ÚU]MERO\s+DE\s*S[ÉE]RIE)"
        r"\s*[:：#=\-]?\s*"
        r"([A-Z0-9][A-Z0-9\-]*)"
    )

    resultado = re.search(padrao_rotulo, texto, re.IGNORECASE)

    if resultado:
        numero = resultado.group(1)
    else:
        # A IA pode retornar somente o número, sem o rótulo.
        numero = texto.strip()

    # Mantém apenas letras e números, removendo espaços e pontuação.
    numero = re.sub(r"[^A-Z0-9]", "", numero)

    # Evita aceitar respostas vazias ou muito curtas.
    if len(numero) < 5:
        return None

    # Não aceita respostas genéricas da IA.
    if numero in {
        "UNKNOWN",
        "DESCONHECIDO",
        "NAOIDENTIFICADO",
        "NAOFOIPOSSIVEL"
    }:
        return None

    return numero


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_template_string(HTML)

    if "foto" not in request.files:
        return jsonify({
            "erro": "Nenhuma foto foi recebida."
        }), 400

    imagem_bytes = request.files["foto"].read()

    if not imagem_bytes:
        return jsonify({
            "erro": "A foto está vazia."
        }), 400

    api_key = os.environ.get("OPENAI_API_KEY")

    if not api_key:
        return jsonify({
            "erro": "OPENAI_API_KEY não está configurada no Railway."
        }), 500

    imagem_base64 = base64.b64encode(
        imagem_bytes
    ).decode("utf-8")

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
                                "Você é um leitor especializado em números "
                                "de série de equipamentos. Examine a imagem "
                                "com atenção. Procure primeiro os rótulos "
                                "S/N, S/N:, SN, SN:, S.N., Serial Number, "
                                "Serial No. ou Número de série. "
                                "Leia o valor impresso associado a esse "
                                "rótulo. Retorne somente o valor do número "
                                "de série, sem o rótulo, sem espaços e sem "
                                "explicações. Preserve todas as letras, "
                                "todos os números e os hífens que estiverem "
                                "visíveis. Não confunda o número de série "
                                "com modelo, IMEI, MAC, código de barras "
                                "ou outros códigos da etiqueta. "
                                "Observe cuidadosamente diferenças entre "
                                "0 e O, 1 e I, 5 e S, 8 e B e 3 e 9. "
                                "Não invente nem complete caracteres "
                                "que não estejam legíveis. "
                                "Se o rótulo ou seu valor não puder ser "
                                "identificado com segurança, responda "
                                "exatamente UNKNOWN."
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
            max_output_tokens=80
        )

        texto = (resposta.output_text or "").strip()

        if not texto or "UNKNOWN" in texto.upper():
            return jsonify({"sn": ""})

        numero = extrair_numero_serie(texto)

        if not numero:
            return jsonify({"sn": ""})

        return jsonify({"sn": numero})

    except Exception as erro:
        print(
            "Erro na leitura com IA:",
            repr(erro),
            flush=True
        )

        return jsonify({
            "erro": (
                "Falha na leitura com IA. Confira os logs do Railway "
                "e os créditos disponíveis na API OpenAI."
            )
        }), 502


if __name__ == "__main__":
    porta = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=porta)
