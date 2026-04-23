import os
import asyncio
import yt_dlp
import re
import threading
import time
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# --- CONFIGURAÇÕES DO BOT ---
TOKEN = "8662880668:AAGv9KsQlDOyOdd3JvEUrpLsGKp7tUDaY1k"
DOWNLOAD_DIR = "downloads_tg"
COOKIES_FILE = "cookies.txt" # Opcional: Caminho para arquivo de cookies se necessário

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# --- SERVIDOR WEB FAKE ---
app = Flask(__name__)
@app.route('/')
def home(): return "Bot is running 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_flask, daemon=True).start()

# --- LÓGICA DE DOWNLOAD ---

def get_ydl_opts(file_id, mode):
    output_template = os.path.join(DOWNLOAD_DIR, f"{file_id}_{mode}.%(ext)s")
    opts = {
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    
    # Se houver um arquivo de cookies, utiliza para evitar bloqueios do Instagram
    if os.path.exists(COOKIES_FILE):
        opts['cookiefile'] = COOKIES_FILE
    
    if mode == 'audio':
        opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
        })
    else:
        # Tenta baixar o melhor vídeo com áudio embutido ou combina os melhores
        opts['format'] = 'bestvideo+bestaudio/best'
    
    return opts

async def download_task(url, file_id, mode):
    """Executa o download de um formato específico."""
    opts = get_ydl_opts(file_id, mode)
    loop = asyncio.get_event_loop()
    
    def run_ydl():
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info)

    try:
        path = await loop.run_in_executor(None, run_ydl)
        if mode == 'audio':
            # O postprocessor do yt-dlp altera a extensão para .mp3
            path = os.path.splitext(path)[0] + ".mp3"
        return path
    except Exception as e:
        print(f"Erro no download {mode}: {e}")
        return None

# --- HANDLERS DO TELEGRAM ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Olá Mestre! Envie um link do Instagram, TikTok ou YouTube.\n\n"
        "Minha nova tecnologia baixa o vídeo e o áudio ao mesmo tempo assim que você manda o link. "
        "É só clicar e receber na hora! ⚡"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not re.match(r'https?://', url):
        return

    file_id = f"{update.effective_user.id}_{int(time.time())}"
    status_msg = await update.message.reply_text("🚀 Link recebido! Preparando seus arquivos (MP4 e MP3)...")

    # Inicia os downloads em segundo plano (Paralelo)
    task_video = asyncio.create_task(download_task(url, file_id, 'video'))
    task_audio = asyncio.create_task(download_task(url, file_id, 'audio'))

    # Armazena as tasks no context do usuário usando o file_id como chave
    context.user_data[file_id] = {
        'video_task': task_video,
        'audio_task': task_audio,
        'url': url
    }

    keyboard = [
        [
            InlineKeyboardButton("🎬 Vídeo (MP4)", callback_data=f"dl:video:{file_id}"),
            InlineKeyboardButton("🎵 Áudio (MP3)", callback_data=f"dl:audio:{file_id}"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await status_msg.edit_text("Escolha o formato desejado:", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data.split(':')
    if data[0] == 'new_download':
        await query.message.reply_text("Certo! Me envie o novo link.")
        return
    
    if data[0] != 'dl':
        return

    mode = data[1]
    file_id = data[2]
    
    user_job = context.user_data.get(file_id)
    if not user_job:
        await query.edit_message_text("Erro: Sessão expirada ou link antigo. Envie o link novamente.")
        return

    # Se a task ainda estiver rodando, avisa o usuário
    task = user_job['video_task'] if mode == 'video' else user_job['audio_task']
    if not task.done():
        await query.edit_message_text(f"⏳ Quase lá! O {mode} está terminando de baixar...")
    
    # Aguarda a conclusão (se já terminou, retorna imediatamente)
    file_path = await task

    if file_path and os.path.exists(file_path):
        await query.edit_message_text(f"✅ {mode.capitalize()} pronto! Enviando...")
        
        try:
            with open(file_path, 'rb') as f:
                if mode == 'video':
                    await query.message.reply_video(video=f, caption="Aqui está seu vídeo, mestre!")
                else:
                    await query.message.reply_audio(audio=f, caption="Aqui está seu áudio, mestre!")
            
            # Limpa o arquivo após o envio
            os.remove(file_path)
        except Exception as e:
            await query.message.reply_text(f"Erro ao enviar o arquivo: {e}")
    else:
        await query.edit_message_text("❌ Desculpe, não consegui baixar esse formato. O link pode estar protegido ou instável.")

    # Botão para novo download
    keyboard = [[InlineKeyboardButton("🔄 Baixar outro", callback_data='new_download')]]
    await query.message.reply_text("Deseja baixar mais alguma coisa?", reply_markup=InlineKeyboardMarkup(keyboard))

def main():
    print("Bot Ultra Fast Iniciado...")
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.run_polling()

if __name__ == '__main__':
    main()
