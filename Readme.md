# Zoom Telegram Bot

This project is a Telegram bot designed for simplify Zoom Management. The bot provides various functionalities to support the Zoom Meeting's operations.

## Installation

1. Clone the repository:
    ```bash
    git clone https://github.com/rezytijo/Zoom-Telebot.git
    ```
2. Navigate to the project directory:
    ```bash
    cd Zoom-Telebot
    ```
3. Install the required dependencies:
    ```bash
    pip install --no-cache-dir -r requirements.txt
    ```

## Usage

### Python
1. Set up your environment variables:
    ```bash
    cp .env.example .env
    ```
    Edit the `.env` file to include your Telegram bot token and other necessary configurations.

2. Start the bot:
    ```bash
    python telegram_bot.py
    ```

### Docker Compose
```Docker Compose
services:
  autologin:
    image: rezytijo/zoom-telebot
    container_name: soc-bot
    restart: unless-stopped
    environment:
      - TZ=$TZ
      - TELEGRAM_API=$TELEGRAM_API
      - GEMINI_API=$GEMINI_API
      - ZOOM_ACCOUNT_ID=$ZOOM_ACCOUNT_ID
      - ZOOM_CLIENT_ID=$ZOOM_CLIENT_ID
      - ZOOM_CLIENT_SECRET=$ZOOM_CLIENT_SECRET
```

## Contributing

We welcome contributions!
