import os
import asyncio
import yt_dlp
import re
import threading
import time
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.error import Conflict

# --- CONFIGURAÇÕES DO BOT ---
TOKEN = "8662880668:AAGv9KsQlDOyOdd3JvEUrpLsGKp7tUDaY1k"
DOWNLOAD_DIR = "downloads_tg"
COOKIES_FILE = "cookies.txt"

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# --- SERVIDOR WEB FAKE (Para manter o Render vivo) ---
app = Flask(__name__)
@app.route('/')
def home(): return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_flask, daemon=True).start()

# --- LÓGICA DE DOWNLOAD ---

def get_ydl_opts(file_id, mode, url):
    output_template = os.path.join(DOWNLOAD_DIR, f"{file_id}.%(ext)s")
    opts = {
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'socket_timeout': 30,
        'retries': 10,
    }
    
    if os.path.exists(COOKIES_FILE):
        opts['cookiefile'] = COOKIES_FILE
    
    if mode == 'audio':
        opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
        })
    else:
        opts['format'] = 'bestvideo+bestaudio/best'
    
    return opts

# --- HANDLERS DO TELEGRAM ---

async def set_commands(application: Application):
    commands = [BotCommand("start", "Iniciar o bot")]
    await application.bot.set_my_commands(commands)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Olá Mestre! Envie um link do YouTube, Instagram ou TikTok e eu baixo para você!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not re.match(r'https?://', url): return
    
    context.user_data['current_url'] = url
    keyboard = [[InlineKeyboardButton("🎬 Vídeo (MP4)", callback_data='video'),
                 InlineKeyboardButton("🎵 Áudio (MP3)", callback_data='audio')]]
    await update.message.reply_text("O que você deseja baixar?", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'new_download':
        await query.message.reply_text("Envie o novo link, mestre!")
        return

    mode = query.data
    url = context.user_data.get('current_url')
    if not url:
        await query.edit_message_text("Erro: Link expirado. Envie novamente.")
        return
        
    status_msg = await query.edit_message_text(f"⏳ Baixando {mode}... Isso pode levar um minuto.")
    
    try:
        file_id = f"{query.from_user.id}_{int(time.time())}"
        ydl_opts = get_ydl_opts(file_id, mode, url)
            
        def run_ydl():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info)

        file_path = await asyncio.get_event_loop().run_in_executor(None, run_ydl)
        if mode == 'audio': file_path = os.path.splitext(file_path)[0] + ".mp3"
        
        if not os.path.exists(file_path):
            base = os.path.splitext(file_path)[0]
            for ext in ['.mp4', '.mkv', '.webm', '.3gp', '.mp3']:
                if os.path.exists(base + ext):
                    file_path = base + ext
                    break
            
        await status_msg.edit_text("✅ Download concluído! Enviando...")
        
        with open(file_path, 'rb') as f:
            if mode == 'video':
                await query.message.reply_video(video=f, caption="Aqui está!")
            else:
                await query.message.reply_audio(audio=f, caption="Aqui está!")
        
        if os.path.exists(file_path): os.remove(file_path)
        await status_msg.delete()
        
    except Exception as e:
        error_msg = str(e)
        if "Sign in to confirm you're not a bot" in error_msg:
            await status_msg.edit_text("❌ O YouTube bloqueou o acesso temporariamente. Tente novamente em alguns minutos.")
        else:
            await status_msg.edit_text(f"❌ Erro: {error_msg[:100]}")

def main():
    while True:
        try:
            application = Application.builder().token(TOKEN).build()
            application.add_handler(CommandHandler("start", start))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
            application.add_handler(CallbackQueryHandler(button_handler))
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(set_commands(application))
            
            print("Bot Iniciado...")
            application.run_polling(drop_pending_updates=True)
        except Conflict:
            print("Conflito detectado! Reiniciando em 10 segundos...")
            time.sleep(10)
        except Exception as e:
            print(f"Erro fatal: {e}")
            time.sleep(5)

if __name__ == '__main__':
    main()
