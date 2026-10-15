
import os
import re
import io
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
<title>Leitor SN</title>
<style>
body{font-family:Arial;background:#f1f5f9;margin:0;padding:20px;color:#172033}
main{max-width:520px;margin:20px auto;background:white;padding:24px;border-radius:16px}
h1{font-size:24px}
label{display:block;font-weight:bold;margin:16px 0 8px}
input,select{width:100%;padding:13px;box-sizing:border-box;border:1px solid #cbd5e1;border-radius:9px;font-size:16px}
button{width:100%;padding:14px;margin-top:12px;border:0;border-radius:9px;background:#1769e0;color:white;font-size:16px;font-weight:bold}
p{line-height:1.5;color:#586174}
</style>
</head>
<body>
<main>
<h1>Leitor de Número de Série</h1>
<p>Envie uma foto nítida da etiqueta ou da tela ligada.</p>
<form method="POST" enctype="multipart/form-data"
 onsubmit="document.getElementById('status').textContent='Lendo... aguarde.'">
<label>Modo de leitura</label>
<select name="modo">
<option value="etiqueta" {% if modo=='etiqueta' %}selected{% endif %}>Etiqueta do equipamento</option>
<option value="tela" {% if modo=='tela' %}selected{% endif %}>Máquina ligada — SN na tela</option>
</select>
<label>Foto</label>
<input type="file" name="foto" accept="image/*" capture="environment" required>
<button type="submit">Ler SN</button>
</form>
{% if resultado is not none %}
<label>SN reconhecido — confira antes de copiar</label>
<input id="sn" value="{{ resultado }}" autocomplete="off">
<button type="button" onclick="copiar()">Copiar SN</button>
<p id="aviso"></p>
{% if not resultado %}
<p>Não encontrei um SN com segurança. Tente uma foto mais próxima e nítida.</p>
{% endif %}
{% endif %}
<p id="status"></p>
</main>
<script>
async function copiar(){
 const campo=document.getElementById('sn');
 const aviso=document.getElementById('aviso');
 if(!campo.value.trim()){aviso.textContent='Nenhum SN encontrado.';return;}
 try{await navigator.clipboard.writeText(campo.value.trim());aviso.textContent='SN copiado!';}
 catch(e){campo.select();document.execCommand('copy');aviso.textContent='Confira se o código foi copiado.';}
}
</script>
</body>
</html>
"""


def preparar(imagem):
    imagem = ImageOps.exif_transpose(imagem).convert("RGB")
    imagem.thumbnail((1500, 1500))
    cinza = ImageOps.grayscale(imagem)
    cinza = ImageEnhance.Contrast(cinza).enhance(1.7)
    cinza = cinza.filter(ImageFilter.SHARPEN)
    return cinza


def variantes(imagem):
    # Três versões: cinza melhorado, preto e branco e imagem ampliada.
    bw = imagem.point(lambda p: 255 if p > 155 else 0)
    ampliada = imagem.resize(
        (imagem.width * 2, imagem.height * 2),
        Image.Resampling.LANCZOS
    )
    return [imagem, bw, ampliada]


def ler_texto(imagem, modo):
    textos = []
    psm = [11, 6, 11]

    for img, modo_psm in zip(variantes(imagem), psm):
        config = (
            f"--oem 3 --psm {modo_psm} "
            "-c load_system_dawg=false "
            "-c load_freq_dawg=false"
        )
        try:
            textos.append(pytesseract.image_to_string(img, config=config, timeout=8))
        except TesseractError:
            continue

    return textos


def localizar_sn(textos):
    # Aceita variações comuns dos rótulos.
    rotulo = re.compile(
        r"(?:S\s*/\s*N|S\.?\s*N\.?|SERIAL\s*(?:NUMBER|NO\.?|NUMERO|N[ÚU]MERO)?)",
        re.IGNORECASE
    )

    codigo = re.compile(
        r"(?<![A-Za-z0-9])[A-Za-z0-9][A-Za-z0-9-]{7,23}(?![A-Za-z0-9])"
    )

    # Procura o código na mesma linha do rótulo ou logo abaixo.
    for texto in textos:
        linhas = [x.strip() for x in texto.splitlines() if x.strip()]

        for i, linha in enumerate(linhas):
            marca = rotulo.search(linha)
            if not marca:
                continue

            candidatos = codigo.findall(linha[marca.end():])

            if not candidatos and i + 1 < len(linhas):
                candidatos = codigo.findall(linhas[i + 1])

            for item in candidatos:
                item = re.sub(r"[^A-Za-z0-9-]", "", item).upper()
                if len(item) >= 8 and re.search(r"\d", item):
                    return item

    # Sem rótulo explícito, não adivinha um SN.
    return ""


@app.route("/", methods=["GET", "POST"])
def inicio():
    resultado = None
    modo = "etiqueta"

    if request.method == "POST":
        modo = request.form.get("modo", "etiqueta")
        arquivo = request.files.get("foto")

        if arquivo and arquivo.filename:
            try:
                imagem = Image.open(io.BytesIO(arquivo.read()))
                imagem = preparar(imagem)
                textos = ler_texto(imagem, modo)
                resultado = localizar_sn(textos)
            except (OSError, ValueError):
                resultado = ""
            except Exception:
                resultado = ""

    return render_template_string(HTML, resultado=resultado, modo=modo)


@app.errorhandler(413)
def arquivo_grande(_):
    return "Foto muito grande. Envie uma imagem de até 8 MB.", 413


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
