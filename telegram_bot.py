import telebot, os, time, locale, json, pytz, logging
from google import genai
from zoomus import ZoomClient
from datetime import datetime, timedelta
from dotenv import load_dotenv

if os.path.exists('.env'):
    load_dotenv()

TELEGRAM_API = os.environ['TELEGRAM_API']
GEMINI_API = os.environ['GEMINI_API']
ZOOM_ACCOUNT_ID = os.environ['ZOOM_ACCOUNT_ID']
ZOOM_CLIENT_ID = os.environ['ZOOM_CLIENT_ID']
ZOOM_CLIENT_SECRET = os.environ['ZOOM_CLIENT_SECRET']

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', datefmt='%d-%B-%Y')

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
            logging.info("Bot Sedang Berjalan...!")
            bot.polling(none_stop=True)

        except Exception as e:
            logging.error(f"Error: {e}. Restarting...")
            # Tunggu selama 1 detik sebelum melakukan restart untuk menghindari restart yang terlalu cepat
            time.sleep(1)

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
    * /meet "Topic" "00 Bulan Tahun" "HH:MM" contoh /meet "Topic" "01 Januari 2024" "18:30"
    * /check_meeting: Menampilkan daftar meeting yang akan datang
    """
    bot.reply_to(message, start_message)
    logging.info(f"{message.from_user.username}: /start")

@bot.message_handler(func=lambda message: message.text.endswith("?"))
def answer_question(message):
    Gemini = genai.Client(api_key=GEMINI_API)
    question = message.text
    response = Gemini.models.generate_content(model="gemini-2.0-flash", contents=question)
    bot.reply_to(message, "*Halo saya adalah asisten virtual* \nIni adalah hasil pencarian dari pertanyaan anda *"+question+"*\n"+response.text, parse_mode='Markdown')
    logging.info(f"{message.from_user.username}: Question - {question}")

@bot.message_handler(commands=["help"])
def help(message):
    help_message = """
    Berikut adalah daftar perintah yang didukung oleh bot:

    * /start: Mulai bot
    * /help: Menampilkan bantuan
    * /meet "Topic" "00 Bulan Tahun" "HH:MM" contoh /meet "Topic" "01 Januari 2024" "18:30"
    * /check_meeting: Menampilkan daftar meeting yang akan datang
    """
    bot.reply_to(message, help_message)
    logging.info(f"{message.from_user.username}: /help")

@bot.message_handler(commands=["askGemini"])
def askGemini(message):
    Gemini = genai.Client(api_key=GEMINI_API)
    question = message.text
    response = Gemini.models.generate_content(model="gemini-2.0-flash", contents=question)
    bot.reply_to(message, response.text, parse_mode='Markdown')
    logging.info(f"{message.from_user.username}: /askGemini - {question}")

# Mendefinisikan perintah /meet
@bot.message_handler(commands=['meet'])
def meet(message):
    # Memisahkan argumen dari pesan
    args = message.text.split('"')[1::2]

    # Mengecek apakah jumlah argumen benar
    if len(args) != 3:
        bot.reply_to(message, "Format perintah salah. Gunakan: /meet \"Topic Meeting\" \"Tanggal\" \"Waktu\"")
        logging.warning(f"{message.from_user.username}: /meet - Format perintah salah")
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
    existing_duration = 120  # Set duration to 120 minutes
    existing_end_time = start_time + timedelta(minutes=existing_duration)

    # Buat instance ZoomClient
    client = ZoomClient(ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET, ZOOM_ACCOUNT_ID)
    
    # Mendapatkan daftar meeting yang sudah ada
    meetings = client.meeting.list(user_id='me').json()['meetings']

    # Mengecek apakah ada meeting lain pada waktu yang sama
    for meeting in meetings:
        meeting_start_time = datetime.strptime(meeting['start_time'], "%Y-%m-%dT%H:%M:%SZ")
        meeting_start_time = pytz.UTC.localize(meeting_start_time)
        meeting_end_time = meeting_start_time + timedelta(minutes=meeting['duration'])
        
        # Mengecek apakah waktu mulai atau waktu selesai bentrok dengan meeting yang ada
        if (start_time <= meeting_start_time < existing_end_time) or (start_time < meeting_end_time <= existing_end_time):
            bot.reply_to(message, f"Pada waktu tersebut terdapat meeting lain dengan Topic: {meeting['topic']}")
            logging.info(f"{message.from_user.username}: /meet - Bentrok dengan meeting lain")
            return
        
    # Membuat meeting dengan judul dan waktu yang diinginkan
    meeting = client.meeting.create(topic=topic, start_time=start_time, user_id='me', duration=120, default_password='true')

    # Mendapatkan informasi meeting seperti id, password, dan join_url
    meeting_id = meeting.json()['id']
    meeting_join_url = meeting.json()['join_url']

    # Mencetak informasi meeting dengan format baru
    formatted_date = date.strftime("%A, %d %B %Y")
    hour = now.hour
    if 4 <= hour < 10:
        waktu = "Selamat pagi"
    elif 10 <= hour < 15:
        waktu = "Selamat siang"
    elif 15 <= hour < 19:
        waktu = "Selamat sore"
    else:
        waktu = "Selamat malam"
    bot.reply_to(message, f'{waktu} Bapak/Ibu/Rekan - Rekan\nBerikut disampaikan {topic} pada:\n\n📆  {formatted_date}\n⏰  {time_str} WIB – selesai\n🔗  {meeting_join_url}\n\nDemikian disampaikan, terimakasih.')
    logging.info(f"{message.from_user.username}: /meet - {topic} pada {formatted_date} {time_str}")

@bot.message_handler(commands=["check_meeting"])
def check_meeting(message):
    # Buat instance ZoomClient
    client = ZoomClient(ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET, ZOOM_ACCOUNT_ID)
    
    # Mendapatkan daftar meeting yang sudah ada
    meetings = client.meeting.list(user_id='me').json()['meetings']
    
    # Mendapatkan waktu saat ini dalam UTC
    now_utc = datetime.now(pytz.UTC)
    
    # Mengecek apakah ada meeting yang akan datang
    upcoming_meetings = []
    for meeting in meetings:
        meeting_start_time = datetime.strptime(meeting['start_time'], "%Y-%m-%dT%H:%M:%SZ")
        meeting_start_time = pytz.UTC.localize(meeting_start_time)
        
        # Menambahkan hanya meeting yang akan datang ke dalam daftar
        if meeting_start_time > now_utc:
            formatted_start_time = meeting_start_time.astimezone(pytz.timezone('Asia/Jakarta')).strftime("%A, %d %B %Y %H:%M WIB")
            upcoming_meetings.append(f"{meeting['topic']} pada {formatted_start_time}")
        
    # Mengecek apakah ada meeting yang akan datang
    if len(upcoming_meetings) > 0:
        bot.reply_to(message, f"*Berikut adalah daftar meeting yang akan datang:*\n\n" + "\n".join(upcoming_meetings), parse_mode='Markdown')
    else:
        bot.reply_to(message, "Tidak ada meeting yang akan datang", parse_mode='Markdown')
    logging.info(f"{message.from_user.username}: /check_meeting")

@bot.message_handler(content_types=["text"])
def echo(message):
    uknown = "Maaf Perintah anda tidak diketahui"
    bot.reply_to(message, uknown)
    logging.warning(f"{message.from_user.username}: Unknown command - {message.text}")

print("Script Sedang Berjalan")
bot.polling()
# start_polling(bot)
