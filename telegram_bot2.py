from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, filters, CallbackContext

# Path ke file whitelist
WHITELIST_FILE = 'whitelist.txt'
PASSWORD = '123456'

def load_whitelist():
    try:
        with open(WHITELIST_FILE, 'r') as file:
            return set(line.strip() for line in file)
    except FileNotFoundError:
        return set()

def save_whitelist(whitelist):
    with open(WHITELIST_FILE, 'w') as file:
        for user_id in whitelist:
            file.write(f"{user_id}\n")

def start(update: Update, context: CallbackContext) -> None:
    user_id = str(update.message.from_user.id)
    whitelist = load_whitelist()

    if user_id in whitelist:
        update.message.reply_text('Anda sudah di-whitelist.')
    else:
        update.message.reply_text('Masukkan sandi untuk mengakses bot:')

def handle_message(update: Update, context: CallbackContext) -> None:
    user_id = str(update.message.from_user.id)
    whitelist = load_whitelist()

    if user_id not in whitelist:
        if update.message.text == PASSWORD:
            whitelist.add(user_id)
            save_whitelist(whitelist)
            update.message.reply_text('Sandi benar. Anda telah di-whitelist.')
        else:
            update.message.reply_text('Sandi salah. Coba lagi.')

def main():
    updater = Updater("1999673703:AAEcfnCOY8nM7HZ3oLyxdnmhoALisHi_A9E")
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()