import os
import asyncio
import yt_dlp
import re
import threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# --- CONFIGURAÇÕES DO BOT ---
TOKEN = "8662880668:AAGv9KsQlDOyOdd3JvEUrpLsGKp7tUDaY1k"
DOWNLOAD_DIR = "downloads_tg"
COOKIES_FILE = "cookies.txt"

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

def get_ydl_opts(file_id, mode, url):
    output_template = os.path.join(DOWNLOAD_DIR, f"{file_id}.%(ext)s")
    opts = {
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    
    if os.path.exists(COOKIES_FILE):
        opts['cookiefile'] = COOKIES_FILE
    
    if mode == 'audio':
        opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
        })
    else:
        if "youtube.com" in url or "youtu.be" in url:
            # Força a melhor qualidade de vídeo e áudio, preferindo MP4 para compatibilidade no Telegram
            opts['format'] = 'bestvideo+bestaudio/best'
            # Se o Telegram tiver dificuldade com MKV/WebM, o ffmpeg converterá se necessário, 
            # mas o 'best' costuma pegar 1080p ou superior.
        else:
            opts['format'] = 'bestvideo+bestaudio/best'
    
    return opts

# --- HANDLERS DO TELEGRAM ---

async def set_commands(application: Application):
    """Configura o menu de comandos (os três risquinhos)."""
    commands = [
        BotCommand("start", "Iniciar o bot"),
    ]
    await application.bot.set_my_commands(commands)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Olá Mestre! Eu sou seu bot de downloads.\n\n"
        "Me envie um link do TikTok, Instagram, YouTube ou Facebook e eu baixarei para você!"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not re.match(r'https?://', url):
        return
    
    context.user_data['current_url'] = url
    keyboard = [
        [
            InlineKeyboardButton("Vídeo (MP4)", callback_data='video'),
            InlineKeyboardButton("Áudio (MP3)", callback_data='audio'),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("O que você deseja baixar?", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'new_download':
        await query.message.reply_text("Certo, mestre! Me envie o novo link.")
        return

    mode = query.data
    url = context.user_data.get('current_url')
    if not url:
        await query.edit_message_text("Erro: Link não encontrado. Envie o link novamente.")
        return
        
    status_msg = await query.edit_message_text(f"Iniciando download do {mode}... aguarde.")
    
    try:
        file_id = f"{query.from_user.id}_{int(asyncio.get_event_loop().time())}"
        ydl_opts = get_ydl_opts(file_id, mode, url)
            
        loop = asyncio.get_event_loop()
        def run_ydl():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info)

        file_path = await loop.run_in_executor(None, run_ydl)
        
        if mode == 'audio':
            file_path = os.path.splitext(file_path)[0] + ".mp3"
        
        # Garantia de encontrar o arquivo caso a extensão mude
        if not os.path.exists(file_path):
            base = os.path.splitext(file_path)[0]
            for ext in ['.mp4', '.mkv', '.webm', '.3gp', '.mp3']:
                if os.path.exists(base + ext):
                    file_path = base + ext
                    break
            
        await status_msg.edit_text("Download concluído! Enviando arquivo...")
        
        with open(file_path, 'rb') as f:
            if mode == 'video':
                await query.message.reply_video(video=f, caption="Aqui está seu vídeo, mestre!")
            else:
                await query.message.reply_audio(audio=f, caption="Aqui está seu áudio, mestre!")
        
        if os.path.exists(file_path):
            os.remove(file_path)
        await status_msg.delete()
        
        keyboard = [[InlineKeyboardButton("🔄 Baixar outro", callback_data='new_download')]]
        await query.message.reply_text("Deseja baixar mais alguma coisa?", reply_markup=InlineKeyboardMarkup(keyboard))
        
    except Exception as e:
        print(f"Erro: {e}")
        await status_msg.edit_text("Ocorreu um erro ao processar esse link. Verifique se o link é válido.")

def main():
    application = Application.builder().token(TOKEN).build()
    
    # Configura o menu de comandos ao iniciar
    loop = asyncio.get_event_loop()
    loop.run_until_complete(set_commands(application))
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    print("Bot Normal Mode Iniciado...")
    application.run_polling()

if __name__ == '__main__':
    main()
