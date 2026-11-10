import sys
import os
import re
import json
import asyncio
import requests
import edge_tts
from PIL import Image, ImageDraw, ImageFont

# Compatibilidade Pillow / MoviePy
import PIL.Image
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = getattr(PIL.Image, 'LANCZOS', PIL.Image.BICUBIC)

try:
    from moviepy.editor import AudioFileClip, VideoFileClip, ImageClip, CompositeVideoClip
except ImportError:
    from moviepy.video.io.VideoFileClip import VideoFileClip
    from moviepy.audio.io.AudioFileClip import AudioFileClip
    from moviepy.video.VideoClip import ImageClip
    from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip

# 1. Entrada de dados
ROTEIRO_BRUTO = sys.argv[1] if len(sys.argv) > 1 else "Um garotinho corre alegremente pela floresta em um dia ensolarado."
FORMATO = sys.argv[2] if len(sys.argv) > 2 else "9:16"
PEXELS_API_KEY = sys.argv[3] if len(sys.argv) > 3 else ""

VOZ = "pt-BR-AntonioNeural"
DIMENSOES = (1080, 1920) if FORMATO == "9:16" else (1920, 1080)

HEADERS_DOWNLOAD = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def limpar_roteiro(texto):
    linhas = texto.split('\n')
    linhas_limpas = []
    for linha in linhas:
        l = re.sub(r'^(Cena\s*\d+|Narrador|Garoto|Homem|Mulher|Voz).*?:', '', linha, flags=re.IGNORECASE)
        l = re.sub(r'\(.*?\)|\[.*?\]', '', l).strip()
        if l:
            linhas_limpas.append(l)
    return linhas_limpas if linhas_limpas else [texto.strip()]

def extrair_palavras_chave(texto):
    t = texto.lower()
    mapa_busca = {
        'floresta': 'forest trees', 'garoto': 'boy child running', 'criança': 'kid happy',
        'cidade': 'city street', 'carro': 'car drive', 'praia': 'beach ocean',
        'tecnologia': 'technology computer', 'futuro': 'future neon', 'dinheiro': 'money business',
        'noite': 'night city', 'sol': 'sunny nature', 'festa': 'party friends'
    }
    for key, val in mapa_busca.items():
        if key in t:
            return val
    return "nature landscape"

async def gerar_audio(texto_completo):
    print("[1/4] Gerando narração...")
    communicate = edge_tts.Communicate(texto_completo, VOZ)
    await communicate.save("narracao.mp3")

def medir_texto(draw, texto, font):
    if hasattr(draw, 'textbbox'):
        bbox = draw.textbbox((0, 0), texto, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    else:
        return draw.textsize(texto, font=font)

def criar_imagem_legenda(texto, largura_max, caminho_saida):
    img = Image.new("RGBA", (largura_max, 250), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 44)
    except:
        font = ImageFont.load_default()

    palavras = texto.split()
    linhas = []
    linha_atual = ""
    
    for p in palavras:
        teste = f"{linha_atual} {p}".strip()
        w, _ = medir_texto(draw, teste, font)
        if w <= (largura_max - 60):
            linha_atual = teste
        else:
            if linha_atual:
                linhas.append(linha_atual)
            linha_atual = p
    if linha_atual:
        linhas.append(linha_atual)
    
    texto_formatado = "\n".join(linhas)
    w_total, h_total = medir_texto(draw, texto_formatado, font)
    
    x = (largura_max - w_total) // 2
    y = (250 - h_total) // 2

    padding = 15
    draw.rectangle([max(0, x - padding), max(0, y - padding), min(largura_max, x + w_total + padding), min(250, y + h_total + padding)], fill=(0, 0, 0, 210))
    draw.text((x, y), texto_formatado, fill="yellow", font=font, align="center")
    
    img.save(caminho_saida)
    return caminho_saida

def baixar_e_validar(url, nome_arquivo="fundo.mp4"):
    r = requests.get(url, headers=HEADERS_DOWNLOAD, timeout=60, stream=True)
    with open(nome_arquivo, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    return nome_arquivo

def buscar_video_fundo(query):
    print(f"[2/4] Buscando vídeo no Pexels para a cena: '{query}'...")
    orientacao = 'portrait' if FORMATO == "9:16" else 'landscape'
    url = f"https://api.pexels.com/videos/search?query={query}&per_page=5&orientation={orientacao}"
    headers_api = {"Authorization": PEXELS_API_KEY, **HEADERS_DOWNLOAD} if PEXELS_API_KEY else HEADERS_DOWNLOAD

    try:
        if PEXELS_API_KEY:
            response = requests.get(url, headers=headers_api, timeout=15)
            if response.status_code == 200:
                data = response.json()
                if data.get('videos') and len(data['videos']) > 0:
                    video_url = data['videos'][0]['video_files'][0]['link']
                    return baixar_e_validar(video_url, "fundo.mp4")
        raise Exception("Pexels Key ausente ou sem resultados")
    except Exception as e:
        print(f"Usando vídeo de reserva... Detalhes: {e}")
        video_fallback = "https://raw.githubusercontent.com/intel-iot-devkit/sample-videos/master/person-bicycle-car-detection.mp4"
        return baixar_e_validar(video_fallback, "fundo.mp4")

def montar_video(frases_limpas):
    print("[3/4] Sincronizando legendas e áudio...")
    audio = AudioFileClip("narracao.mp3")
    duracao_total = audio.duration

    fundo = VideoFileClip("fundo.mp4")
    if fundo.duration < duracao_total:
        fundo = fundo.loop(duration=duracao_total)
    else:
        fundo = fundo.subclip(0, duracao_total)
    
    fundo = fundo.resize(newsize=DIMENSOES).set_audio(audio)

    clips_legendas = []
    duracao_por_frase = duracao_total / len(frases_limpas)
    
    for i, frase in enumerate(frases_limpas):
        tempo_inicio = i * duracao_por_frase
        img_path = f"legenda_{i}.png"
        criar_imagem_legenda(frase, DIMENSOES[0] - 80, img_path)
        
        pos_y = DIMENSOES[1] - 450 if FORMATO == "9:16" else DIMENSOES[1] - 250
        clip_txt = (ImageClip(img_path)
                    .set_start(tempo_inicio)
                    .set_duration(duracao_por_frase)
                    .set_position(('center', pos_y)))
        clips_legendas.append(clip_txt)

    video_final = CompositeVideoClip([fundo] + clips_legendas)

    print("[4/4] Renderizando MP4 final...")
    video_final.write_videofile("resultado.mp4", fps=24, codec="libx264", audio_codec="aac")

if __name__ == "__main__":
    frases = limpar_roteiro(ROTEIRO_BRUTO)
    texto_narracao = " ".join(frases)
    query_busca = extrair_palavras_chave(ROTEIRO_BRUTO)
    
    asyncio.run(gerar_audio(texto_narracao))
    buscar_video_fundo(query_busca)
    montar_video(frases)
