import logging

logger = logging.getLogger(__name__)


class LoggingMiddleware:
    """Middleware to log incoming updates before handlers run.

    Logs event type, chat_id, user_id, username for debugging.
    """
    async def __call__(self, handler, event, data):
        try:
            from aiogram.types import Message as AiMessage, CallbackQuery as AiCallback
            user_id = None
            username = None
            chat_id = None
            ev_type = type(event).__name__
            if isinstance(event, AiMessage):
                user = event.from_user
                user_id = getattr(user, 'id', None)
                username = getattr(user, 'username', None)
                chat_id = getattr(getattr(event, 'chat', None), 'id', None)
            elif isinstance(event, AiCallback):
                user = event.from_user
                user_id = getattr(user, 'id', None)
                username = getattr(user, 'username', None)
                msg = getattr(event, 'message', None)
                chat_id = getattr(getattr(msg, 'chat', None), 'id', None) if msg is not None else None
            else:
                # best-effort: try to inspect common attributes
                user = getattr(event, 'from_user', None)
                user_id = getattr(user, 'id', None) if user is not None else None
                username = getattr(user, 'username', None) if user is not None else None
                chat_id = getattr(getattr(event, 'chat', None), 'id', None) if getattr(event, 'chat', None) is not None else None

            logger.debug("Middleware incoming update type=%s chat_id=%s user_id=%s username=%s",
                         ev_type, chat_id, user_id, username)
        except Exception:
            logger.exception("LoggingMiddleware failed to introspect event")
        return await handler(event, data)