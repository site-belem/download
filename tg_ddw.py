import os
import asyncio
import yt_dlp
import re
import threading
import time
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.error import Conflict, TimedOut, NetworkError

# --- CONFIGURAÇÕES DO BOT ---
TOKEN = "8662880668:AAGv9KsQlDOyOdd3JvEUrpLsGKp7tUDaY1k"
DOWNLOAD_DIR = "downloads_tg"
COOKIES_FILE = "cookies.txt"

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# --- SERVIDOR WEB FAKE ---
app = Flask(__name__)
@app.route('/')
def home(): return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_flask, daemon=True).start()

# --- LÓGICA DE DOWNLOAD ---

def clean_url(url):
    """Limpa parâmetros de rastreamento do Instagram que causam timeout."""
    if "instagram.com" in url:
        url = url.split('?')[0]
        if not url.endswith('/'):
            url += '/'
    return url

def get_ydl_opts(file_id, mode, url):
    output_template = os.path.join(DOWNLOAD_DIR, f"{file_id}.%(ext)s")
    user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
    
    opts = {
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'user_agent': user_agent,
        'socket_timeout': 120, # Aumentado para evitar timeouts em conexões lentas
        'retries': 15,
        'fragment_retries': 15,
        'extractor_args': {'youtube': {'player_client': ['web', 'mweb', 'tv', 'ios']}},
    }
    
    if os.path.exists(COOKIES_FILE):
        opts['cookiefile'] = COOKIES_FILE
    
    if mode == 'audio':
        opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
        })
    else:
        # Prioriza formatos que já são mp4 para evitar conversões lentas no servidor
        opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
    
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
    
    url = clean_url(url)
    context.user_data['current_url'] = url
    
    keyboard = [[InlineKeyboardButton("🎬 Vídeo (MP4)", callback_data='video'),
                 InlineKeyboardButton("🎵 Áudio (MP3)", callback_data='audio')]]
    await update.message.reply_text("O que você deseja baixar?", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'new_download':
        await query.message.reply_text("Certo, mestre! Me envie o novo link.")
        return

    mode = query.data
    url = context.user_data.get('current_url')
    if not url:
        await query.edit_message_text("Erro: Link expirado. Envie novamente.")
        return
        
    status_msg = await query.edit_message_text(f"⏳ Baixando {mode}... Isso pode levar um tempo dependendo do tamanho.")
    
    file_path = None
    try:
        file_id = f"{query.from_user.id}_{int(time.time())}"
        ydl_opts = get_ydl_opts(file_id, mode, url)
            
        def run_ydl():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info)

        # Download do arquivo
        file_path = await asyncio.get_event_loop().run_in_executor(None, run_ydl)
        
        # Ajuste de extensão para áudio
        if mode == 'audio':
            base = os.path.splitext(file_path)[0]
            if os.path.exists(base + ".mp3"):
                file_path = base + ".mp3"
        
        # Verificação robusta do arquivo
        if not os.path.exists(file_path):
            base = os.path.splitext(file_path)[0]
            for ext in ['.mp4', '.mkv', '.webm', '.3gp', '.mp3', '.m4a']:
                if os.path.exists(base + ext):
                    file_path = base + ext
                    break
        
        if not os.path.exists(file_path):
            raise Exception("Arquivo não encontrado após o download.")
            
        await status_msg.edit_text("✅ Download concluído! Enviando para o Telegram... (Aguarde)")
        
        # Envio do arquivo com tratamento de timeout específico do Telegram
        max_retries = 3
        for attempt in range(max_retries):
            try:
                with open(file_path, 'rb') as f:
                    if mode == 'video':
                        await query.message.reply_video(
                            video=f, 
                            caption="Aqui está seu vídeo!",
                            read_timeout=300, 
                            write_timeout=300, 
                            connect_timeout=300, 
                            pool_timeout=300
                        )
                    else:
                        await query.message.reply_audio(
                            audio=f, 
                            caption="Aqui está seu áudio!",
                            read_timeout=300, 
                            write_timeout=300, 
                            connect_timeout=300, 
                            pool_timeout=300
                        )
                break # Sucesso no envio
            except (TimedOut, NetworkError) as te:
                if attempt == max_retries - 1:
                    raise te
                await asyncio.sleep(5) # Espera um pouco antes de tentar reenviar
        
        await status_msg.delete()
        
    except Exception as e:
        error_msg = str(e).lower()
        print(f"Erro no processamento: {e}")
        
        if "sign in to confirm you're not a bot" in error_msg:
            await status_msg.edit_text("❌ O YouTube bloqueou o IP do servidor. Tente novamente mais tarde.")
        elif "timeout" in error_msg or "timed out" in error_msg:
            await status_msg.edit_text("❌ O envio demorou demais, mas o arquivo pode ter sido enviado. Verifique seu chat.")
        else:
            # Só exibe erro de download se o arquivo realmente não existir
            if file_path and os.path.exists(file_path):
                await status_msg.edit_text(f"❌ Erro ao enviar o arquivo para o Telegram.")
            else:
                await status_msg.edit_text(f"❌ Erro ao baixar o arquivo.")
    
    finally:
        # Limpeza do arquivo
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass

    # Garante que o botão "Baixar outro" apareça sempre no final
    keyboard = [[InlineKeyboardButton("🔄 Baixar outro", callback_data='new_download')]]
    await query.message.reply_text("Deseja baixar mais alguma coisa?", reply_markup=InlineKeyboardMarkup(keyboard))

def main():
    while True:
        try:
            # Aumentar o timeout do Application para lidar com uploads longos
            application = Application.builder().token(TOKEN).read_timeout(300).write_timeout(300).build()
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
