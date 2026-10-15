import os
import re

from flask import Flask, request, render_template_string
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import pytesseract


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB

# No Windows usa o Tesseract instalado no computador.
# No Render/Linux usa o executável instalado pelo Dockerfile.
if os.name == "nt":
    pytesseract.pytesseract.tesseract_cmd = (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    )


PAGINA = """
<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#1769aa">
<title>Leitor de Número de Série</title>
<style>
* {
    box-sizing: border-box;
}
body {
    font-family: Arial, sans-serif;
    max-width: 540px;
    margin: 24px auto;
    padding: 16px;
    background: #f2f4f7;
    color: #202124;
}
main {
    background: white;
    padding: 22px;
    border-radius: 16px;
    box-shadow: 0 3px 14px #0000000b;
}
h2 {
    margin-top: 4px;
}
input[type=file] {
    display: block;
    width: 100%;
    margin: 18px 0;
    padding: 10px 0;
}
button {
    width: 100%;
    padding: 15px;
    margin: 10px 0;
    background: #1769aa;
    color: white;
    border: 0;
    border-radius: 8px;
    font-size: 16px;
    cursor: pointer;
}
button:disabled {
    opacity: 0.65;
}
.resultado {
    background: #eaf4ff;
    padding: 14px;
    margin: 10px 0;
    border-radius: 8px;
    overflow-wrap: anywhere;
}
.resultado input {
    margin-right: 10px;
    transform: scale(1.2);
}
.erro {
    background: #fff0f0;
    padding: 12px;
    border-radius: 8px;
    color: #8b1e1e;
}
.ajuda {
    color: #555;
    font-size: 14px;
    line-height: 1.5;
}
</style>
</head>
<body>
<main>
<h2>Leitor de Número de Série</h2>
<p>Envie uma foto da etiqueta do equipamento.</p>

<form method="post" enctype="multipart/form-data" id="formulario">
<input type="file" name="foto" accept="image/*"
       capture="environment" required>
<button type="submit" id="botao">Ler número de série</button>
<p class="ajuda" id="aguarde" hidden>
Analisando a etiqueta. Aguarde...
</p>
</form>

{% if erro %}
<p class="erro">{{ erro }}</p>
{% endif %}

{% if candidatos %}
<h3>Confira o número identificado</h3>
<p class="ajuda">
Selecione o número correto antes de copiar.
Os primeiros resultados são os que parecem mais próximos
da indicação S/N ou Serial.
</p>

<form id="form-copiar" onsubmit="return false;">
{% for c in candidatos %}
<div class="resultado">
<label>
<input type="radio" name="serie" value="{{ c.valor }}"
{% if loop.first %}checked{% endif %}>
<strong>{{ c.valor }}</strong>
{% if c.prioritario %}
<span> — provável número de série</span>
{% endif %}
</label>
</div>
{% endfor %}
</form>

<button type="button" onclick="copiar()">Copiar selecionado</button>
<p id="status" role="status"></p>
{% endif %}

<script>
document.getElementById("formulario").addEventListener("submit", function() {
    document.getElementById("botao").disabled = true;
    document.getElementById("botao").textContent = "Lendo etiqueta...";
    document.getElementById("aguarde").hidden = false;
});

async function copiar() {
    const item = document.querySelector('input[name="serie"]:checked');
    const status = document.getElementById("status");

    if (!item) {
        status.textContent = "Selecione um número primeiro.";
        return;
    }

    try {
        await navigator.clipboard.writeText(item.value);
        status.textContent = "Número copiado: " + item.value;
    } catch (e) {
        const campo = document.createElement("textarea");
        campo.value = item.value;
        campo.style.position = "fixed";
        campo.style.opacity = "0";
        document.body.appendChild(campo);
        campo.select();

        const sucesso = document.execCommand("copy");
        campo.remove();

        status.textContent = sucesso
            ? "Número copiado: " + item.value
            : "Não foi possível copiar. Anote o número exibido.";
    }
}
</script>
</main>
</body>
</html>
"""


# Termos que podem aparecer na etiqueta, mas não são números de série.
PALAVRAS_IGNORAR = {
    "SERIAL", "NUMBER", "NUMERO", "SERIE", "MODEL", "MODELO",
    "PAGSEGURO", "PAGBANK", "INPUT", "OUTPUT", "VOLTS",
    "AMPERES", "MADE", "BRASIL", "CHINA", "SAMSUNG"
}

PADRAO_TOKEN = re.compile(
    r"(?<![A-Z0-9])[A-Z0-9][A-Z0-9-]{5,23}(?![A-Z0-9])"
)

PADRAO_ROTULO = re.compile(
    r"\b(?:S\s*/\s*N|S\.?\s*N\.?|SERIAL(?:\s+NUMBER)?|"
    r"N[ÚU]MERO\s+(?:DE\s+)?S[ÉE]RIE)\b",
    re.IGNORECASE
)


