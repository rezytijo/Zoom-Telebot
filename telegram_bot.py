import telebot, os, time, locale, json, pytz
from bardapi import Bard
from zoomus import ZoomClient
from datetime import datetime
import bardapi
import requests
import subprocess
from dotenv import load_dotenv

if.os.path.exists('/.env'):
    load_dotenv()

TELEGRAM_API = os.environ['TELEGRAM_API']
BARD_API = os.environ['BARD_API']
ZOOM_ACCOUNT_ID = os.environ['ZOOM_ACCOUNT_ID']
ZOOM_CLIENT_ID = os.environ['ZOOM_CLIENT_ID']
ZOOM_CLIENT_SECRET = os.environ['ZOOM_CLIENT_SECRET']


# Get the current date and time
locale.setlocale(locale.LC_ALL,'id_ID.UTF-8')
now = datetime.now()
# Format the date and time
folder_time = now.strftime("%d-%B-%Y")
file_time = now.strftime("%d %B %Y")


# Membuat Bot Restart Otomatis
def start_polling(bot):
    while True:
        try:
            print(f"Bot Sedang Berjalan...!")
            bot.polling(none_stop=True)

        except Exception as e:
            print(f"Error: {e}. Restarting...")
            # Tunggu selama 1 detik sebelum melakukan restart untuk menghindari restart yang terlalu cepat
            time.sleep(1)

# Deklarasikan fungsi untuk menjalankan file Python "run.py"
def run_file():
    # Jalankan file Python
    subprocess.run("python","run.py")

# Bot Token

bot = telebot.TeleBot(TELEGRAM_API)

# ##########################################################################
#                         COMMAND LIST BOT
# ##########################################################################

@bot.message_handler(commands=["start"])
def start(message):
    start_message = """
    *Selamat datang di BOT-SOC!*
    Berikut adalah daftar perintah yang didukung oleh bot:

    * /start: Mulai bot
    * /help: Menampilkan bantuan
    * /report [tanggal]: Mengunduh File Laporan (belum jadi, masih mikir mau ngambil dari mana datanya)
    * /meet "Topic" "00 Bulan Tahun" "HH:MM" contoh /meet "Topic" "01 Januari 2024" "18:30"
    """
    bot.reply_to(message, start_message)

@bot.message_handler(commands=["report"])
def daily(message):
    file_path = "./Picture/"+folder_time+"/Daily Report Kamsiber Kominfo Periode "+file_time+".pdf"
    caption = "Ini Laporan Periode "+file_time
    bot.send_document(message, open(file_path, "rb"), caption=caption)

@bot.message_handler(func=lambda message: message.text.endswith("?"))
def answer_question(message):
    bard = Bard(token=BARD_API)
    question = message.text
    response = bard.get_answer(question)['content']
    bot.reply_to(message, "*Halo saya adalah asisten virtual* \nIni adalah hasil pencarian dari pertanyaan anda *"+question+"*\n"+response, parse_mode='Markdown')

@bot.message_handler(commands=["help"])
def help(message):
    help_message = """
    Berikut adalah daftar perintah yang didukung oleh bot:

    * /start: Mulai bot
    * /help: Menampilkan bantuan
    * /report [tanggal]: Mengunduh File Laporan (belum jadi, masih mikir mau ngambil dari mana datanya)
    * /meet "Topic" "00 Bulan Tahun" "HH:MM" contoh /meet "Topic" "01 Januari 2024" "18:30"
    """

    bot.reply_to(message, help_message)

@bot.message_handler(commands=["askBard"])
def askBard(message):
    bard = Bard(token=BARD_API)
    question = message.text
    response = bard.get_answer(question)['content']
    bot.reply_to(message, "*Halo saya adalah asisten virtual* \nIni adalah hasil pencarian dari pertanyaan anda *"+question+"*\n"+response, parse_mode='Markdown')

# Mendefinisikan perintah /meet
@bot.message_handler(commands=['meet'])
def meet(message):
    # Memisahkan argumen dari pesan
    args = message.text.split('"')[1::2]

    # Mengecek apakah jumlah argumen benar
    if len(args) != 3:
        bot.reply_to(message, "Format perintah salah. Gunakan: /meet \"Topic Meeting\" \"Tanggal\" \"Waktu\"")
        return

    # Mengambil argumen
    topic, date_str, time_str = args

    # Mengubah string tanggal dan waktu menjadi objek datetime
    date = datetime.strptime(date_str, "%d %B %Y")
    time = datetime.strptime(time_str, "%H:%M")
    start_time = date.replace(hour=time.hour, minute=time.minute)

    # Mengubah zona waktu menjadi WIB
    jakarta = pytz.timezone('Asia/Jakarta')
    start_time = jakarta.localize(start_time)

    # Mengubah zona waktu menjadi UTC
    start_time = start_time.astimezone(pytz.UTC)
    
    # Buat instance ZoomClient
    client = ZoomClient(ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET, ZOOM_ACCOUNT_ID)
    
    # Membuat meeting dengan judul dan waktu yang diinginkan
    meeting = client.meeting.create(topic=topic, start_time=start_time, user_id='me', duration=120, default_password='true')

    # Mendapatkan informasi meeting seperti id, password, dan join_url
    meeting_id = meeting.json()['id']
    meeting_join_url = meeting.json()['join_url']

    # Mencetak informasi meeting dengan format baru
    formatted_date = date.strftime("%A, %d %B %Y")
    bot.reply_to(message, f'Selamat pagi Bapak/Ibu/Rekan - Rekan\nBerikut disampaikan {topic} pada:\n\n📆  {formatted_date}\n⏰  {time_str} WIB – selesai\n🔗  {meeting_join_url}\n\nDemikian disampaikan, terimakasih.')

@bot.message_handler(content_types=["text"])
def echo(message):
    uknown = "Maaf Perintah anda tidak diketahui"
    bot.reply_to(message, uknown)

print("Script Sedang Berjalan")
bot.polling()
# start_polling(bot)
