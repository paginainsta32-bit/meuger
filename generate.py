import sys
import os
import re
import asyncio
import requests
import edge_tts
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

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

# 1. Dados recebidos do site
ROTEIRO_BRUTO = sys.argv[1] if len(sys.argv) > 1 else "Um garotinho corre pela floresta."
FORMATO = sys.argv[2] if len(sys.argv) > 2 else "9:16"
PEXELS_API_KEY = sys.argv[3] if len(sys.argv) > 3 else ""
ESTILO = sys.argv[4] if len(sys.argv) > 4 else "realista"
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

def extrair_termo_busca(frase):
    f = frase.lower()
    mapa = {
        'garoto': 'boy child', 'menino': 'kid boy', 'criança': 'happy child',
        'floresta': 'forest trees', 'riacho': 'river stream', 'rio': 'river nature',
        'cidade': 'city street', 'carro': 'car drive', 'praia': 'beach sea',
        'tecnologia': 'technology', 'futuro': 'future neon', 'dinheiro': 'money cash',
        'noite': 'night dark', 'sol': 'sunlight nature', 'festa': 'party celebration'
    }
    
    termo_base = "nature background"
    for key, val in mapa.items():
        if key in f:
            termo_base = val
            break
            
    # Adiciona a palavra do estilo visual escolhido à busca
    if ESTILO == "cartoon":
        return f"{termo_base} cartoon illustration"
    elif ESTILO == "anime":
        return f"{termo_base} anime style"
    elif ESTILO == "3d":
        return f"{termo_base} 3d render animation"
    else:
        return termo_base

async def gerar_audio(texto_completo):
    print("[1/4] Gerando narração...")
    communicate = edge_tts.Communicate(texto_completo, VOZ)
    await communicate.save("narracao.mp3")

def aplicar_efeito_filtro(caminho_imagem):
    # Aplica os filtros estilo CapCut na imagem
    img = Image.open(caminho_imagem)
    if EFEITO == "vivido":
        enhancer = ImageEnhance.Color(img)
        img = enhancer.enhance(1.6)
    elif EFEITO == "vintage":
        enhancer = ImageEnhance.Color(img)
        img = enhancer.enhance(0.7)
        enhancer_b = ImageEnhance.Brightness(img)
        img = enhancer_b.enhance(0.9)
    img.save(caminho_imagem)

def criar_imagem_legenda(texto, largura_max, caminho_saida):
    img = Image.new("RGBA", (largura_max, 260), (0, 0, 0, 0))
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
        bbox = draw.textbbox((0, 0), teste, font=font) if hasattr(draw, 'textbbox') else (0,0,100,20)
        w = bbox[2] - bbox[0]
        if w <= (largura_max - 60):
            linha_atual = teste
        else:
            if linha_atual: linhas.append(linha_atual)
            linha_atual = p
    if linha_atual: linhas.append(linha_atual)
    
    texto_formatado = "\n".join(linhas)
    x, y = 40, 40

    draw.rectangle([10, 10, largura_max - 10, 240], fill=(0, 0, 0, 210))
    draw.multiline_text((x, y), texto_formatado, fill="#facc15", font=font, align="center")
    
    img.save(caminho_saida)
    return caminho_saida

def buscar_foto_pexels(query, index):
    orientacao = 'portrait' if FORMATO == "9:16" else 'landscape'
    url = f"https://api.pexels.com/v1/search?query={query}&per_page=5&orientation={orientacao}"
    headers_api = {"Authorization": PEXELS_API_KEY, **HEADERS_DOWNLOAD} if PEXELS_API_KEY else HEADERS_DOWNLOAD
    nome_foto = f"foto_{index}.jpg"

    try:
        if PEXELS_API_KEY:
            res = requests.get(url, headers=headers_api, timeout=15)
            if res.status_code == 200:
                data = res.json()
                if data.get('photos') and len(data['photos']) > 0:
                    img_url = data['photos'][0]['src']['large2x']
                    r = requests.get(img_url, headers=HEADERS_DOWNLOAD, timeout=30)
                    with open(nome_foto, "wb") as f:
                        f.write(r.content)
                    aplicar_efeito_filtro(nome_foto)
                    return nome_foto
        raise Exception("Uso de imagem padrão")
    except Exception as e:
        img_fallback = "https://images.pexels.com/photos/15286/pexels-photo.jpg"
        r = requests.get(img_fallback, headers=HEADERS_DOWNLOAD, timeout=30)
        with open(nome_foto, "wb") as f:
            f.write(r.content)
        aplicar_efeito_filtro(nome_foto)
        return nome_foto

def montar_video(frases_limpas):
    print("[3/4] Montando imagens, animações e efeitos...")
    audio = AudioFileClip("narracao.mp3")
    duracao_total = audio.duration
    duracao_por_cena = duracao_total / len(frases_limpas)

    clips_fundo = []
    clips_legendas = []

    for i, frase in enumerate(frases_limpas):
        tempo_inicio = i * duracao_por_cena
        termo = extrair_termo_busca(frase)
        foto_path = buscar_foto_pexels(termo, i)
        
        # Clip da imagem base
        clip_img = (ImageClip(foto_path)
                    .set_duration(duracao_por_cena)
                    .resize(newsize=DIMENSOES))
        
        # Efeito Ken Burns (Zoom Suave estilo CapCut)
        if EFEITO == "zoom":
            clip_img = clip_img.resize(lambda t: 1 + 0.04 * t)
            
        clips_fundo.append(clip_img)
        
        # Legenda amarela estilizada
        legenda_path = f"legenda_{i}.png"
        criar_imagem_legenda(frase, DIMENSOES[0] - 80, legenda_path)
        pos_y = DIMENSOES[1] - 450 if FORMATO == "9:16" else DIMENSOES[1] - 250
        
        clip_leg = (ImageClip(legenda_path)
                    .set_start(tempo_inicio)
                    .set_duration(duracao_por_cena)
                    .set_position(('center', pos_y)))
        clips_legendas.append(clip_leg)

    fundo_sequencial = concatenate_videoclips(clips_fundo, method="compose").set_audio(audio)
    video_final = CompositeVideoClip([fundo_sequencial] + clips_legendas)

    print("[4/4] Renderizando MP4 final...")
    video_final.write_videofile("resultado.mp4", fps=24, codec="libx264", audio_codec="aac")

if __name__ == "__main__":
    frases = limpar_roteiro(ROTEIRO_BRUTO)
    texto_narracao = " ".join(frases)
    
    asyncio.run(gerar_audio(texto_narracao))
    montar_video(frases)
