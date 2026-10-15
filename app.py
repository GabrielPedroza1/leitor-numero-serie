```python
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
    background: #101827;
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
    margin-bottom: 12px;
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
    border: 3px solid #1767df;
    border-radius: 6px;
    pointer-events: none;
}

button {
    width: 100%;
    min-height: 56px;
    padding: 16px;
    margin-top: 12px;
    border: none;
    border-radius: 9px;
    background: #1767df;
    color: white;
    font-size: 17px;
    font-weight: bold;
    cursor: pointer;
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
    margin-top: 16px;
    padding: 15px;
    border: 2px solid #1767df;
    border-radius: 9px;
    background: #202b3a;
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
    margin-top: 12px;
    color: #d6d6d6;
    font-size: 14px;
    line-height: 1.5;
    overflow-wrap: anywhere;
}
</style>
</head>

<body>
<div class="container">
    <h1>Leitor de Número de Série</h1>

    <p class="hint">
        Posicione o número