def preparar_imagem(imagem):
    """Gera versões da imagem para melhorar a leitura do OCR."""
    imagem = ImageOps.exif_transpose(imagem)
    imagem = ImageOps.grayscale(imagem)

    # Limita o tamanho para evitar consumo excessivo de memória.
    maior = max(imagem.size)
    if maior > 2200:
        fator = 2200 / maior
        novo_tamanho = (
            max(1, int(imagem.width * fator)),
            max(1, int(imagem.height * fator))
        )
        imagem = imagem.resize(novo_tamanho, Image.Resampling.LANCZOS)

    ampliada = imagem.resize(
        (imagem.width * 2, imagem.height * 2),
        Image.Resampling.LANCZOS
    )

    contraste = ImageOps.autocontrast(ampliada)
    contraste = ImageEnhance.Contrast(contraste).enhance(1.6)
    nitida = contraste.filter(ImageFilter.SHARPEN)

    # Uma versão binária pode ajudar quando a etiqueta está clara.
    limiar = contraste.point(lambda p: 255 if p > 155 else 0)

    return [ampliada, nitida, limiar]


def ler_textos(imagem):
    """Executa OCR em diferentes versões e configurações."""
    textos = []

    for versao in preparar_imagem(imagem):
        for psm in (6, 11):
            try:
                texto = pytesseract.image_to_string(
                    versao,
                    config=f"--oem 3 --psm {psm}"
                )
                if texto.strip():
                    textos.append(texto)
            except pytesseract.TesseractError:
                app.logger.exception("Falha em uma tentativa de OCR")

    return textos


def normalizar_token(token):
    token = token.upper().strip()
    token = token.strip(".,:;|()[]{}")
    return token.replace(" ", "")


def localizar_series(textos):
    """
    Dá prioridade aos códigos que aparecem perto de S/N ou Serial.
    Também mantém outros candidatos para conferência manual.
    """
    pontuacoes = {}

    for texto in textos:
        linhas = texto.upper().splitlines()

        for i, linha in enumerate(linhas):
            contexto = " ".join(linhas[max(0, i - 1):i + 2])
            tem_rotulo = bool(PADRAO_ROTULO.search(linha))
            rotulo_proximo = bool(PADRAO_ROTULO.search(contexto))

            # Se a linha contém S/N, prioriza o código dessa linha
            # e da linha seguinte.
            if tem_rotulo:
                trecho = " ".join(linhas[i:min(i + 2, len(linhas))])
            else:
                trecho = linha

            for token in PADRAO_TOKEN.findall(trecho):
                token = normalizar_token(token)

                if token in PALAVRAS_IGNORAR:
                    continue

                # Evita palavras comuns e códigos muito curtos.
                if len(token) < 7 or len(token) > 24:
                    continue

                if not any(ch.isdigit() for ch in token):
                    continue

                pontuacao = 0

                if rotulo_proximo:
                    pontuacao += 10
                if tem_rotulo:
                    pontuacao += 5
                if token.isdigit() and 8 <= len(token) <= 16:
                    pontuacao += 2
                if "-" in token:
                    pontuacao += 1

                # Repetições em diferentes tentativas reforçam o candidato.
                pontuacoes[token] = pontuacoes.get(token, 0) + pontuacao + 1

    ordenados = sorted(
        pontuacoes.items(),
        key=lambda item: item[1],
        reverse=True
    )

    candidatos = []
    for valor, pontos in ordenados[:15]:
        candidatos.append({
            "valor": valor,
            "prioritario": pontos >= 10
        })

    return candidatos


@app.errorhandler(413)
def arquivo_grande(_erro):
    return render_template_string(
        PAGINA,
        candidatos=[],
        erro="A foto é muito grande. Envie uma imagem de até 10 MB."
    ), 413


@app.route("/", methods=["GET", "POST"])
def inicio():
    candidatos = []
    erro = None

    if request.method == "POST":
        foto = request.files.get("foto")

        if not foto or not foto.filename:
            erro = "Selecione uma foto."
        else:
            try:
                imagem = Image.open(foto.stream)
                imagem.load()

                if imagem.width < 50 or imagem.height < 50:
                    erro = "A imagem é pequena demais. Tire outra foto."
                else:
                    textos = ler_textos(imagem)
                    candidatos = localizar_series(textos)

                    if not candidatos:
                        erro = (
                            "Não encontrei números candidatos. "
                            "Tente aproximar a câmera da etiqueta, "
                            "melhorar a iluminação e evitar reflexos."
                        )

            except (OSError, ValueError):
                app.logger.exception("Imagem inválida")
                erro = "Não consegui abrir essa foto. Tente outra imagem."
            except Exception:
                app.logger.exception("Erro ao processar a foto")
                erro = (
                    "Ocorreu um erro ao ler a foto. "
                    "Tente novamente; se persistir, confira os logs do servidor."
                )

    return render_template_string(
        PAGINA,
        candidatos=candidatos,
        erro=erro
    )


if __name__ == "__main__":
    app.run(debug=False, port=5000)
