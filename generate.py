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
    from moviepy.editor import AudioFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips
except ImportError:
    from moviepy.audio.io.AudioFileClip import AudioFileClip
    from moviepy.video.VideoClip import ImageClip
    from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
    from moviepy.video.compositing.concatenate import concatenate_videoclips

# 1. Configurações recebidas
ROTEIRO_BRUTO = sys.argv[1] if len(sys.argv) > 1 else "Um garotinho corre alegremente pela floresta em um dia ensolarado."
FORMATO = sys.argv[2] if len(sys.argv) > 2 else "9:16"
PEXELS_API_KEY = sys.argv[3] if len(sys.argv) > 3 else ""

VOZ = "pt-BR-AntonioNeural"
DIMENSOES = (1080, 1920) if FORMATO == "9:16" else (1920, 1080)

HEADERS_DOWNLOAD = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def limpar_roteiro(texto):
    # Remove marcadores como "Cena 1:" ou "[Música]"
    t = re.sub(r'^(Cena\s*\d+|Narrador|Garoto|Homem|Mulher|Voz).*?:', '', texto, flags=re.IGNORECASE)
    t = re.sub(r'\(.*?\)|\[.*?\]', '', t)
    
    # Quebra por linha ou por pontos finais
    linhas_brutas = re.split(r'[\n\.]+', t)
    
    frases_limpas = []
    for l in linhas_brutas:
        item = l.strip()
        if len(item) > 3:  # Ignora frases vazias ou muito curtas
            frases_limpas.append(item)
            
    print(f"Roteiro dividido em {len(frases_limpas)} cenas/fotos.")
    return frases_limpas if frases_limpas else [texto.strip()]
def extrair_termo_busca(frase):
    f = frase.lower()
    mapa = {
        'garoto': 'boy child', 'menino': 'kid boy', 'criança': 'happy child',
        'floresta': 'forest trees', 'riacho': 'river stream', 'rio': 'river nature',
        'cidade': 'city street', 'carro': 'car drive', 'praia': 'beach sea',
        'tecnologia': 'technology', 'futuro': 'future neon', 'dinheiro': 'money cash',
        'noite': 'night dark', 'sol': 'sunlight nature', 'festa': 'party celebration',
        'casa': 'cozy house', 'montanha': 'mountain landscape', 'espacial': 'galaxy space'
    }
    for key, val in mapa.items():
        if key in f:
            return val
    return "nature background"

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
    y = (260 - h_total) // 2

    padding = 15
    draw.rectangle([max(0, x - padding), max(0, y - padding), min(largura_max, x + w_total + padding), min(260, y + h_total + padding)], fill=(0, 0, 0, 220))
    draw.text((x, y), texto_formatado, fill="yellow", font=font, align="center")
    
    img.save(caminho_saida)
    return caminho_saida

def buscar_foto_pexels(query, index):
    print(f"[2/4] Buscando foto Pexels para a cena {index+1}: '{query}'...")
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
                    return nome_foto
        raise Exception("Pexels Key ausente ou sem fotos")
    except Exception as e:
        print(f"Usando foto padrão para a cena {index+1}... ({e})")
        img_fallback = "https://images.pexels.com/photos/15286/pexels-photo.jpg"
        r = requests.get(img_fallback, headers=HEADERS_DOWNLOAD, timeout=30)
        with open(nome_foto, "wb") as f:
            f.write(r.content)
        return nome_foto

def montar_video(frases_limpas):
    print("[3/4] Montando sequência de fotos e legendas...")
    audio = AudioFileClip("narracao.mp3")
    duracao_total = audio.duration
    duracao_por_cena = duracao_total / len(frases_limpas)

    clips_fundo = []
    clips_legendas = []

    for i, frase in enumerate(frases_limpas):
        tempo_inicio = i * duracao_por_cena
        
        # 1. Busca foto da cena
        termo = extrair_termo_busca(frase)
        foto_path = buscar_foto_pexels(termo, i)
        
        # Clip da Foto (Duração individual por frase)
        clip_img = (ImageClip(foto_path)
                    .set_duration(duracao_por_cena)
                    .resize(newsize=DIMENSOES))
        clips_fundo.append(clip_img)
        
        # 2. Clip da Legenda Sincronizada
        legenda_path = f"legenda_{i}.png"
        criar_imagem_legenda(frase, DIMENSOES[0] - 80, legenda_path)
        pos_y = DIMENSOES[1] - 450 if FORMATO == "9:16" else DIMENSOES[1] - 250
        
        clip_leg = (ImageClip(legenda_path)
                    .set_start(tempo_inicio)
                    .set_duration(duracao_por_cena)
                    .set_position(('center', pos_y)))
        clips_legendas.append(clip_leg)

    # Concatena as fotos em sequência temporal contínua
    fundo_sequencial = concatenate_videoclips(clips_fundo, method="compose").set_audio(audio)
    video_final = CompositeVideoClip([fundo_sequencial] + clips_legendas)

    print("[4/4] Renderizando MP4 final...")
    video_final.write_videofile("resultado.mp4", fps=24, codec="libx264", audio_codec="aac")

if __name__ == "__main__":
    frases = limpar_roteiro(ROTEIRO_BRUTO)
    texto_narracao = " ".join(frases)
    
    asyncio.run(gerar_audio(texto_narracao))
    montar_video(frases)
