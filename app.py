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
    border: 3px solid #1767df;
    border-radius: 8px;
    pointer-events: none;
    box-shadow: 0 0 8px rgba(23, 103, 223, 0.25);
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
        Posicione o número de série dentro da moldura azul.
    </p>

    <div class="camera">
        <video id="video" autoplay playsinline muted></video>
        <div class="frame"></div>
    </div>

    <button id="capture">📷 Tirar foto</button>

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
    statusText.textContent = "Enviando a
