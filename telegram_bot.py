import os
import time
import locale
import pytz
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
import telebot
from google import genai
from zoomus import ZoomClient

# Load environment variables
if os.path.exists('.env'):
    load_dotenv()

# Retrieve environment variables with error handling
try:
    TELEGRAM_API = os.environ['TELEGRAM_API']
    GEMINI_API = os.environ['GEMINI_API']
    ZOOM_ACCOUNT_ID = os.environ['ZOOM_ACCOUNT_ID']
    ZOOM_CLIENT_ID = os.environ['ZOOM_CLIENT_ID']
    ZOOM_CLIENT_SECRET = os.environ['ZOOM_CLIENT_SECRET']
except KeyError as e:
    logging.error(f"Missing environment variable: {e}")
    exit(1)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', datefmt='%d-%B-%Y')

# Set locale for date formatting
locale.setlocale(locale.LC_ALL, 'id_ID.UTF-8')

# Initialize bot
bot = telebot.TeleBot(TELEGRAM_API)

def start_polling(bot):
    while True:
        try:
            logging.info("Bot Sedang Berjalan...!")
            bot.polling(none_stop=True)
        except Exception as e:
            logging.error(f"Error: {e}. Restarting...")
            time.sleep(1)

def format_greeting():
    hour = datetime.now().hour
    if 4 <= hour < 10:
        return "Selamat pagi"
    elif 10 <= hour < 15:
        return "Selamat siang"
    elif 15 <= hour < 19:
        return "Selamat sore"
    else:
        return "Selamat malam"

@bot.message_handler(commands=["start"])
def start(message):
    start_message = """
    *Selamat datang di BOT-SOC!*
    Berikut adalah daftar perintah yang didukung oleh bot:

    * /start: Mulai bot
    * /help: Menampilkan bantuan
    * /meet "Topic" "00 Bulan Tahun" "HH:MM" contoh /meet "Topic" "01 Januari 2024" "18:30"
    * /check_meeting: Menampilkan daftar meeting yang akan datang
    * /askGemini: Bertanya kepada AI Gemini
    """
    bot.reply_to(message, start_message, parse_mode='Markdown')
    logging.info(f"{message.from_user.username}: /start")

# @bot.message_handler(func=lambda message: message.text.endswith("?"))
# def answer_question(message):
#     Gemini = genai.Client(api_key=GEMINI_API)
#     question = message.text
#     response = Gemini.models.generate_content(model="gemini-2.0-flash", contents=question)
#     bot.reply_to(message, f"*Halo saya adalah asisten virtual*\nIni adalah hasil pencarian dari pertanyaan anda *{question}*\n{response.text}", parse_mode='Markdown')
#     logging.info(f"{message.from_user.username}: Question - {question}")

@bot.message_handler(commands=["help"])
def help(message):
    help_message = """
    Berikut adalah daftar perintah yang didukung oleh bot:

    * /start: Mulai bot
    * /help: Menampilkan bantuan
    * /meet "Topic" "00 Bulan Tahun" "HH:MM" contoh /meet "Topic" "01 Januari 2024" "18:30"
    * /check_meeting: Menampilkan daftar meeting yang akan datang
    * /askGemini: Bertanya kepada AI Gemini
    """
    bot.reply_to(message, help_message, parse_mode='Markdown')
    logging.info(f"{message.from_user.username}: /help")

@bot.message_handler(commands=["askGemini"])
def askGemini(message):
    Gemini = genai.Client(api_key=GEMINI_API)
    question = message.text
    response = Gemini.models.generate_content(model="gemini-2.0-flash", contents=question)
    response = response.text
    bot.reply_to(message, response, parse_mode='Markdown')
    logging.info(f"{message.from_user.username}: /askGemini - {question}")

@bot.message_handler(commands=['meet'])
def meet(message):
    args = message.text.split('"')[1::2]
    if len(args) != 3:
        bot.reply_to(message, "Format perintah salah. Gunakan: /meet \"Topic Meeting\" \"Tanggal\" \"Waktu\"")
        logging.warning(f"{message.from_user.username}: /meet - Format perintah salah")
        return

    topic, date_str, time_str = args
    try:
        date = datetime.strptime(date_str, "%d %B %Y")
        time = datetime.strptime(time_str, "%H:%M")
    except ValueError:
        bot.reply_to(message, "Format tanggal atau waktu salah. Gunakan: /meet \"Topic Meeting\" \"Tanggal\" \"Waktu\"")
        logging.warning(f"{message.from_user.username}: /meet - Format tanggal atau waktu salah")
        return

    start_time = date.replace(hour=time.hour, minute=time.minute)
    jakarta = pytz.timezone('Asia/Jakarta')
    start_time = jakarta.localize(start_time).astimezone(pytz.UTC)
    end_time = start_time + timedelta(minutes=120)

    client = ZoomClient(ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET, ZOOM_ACCOUNT_ID)
    meetings = client.meeting.list(user_id='me').json()['meetings']

    for meeting in meetings:
        meeting_start_time = datetime.strptime(meeting['start_time'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC)
        meeting_end_time = meeting_start_time + timedelta(minutes=meeting['duration'])
        if (start_time <= meeting_start_time < end_time) or (start_time < meeting_end_time <= end_time):
            bot.reply_to(message, f"Pada waktu tersebut terdapat meeting lain dengan Topic: {meeting['topic']}")
            logging.info(f"{message.from_user.username}: /meet - Bentrok dengan meeting lain")
            return

    meeting = client.meeting.create(topic=topic, start_time=start_time, user_id='me', duration=120, default_password='true')
    meeting_info = meeting.json()
    formatted_date = date.strftime("%A, %d %B %Y")
    greeting = format_greeting()
    bot.reply_to(message, f'{greeting} Bapak/Ibu/Rekan - Rekan\nBerikut disampaikan {topic} pada:\n\n📆  {formatted_date}\n⏰  {time_str} WIB – selesai\n🔗  {meeting_info["join_url"]}\n\nDemikian disampaikan, terimakasih.')
    logging.info(f"{message.from_user.username}: /meet - {topic} pada {formatted_date} {time_str}")

@bot.message_handler(commands=["check_meeting"])
def check_meeting(message):
    client = ZoomClient(ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET, ZOOM_ACCOUNT_ID)
    meetings = client.meeting.list(user_id='me').json()['meetings']
    now_utc = datetime.now(pytz.UTC)
    upcoming_meetings = []

    for meeting in meetings:
        meeting_start_time = datetime.strptime(meeting['start_time'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC)
        if meeting_start_time > now_utc:
            formatted_start_time = meeting_start_time.astimezone(pytz.timezone('Asia/Jakarta')).strftime("%A, %d %B %Y %H:%M WIB")
            upcoming_meetings.append(f"{meeting['topic']} pada {formatted_start_time}")

    if upcoming_meetings:
        bot.reply_to(message, f"*Berikut adalah daftar meeting yang akan datang:*\n\n" + "\n".join(upcoming_meetings), parse_mode='Markdown')
    else:
        bot.reply_to(message, "Tidak ada meeting yang akan datang", parse_mode='Markdown')
    logging.info(f"{message.from_user.username}: /check_meeting")

@bot.message_handler(content_types=["text"])
def echo(message):
    unknown = "Maaf Perintah anda tidak diketahui"
    bot.reply_to(message, unknown)
    logging.warning(f"{message.from_user.username}: Unknown command - {message.text}")

if __name__ == "__main__":
    print("Script Sedang Berjalan")
    start_polling(bot)
