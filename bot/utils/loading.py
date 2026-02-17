import asyncio
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Default loading text
DEFAULT_LOADING_TEXT = "⏳ Processing..."

async def send_loading_message(
    message: Message, 
    text: str = DEFAULT_LOADING_TEXT, 
    reply: bool = True
) -> Optional[Message]:
    """
    Send a loading message.
    
    Args:
        message (Message): The original message from the user.
        text (str): The loading text to display.
        reply (bool): Whether to reply to the original message or send a new one.
        
    Returns:
        Message: The sent loading message object, or None if failed.
    """
    try:
        if reply:
            return await message.reply(text)
        else:
            return await message.answer(text)
    except Exception as e:
        logger.warning(f"Failed to send loading message: {e}")
        return None

async def edit_loading_message(
    loading_msg: Message, 
    text: str
) -> bool:
    """
    Edit an existing loading message.
    
    Args:
        loading_msg (Message): The message object to edit.
        text (str): The new text content.
        
    Returns:
        bool: True if successful, False otherwise.
    """
    try:
        if loading_msg:
            await loading_msg.edit_text(text)
            return True
        return False
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            return True # Ignore if same content
        logger.warning(f"Failed to edit loading message: {e}")
        return False
    except Exception as e:
        logger.warning(f"Failed to edit loading message: {e}")
        return False

async def delete_loading_message(
    loading_msg: Optional[Message]
) -> bool:
    """
    Delete the loading message found.
    
    Args:
        loading_msg (Message): The message object to delete.
        
    Returns:
        bool: True if successful, False otherwise.
    """
    if not loading_msg:
        return False
        
    try:
        await loading_msg.delete()
        return True
    except Exception as e:
        logger.warning(f"Failed to delete loading message: {e}")
        return False

class LoadingContext:
    """
    Context manager for handling loading messages automatically.
    
    Usage:
        async with LoadingContext(message, "⏳ Uploading...") as loading:
            await upload_file()
            # Loading message is automatically deleted on exit
            
        async with LoadingContext(message, "⏳ Working...") as loading:
            await step1()
            await loading.update("⏳ Still working...")
            await step2()
    """
    def __init__(self, message: Message, text: str = DEFAULT_LOADING_TEXT, reply: bool = True):
        self.original_message = message
        self.text = text
        self.reply = reply
        self.loading_msg: Optional[Message] = None
        
    async def __aenter__(self):
        self.loading_msg = await send_loading_message(
            self.original_message, 
            self.text, 
            self.reply
        )
        return self

    async def update(self, new_text: str):
        if self.loading_msg:
            await edit_loading_message(self.loading_msg, new_text)

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await delete_loading_message(self.loading_msg)
