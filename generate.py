import sys
import json
import asyncio
import requests
import edge_tts
from moviepy.editor import AudioFileClip, VideoFileClip, TextClip, CompositeVideoClip, concatenate_videoclips

# 1. Configurações recebidas
ROTEIRO = sys.argv[1] if len(sys.argv) > 1 else "Este é um teste de vídeo automático."
FORMATO = sys.argv[2] if len(sys.argv) > 2 else "9:16"  # "9:16" ou "16:9"
PEXELS_API_KEY = sys.argv[3] if len(sys.argv) > 3 else ""

VOZ = "pt-BR-AntonioNeural" # Voz masculina excelente (ou "pt-BR-FranciscaNeural")

# Resolução baseada no formato
DIMENSOES = (1080, 1920) if FORMATO == "9:16" else (1920, 1080)

async def gerar_audio():
    print("[1/4] Gerando narração com voz realista...")
    communicate = edge_tts.Communicate(ROTEIRO, VOZ)
    await communicate.save("narracao.mp3")

def buscar_video_fundo(query="nature background"):
    print("[2/4] Buscando vídeo de fundo no Pexels...")
    url = f"https://api.pexels.com/videos/search?query={query}&per_page=1&orientation={'portrait' if FORMATO == '9:16' else 'landscape'}"
    headers = {"Authorization":ad4jE5qOvBqxv2XdO3rQ5qnimXMPo5LMcN267k7YzOfd0W5WwZBPVXBJ}
    response = requests.get(url, headers=headers).json()
    
    if response.get('videos'):
        video_url = response['videos'][0]['video_files'][0]['link']
        r = requests.get(video_url)
        with open("fundo.mp4", "wb") as f:
            f.write(r.content)
        return "fundo.mp4"
    else:
        raise Exception("Nenhum vídeo encontrado no Pexels.")

def montar_video():
    print("[3/4] Montando o vídeo final...")
    audio = AudioFileClip("narracao.mp3")
    duracao_audio = audio.duration
    
    # Carrega vídeo de fundo e ajusta duração e tamanho
    fundo = VideoFileClip("fundo.mp4").subclip(0, min(duracao_audio, 10))
    if fundo.duration < duracao_audio:
        fundo = fundo.loop(duration=duracao_audio)
    else:
        fundo = fundo.subclip(0, duracao_audio)
        
    fundo = fundo.resize(newsize=DIMENSOES)
    fundo = fundo.set_audio(audio)
    
    # Adiciona legenda simples centralizada
    legenda = TextClip(ROTEIRO, fontsize=45, color='white', bg_color='black', 
                       method='caption', size=(DIMENSOES[0] - 100, None))
    legenda = legenda.set_position('center').set_duration(duracao_audio)
    
    video_final = CompositeVideoClip([fundo, legenda])
    
    print("[4/4] Renderizando MP4 final...")
    video_final.write_videofile("resultado.mp4", fps=24, codec="libx264", audio_codec="aac")

if __name__ == "__main__":
    asyncio.run(gerar_audio())
    buscar_video_fundo("technology abstract")
    montar_video()
