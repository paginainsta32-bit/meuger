import sys
import os
import re
import time
import random
import asyncio
import requests
import urllib.parse
import edge_tts
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

# Tradutor
try:
    from deep_translator import GoogleTranslator
    HAS_TRANSLATOR = True
except ImportError:
    HAS_TRANSLATOR = False

# Compatibilidade Pillow / MoviePy
import PIL.Image
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = getattr(PIL.Image, 'LANCZOS', PIL.Image.BICUBIC)

try:
    from moviepy.editor import AudioFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips
except ImportError:
    from moviepy.audio.io.AudioFileClip import AudioFileClip
    from moviepy.video.VideoClip import ImageClip
    from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
    from moviepy.video.compositing.concatenate import concatenate_videoclips

# 1. Parâmetros Recebidos
ROTEIRO_BRUTO = sys.argv[1] if len(sys.argv) > 1 else "Um garotinho corre pela floresta."
FORMATO = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] in ["9:16", "16:9"] else "9:16"
PEXELS_API_KEY = sys.argv[3] if len(sys.argv) > 3 and "cfut_" not in sys.argv[3] else os.environ.get("PEXELS_KEY", "")
ESTILO = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] in ["cartoon", "anime", "3d", "realista"] else "3d"
EFEITO = sys.argv[5] if len(sys.argv) > 5 else "zoom"

VOZ = "pt-BR-AntonioNeural"
DIMENSOES = (1080, 1920) if FORMATO == "9:16" else (1920, 1080)

HEADERS_DOWNLOAD = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def limpar_roteiro(texto):
    t = re.sub(r'^(Cena\s*\d+|Narrador|Garoto|Homem|Mulher|Voz).*?:', '', texto, flags=re.IGNORECASE)
    t = re.sub(r'\(.*?\)|\[.*?\]', '', t)
    linhas_brutas = re.split(r'[\n\.]+', t)
    
    frases_limpas = []
    for l in linhas_brutas:
        item = l.strip()
        if len(item) > 3:
            frases_limpas.append(item)
    return frases_limpas if frases_limpas else [texto.strip()]

def traduzir_ou_extrair_prompt(frase_pt, index):
    frase_en = None
    if HAS_TRANSLATOR:
        try:
            frase_en = GoogleTranslator(source='pt', target='en').translate(frase_pt)
        except Exception:
            pass

    # Tradução local instantânea caso a API do Google Translate bloqueie
    if not frase_en or frase_en == frase_pt:
        dicionario = {
            'parque': 'magical playground park with giant flowers',
            'árvores': 'colorful trees and rainbow',
            'flores': 'giant magical flowers',
            'brinquedos': 'playground toys',
            'pedro': 'cute little boy Pedro',
            'luna': 'cute little girl Luna',
            'bidu': 'playful cute puppy dog',
            'correndo': 'running happily and smiling',
            'sorrindo': 'smiling cheerful',
            'pulando': 'jumping happily',
            'rabinho': 'wagging little tail',
            'floresta': 'enchanted green forest',
            'cidade': 'modern city street',
            'carro': 'fast modern sport car'
        }
        palavras_en = []
        for p in frase_pt.lower().split():
            p_limpa = re.sub(r'[^\w]', '', p)
            if p_limpa in dicionario:
                palavras_en.append(dicionario[p_limpa])
        
        if palavras_en:
            frase_en = ", ".join(palavras_en)
        else:
            frase_en = f"cute characters in scene number {index+1}"

    sufixos = {
        "cartoon": "vibrant 2d cartoon illustration style, disney aesthetic, colorful, 8k resolution",
        "anime": "anime art style, studio ghibli aesthetic, makoto shinkai lighting, 8k resolution",
        "3d": "3d render animation, pixar character style, disney 3d movie, unreal engine 5 render, cute, highly detailed",
        "realista": "cinematic realistic photo, hyperrealistic, 8k, professional photography, sharp focus"
    }
    
    sufixo = sufixos.get(ESTILO, sufixos["3d"])
    return f"{frase_en}, {sufixo}"

async def gerar_audio(texto_completo):
    print("[1/4] Gerando narração...")
    communicate = edge_tts.Communicate(texto_completo, VOZ)
    await communicate.save("narracao.mp3")

def gerador_imagem_ia_gratis(prompt, nome_saida, index):
    print(f"🎨 Gerando imagem IA (Pollinations)...")
    print(f"Prompt EN: '{prompt}'")
    
    if index > 0:
        time.sleep(3)  # Pausa essencial entre chamadas

    prompt_encoded = urllib.parse.quote(prompt)
    largura, altura = (1080, 1920) if FORMATO == "9:16" else (1920, 1080)
    seed_random = random.randint(1000, 999999)
    
    # Lista de endpoints/modelos para rotação automática
    modelos = ["flux", "turbo", "pixart"]

    for model in modelos:
        url = f"https://image.pollinations.ai/prompt/{prompt_encoded}?width={largura}&height={altura}&nologo=true&seed={seed_random}&model={model}"
        try:
            res = requests.get(url, headers=HEADERS_DOWNLOAD, timeout=40)
            print(f"--> Modelo '{model}' Status: {res.status_code}")
            if res.status_code == 200 and len(res.content) > 5000:
                with open(nome_saida, "wb") as f:
                    f.write(res.content)
                print(f"✅ IMAGEM IA GERADA COM SUCESSO (Modelo: {model})!")
                return nome_saida
        except Exception as err:
            print(f"Aviso no modelo {model}: {err}")
        time.sleep(2)

    raise Exception("Todos os modelos de IA falharam temporariamente.")

def processar_e_ajustar_imagem(caminho_imagem):
    img = Image.open(caminho_imagem)
    
    if EFEITO == "vivido":
        enhancer = ImageEnhance.Color(img)
        img = enhancer.enhance(1.5)
    elif EFEITO == "vintage":
        enhancer = ImageEnhance.Color(img)
        img = enhancer.enhance(0.7)

    w_target, h_target = DIMENSOES
    w_orig, h_orig = img.size
    
    ratio_target = w_target / h_target
    ratio_orig = w_orig / h_orig
    
    if ratio_orig > ratio_target:
        new_w = int(h_target * ratio_orig)
        new_h = h_target
    else:
        new_w = w_target
        new_h = int(w_target / ratio_orig)
        
    img_resized = img.resize((new_w, new_h), Image.LANCZOS)
    
    left = (new_w - w_target) // 2
    top = (new_h - h_target) // 2
    right = left + w_target
    bottom = top + h_target
    
    img_cropped = img_resized.crop((left, top,
