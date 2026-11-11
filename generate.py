import sys
import os
import re
import asyncio
import requests
import edge_tts
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from deep_translator import GoogleTranslator

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
ESTILO = sys.argv[4] if len(sys.argv) > 4 else "3d"
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

def construir_prompt_flux(frase_pt):
    try:
        frase_en = GoogleTranslator(source='pt', target='en').translate(frase_pt)
    except Exception as e:
        print(f"Aviso na tradução: {e}")
        frase_en = frase_pt

    sufixos = {
        "cartoon": "vibrant 2d cartoon illustration style, disney pixar aesthetic, colorful, highly detailed",
        "anime": "anime art style, studio ghibli aesthetic, makoto shinkai lighting, 8k resolution",
        "3d": "3d render animation, pixar character style, disney 3d movie, unreal engine 5, octane render, cute, highly detailed",
        "realista": "cinematic realistic photo, hyperrealistic, 8k, professional photography, dramatic lighting"
    }
    
    sufixo = sufixos.get(ESTILO, sufixos["3d"])
    return f"{frase_en}, {sufixo}"

async def gerar_audio(texto_completo):
    print("[1/4] Gerando narração...")
    communicate = edge_tts.Communicate(texto_completo, VOZ)
    await communicate.save("narracao.mp3")

def gerador_imagem_flux(prompt, nome_saida):
    print(f"🎨 Gerando imagem IA (FLUX-1-Schnell)...")
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

    if response.status_code == 200:
        res_json = response.json()
        if res_json.get("success") and "result" in res_json and "image" in res_json["result"]:
            import base64
            image_bytes = base64.b64decode(res_json["result"]["image"])
            with open(nome_saida, "wb") as f:
                f.write(image_bytes)
            print("✅ Imagem IA criada com sucesso pelo FLUX.1!")
            return nome_saida
    raise Exception("Falha na geração via Cloudflare")

def processar_e_ajustar_imagem(caminho_imagem):
    # Recorta e ajusta a imagem para preencher toda a tela sem bordas pretas
    img = Image.open(caminho_imagem)
    
    if EFEITO == "vivido":
        enhancer = ImageEnhance.Color(img)
        img = enhancer.enhance(1.5)
    elif EFEITO == "vintage":
        enhancer = ImageEnhance.Color(img)
        img = enhancer.enhance(0.7)

    # Redimensionamento inteligente (Crop Cover)
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
    
    img_cropped = img_resized.crop((left, top, right, bottom))
    img_cropped.save(caminho_imagem)

def criar_imagem_legenda(texto_pt, largura_max, caminho_saida):
    # Gera a legenda em PORTUGUÊS
    img = Image.new("RGBA", (largura_max, 260), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 44)
    except:
        font = ImageFont.load_default()

    palavras = texto_pt.split()
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

def obter_imagem_cena(frase_pt, index):
    nome_foto = f"foto_{index}.jpg"
    prompt_en = construir_prompt_flux(frase_pt)

    if CF_ACCOUNT_ID and CF_API_TOKEN:
        try:
            gerador_imagem_flux(prompt_en, nome_foto)
            processar_e_ajustar_imagem(nome_foto)
            return nome_foto
        except Exception as e:
            print(f"⚠️ Cloudflare falhou na cena {index+1}: {e}")

    # Fallback de emergência
    img_fallback = "https://images.pexels.com/photos/15286/pexels-photo.jpg"
    r = requests.get(img_fallback, timeout=20)
    with open(nome_foto, "wb") as f: f.write(r.content)
    processar_e_ajustar_imagem(nome_foto)
    return nome_foto

def montar_video(frases_limpas):
    print("[3/4] Montando imagens e narração...")
    audio = AudioFileClip("narracao.mp3")
    duracao_total = audio.duration
    duracao_por_cena = duracao_total / len(frases_limpas)

    clips_fundo = []
    clips_legendas = []

    for i, frase_pt in enumerate(frases_limpas):
        tempo_inicio = i * duracao_por_cena
        foto_path = obter_imagem_cena(frase_pt, i)
        
        clip_img = (ImageClip(foto_path)
                    .set_duration(duracao_por_cena)
                    .resize(newsize=DIMENSOES))
        
        if EFEITO == "zoom":
            clip_img = clip_img.resize(lambda t: 1 + 0.04 * t)
            
        clips_fundo.append(clip_img)
        
        # Passa a frase em PORTUGUÊS para a legenda
        legenda_path = f"legenda_{i}.png"
        criar_imagem_legenda(frase_pt, DIMENSOES[0] - 80, legenda_path)
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
