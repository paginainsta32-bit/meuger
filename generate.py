import sys
import os
import json
import asyncio
import requests
import edge_tts

# Importação compatível com diferentes versões do MoviePy
try:
    from moviepy.editor import AudioFileClip, VideoFileClip, TextClip, CompositeVideoClip, concatenate_videoclips
except ImportError:
    from moviepy.video.io.VideoFileClip import VideoFileClip
    from moviepy.audio.io.AudioFileClip import AudioFileClip
    from moviepy.video.VideoClip import TextClip
    from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
    from moviepy.video.compositing.concatenate import concatenate_videoclips

# 1. Configurações recebidas
ROTEIRO = sys.argv[1] if len(sys.argv) > 1 else "Este é um teste de vídeo automático."
FORMATO = sys.argv[2] if len(sys.argv) > 2 else "9:16"  # "9:16" ou "16:9"
PEXELS_API_KEY = sys.argv[3] if len(sys.argv) > 3 else ""

VOZ = "pt-BR-AntonioNeural" # Voz masculina excelente (ou "pt-BR-FranciscaNeural")
DIMENSOES = (1080, 1920) if FORMATO == "9:16" else (1920, 1080)

HEADERS_DOWNLOAD = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

async def gerar_audio():
    print("[1/4] Gerando narração com voz realista...")
    communicate = edge_tts.Communicate(ROTEIRO, VOZ)
    await communicate.save("narracao.mp3")

def baixar_e_validar(url, nome_arquivo="fundo.mp4"):
    r = requests.get(url, headers=HEADERS_DOWNLOAD, timeout=60, stream=True)
    with open(nome_arquivo, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    
    tamanho = os.path.getsize(nome_arquivo)
    print(f"Arquivo {nome_arquivo} baixado. Tamanho: {tamanho} bytes")
    if tamanho < 10000:  # Menor que 10KB é download corrompido/inválido
        raise Exception("Arquivo baixado é inválido ou muito pequeno.")
    return nome_arquivo

def buscar_video_fundo(query="nature"):
    print("[2/4] Buscando vídeo de fundo no Pexels...")
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
                    print(f"Baixando vídeo do Pexels: {video_url}")
                    return baixar_e_validar(video_url, "fundo.mp4")
        
        print("AVISO: Chave do Pexels ausente ou nenhum vídeo encontrado. Usando vídeo de reserva...")
        raise Exception("Usando fallback")

    except Exception as e:
        print(f"Baixando vídeo de fundo padrão (Fallback)... Detalhes: {e}")
        # Vídeo público direto em CDN confiável
        video_fallback = "https://raw.githubusercontent.com/intel-iot-devkit/sample-videos/master/person-bicycle-car-detection.mp4"
        return baixar_e_validar(video_fallback, "fundo.mp4")

def montar_video():
    print("[3/4] Montando o vídeo final...")
    audio = AudioFileClip("narracao.mp3")
    duracao_audio = audio.duration

    fundo = VideoFileClip("fundo.mp4")
    
    if fundo.duration < duracao_audio:
        fundo = fundo.loop(duration=duracao_audio)
    else:
        fundo = fundo.subclip(0, duracao_audio)

    fundo = fundo.resize(newsize=DIMENSOES)
    fundo = fundo.set_audio(audio)

    # Legenda simples centralizada
    legenda = TextClip(
        ROTEIRO, 
        fontsize=45, 
        color='white', 
        bg_color='black',
        method='caption', 
        size=(DIMENSOES[0] - 100, None)
    )
    legenda = legenda.set_position('center').set_duration(duracao_audio)

    video_final = CompositeVideoClip([fundo, legenda])

    print("[4/4] Renderizando MP4 final...")
    video_final.write_videofile("resultado.mp4", fps=24, codec="libx264", audio_codec="aac")

if __name__ == "__main__":
    asyncio.run(gerar_audio())
    buscar_video_fundo("technology abstract")
    montar_video()
