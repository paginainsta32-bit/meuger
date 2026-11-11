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

# 1. Dados recebidos
ROTEIRO_BRUTO = sys.argv[1] if len(sys.argv) > 1 else "Um garotinho corre pela floresta."
FORMATO = sys.argv[2] if len(sys.argv) > 2 else "9:16"
PEXELS_API_KEY = sys.argv[3] if len(sys.argv) > 3 else ""
ESTILO = sys.argv[4] if len(sys.argv) > 4 else "realista"
EFEITO = sys.argv[5] if len(sys.argv) > 5 else "zoom"
CF_ACCOUNT_ID = sys.argv[6] if len(sys.argv) > 6 else ""
CF_API_TOKEN = sys.argv[7] if len(sys.argv) > 7 else ""

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

def construir_prompt_flux(frase):
    f = frase.lower()
    mapa = {
        'garoto': 'a young boy', 'menino': 'a young boy', 'criança': 'a happy child',
        'floresta': 'dense green forest', 'riacho': 'sparkling river stream', 'rio': 'beautiful river',
        'cidade': 'modern city street', 'carro': 'fast sport car', 'praia': 'sunny tropical beach',
        'tecnologia': 'futuristic technology', 'futuro': 'cyberpunk city neon lights', 'dinheiro': 'stacks of cash money',
        'noite': 'mysterious night sky with stars', 'sol': 'bright sunlight and warm day', 'festa': 'vibrant party celebration'
    }
    
    sujeito = "scenery"
    for key, val in mapa.items():
        if key in f:
            sujeito = val
            break
            
    sufixos = {
        "cartoon": "cartoon 2d style, vibrant colors, disney pixel art, highly detailed",
        "anime": "anime style, makoto shinkai aesthetics, studio ghibli, 8k resolution",
        "3d": "3d render, pixar style, unreal engine 5, octane render, cute and detailed",
        "realista": "hyperrealistic photography, 8k, cinematic lighting, sharp focus, professional photo"
    }
    
    sufixo = sufixos.get(ESTILO, sufixos["realista"])
    return f"{sujeito}, {frase}, {sufixo}"

async def gerar_audio(texto_completo):
    print("[1/4] Gerando narração...")
    communicate = edge_tts.Communicate(texto_completo, VOZ)
    await communicate.save("narracao.mp3")

def gerador_imagem_flux(prompt, nome_saida):
    print(f"🎨 Chamando Cloudflare FLUX-1-Schnell para o prompt: '{prompt[:60]}...'")
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/blackforestlabs/flux-1-schnell"
    
    headers = {
        "Authorization": f"Bearer {CF_API_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "prompt": prompt,
        "num_steps": 4
    }
    
    response = requests.post(url, headers=headers, json=payload, timeout=60)
    print(f"Status API Cloudflare: {response.status_code}")

    if response.status_code == 200:
        res_json = response.json()
        if res_json.get("success") and "result" in res_json and "image" in res_json["result"]:
            import base64
            image_bytes = base64.b64decode(res_json["result"]["image"])
            with open(nome_saida, "wb") as f:
                f.write(image_bytes)
            print("✅ Imagem IA gerada e salva com sucesso!")
            return nome_saida
        else:
            print(f"❌ Resposta de erro da Cloudflare: {res_json}")
    else:
        print(f"❌ Erro HTTP na Cloudflare ({response.status_code}): {response.text}")
        
    raise Exception("Falha na geração de imagem com a Cloudflare Workers AI.")

def aplicar_efeito_filtro(caminho_imagem):
    try:
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
    except Exception as e:
        print(f"Aviso no filtro: {e}")

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

def obter_imagem_cena(frase, index):
    nome_foto = f"foto_{index}.jpg"
    prompt = construir_prompt_flux(frase)

    print(f"\n--- Processando Cena {index+1} ---")
    print(f"CF_ACCOUNT_ID presente: {bool(CF_ACCOUNT_ID)}")
    print(f"CF_API_TOKEN presente: {bool(CF_API_TOKEN)}")

    # 1. Tenta gerar via FLUX.1 (Cloudflare Workers AI)
    if CF_ACCOUNT_ID and CF_API_TOKEN:
        try:
            gerador_imagem_flux(prompt, nome_foto)
            aplicar_efeito_filtro(nome_foto)
            return nome_foto
        except Exception as e:
            print(f"⚠️ Erro ao gerar com FLUX.1: {e}")

    # 2. Fallback Pexels se a Cloudflare falhar
    print("Tentando buscar no Pexels como alternativa...")
    try:
        url = f"https://api.pexels.com/v1/search?query={prompt}&per_page=1"
        headers = {"Authorization": PEXELS_API_KEY} if PEXELS_API_KEY else {}
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200 and res.json().get('photos'):
            img_url = res.json()['photos'][0]['src']['large2x']
            r = requests.get(img_url, timeout=20)
            with open(nome_foto, "wb") as f: f.write(r.content)
            aplicar_efeito_filtro(nome_foto)
            return nome_foto
    except Exception as ex:
        print(f"Erro no Pexels: {ex}")

    # 3. Imagem de reserva final
    print("Usando imagem estática de reserva final.")
    img_fallback = "https://images.pexels.com/photos/15286/pexels-photo.jpg"
    r = requests.get(img_fallback, timeout=20)
    with open(nome_foto, "wb") as f: f.write(r.content)
    aplicar_efeito_filtro(nome_foto)
    return nome_foto

def montar_video(frases_limpas):
    print("[3/4] Montando vídeo com as imagens e narração...")
    audio = AudioFileClip("narracao.mp3")
    duracao_total = audio.duration
    duracao_por_cena = duracao_total / len(frases_limpas)

    clips_fundo = []
    clips_legendas = []

    for i, frase in enumerate(frases_limpas):
        tempo_inicio = i * duracao_por_cena
        foto_path = obter_imagem_cena(frase, i)
        
        clip_img = (ImageClip(foto_path)
                    .set_duration(duracao_por_cena)
                    .resize(newsize=DIMENSOES))
        
        if EFEITO == "zoom":
            clip_img = clip_img.resize(lambda t: 1 + 0.04 * t)
            
        clips_fundo.append(clip_img)
        
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
