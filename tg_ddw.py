import os
import asyncio
import yt_dlp
import re
import threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# --- CONFIGURAÇÕES DO BOT ---
TOKEN = "8662880668:AAGv9KsQlDOyOdd3JvEUrpLsGKp7tUDaY1k"
DOWNLOAD_DIR = "downloads_tg"

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# --- SERVIDOR WEB FAKE COM FLASK PARA O RENDER ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# Inicia o Flask em uma thread separada para não travar o bot
threading.Thread(target=run_flask, daemon=True).start()
# -------------------------------------------------

def clean_filename(name):
    clean = re.sub(r'[^a-zA-Z0-9@_]', '_', name)
    return clean[:30]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Olá Mestre! Eu sou seu bot de downloads.\n\nMe envie um link do TikTok, Instagram, YouTube ou Facebook e eu baixarei para você!"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if not re.match(r'http', url):
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
    mode = query.data
    url = context.user_data.get('current_url')
    if not url:
        await query.edit_message_text("Erro: Link não encontrado. Envie o link novamente.")
        return
    status_msg = await query.edit_message_text(f"Iniciando download do {mode}... aguarde.")
    try:
        file_id = f"{query.from_user.id}_{int(asyncio.get_event_loop().time())}"
        output_template = os.path.join(DOWNLOAD_DIR, f"{file_id}.%(ext)s")
        ydl_opts = {
            'outtmpl': output_template,
            'quiet': True,
            'no_warnings': True,
        }
        if mode == 'audio':
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
            })
        else:
            ydl_opts['format'] = 'best'
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=True))
        file_path = yt_dlp.YoutubeDL(ydl_opts).prepare_filename(info)
        if mode == 'audio':
            file_path = os.path.splitext(file_path)[0] + ".mp3"
        await status_msg.edit_text("Download concluído! Enviando arquivo...")
        with open(file_path, 'rb') as f:
            if mode == 'video':
                await query.message.reply_video(video=f, caption="Aqui está seu vídeo, mestre!")
            else:
                await query.message.reply_audio(audio=f, caption="Aqui está seu áudio, mestre!")
        os.remove(file_path)
        await status_msg.delete()
    except Exception as e:
        print(f"Erro: {e}")
        await status_msg.edit_text("Ocorreu um erro ao processar esse link. Verifique se o link é válido.")

def main():
    print("Bot iniciado...")
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.run_polling()

if __name__ == '__main__':
    main()
