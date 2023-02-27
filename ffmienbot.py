import os
from os import getenv
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram import Message as tgMessage
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler
from telegram.ext import filters
import telegram
import logging

from db import User, Message, engine, select, func, async_sessionmaker

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)


CHANNEL_ID = os.getenv("CHANNEL_ID")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

Session = async_sessionmaker(bind=engine)
session = Session()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Приветствую в боте ФФМиЕН!"
        "\n\nДанный бот предназначен пока что только для кругов"
        "\n\nДля помощи наберите /help."
    )

    user = update.effective_user

    # async with AsyncSession(engine) as session:
    if await session.scalar(select(func.count()).select_from(User).filter_by(id=user.id)):
        return

    db_user = User(
        id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        bot=user.is_bot
    )
    session.add(db_user)
    await session.commit()


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "• /help — показать данной сообщение"
        "\n• /asd <запрос> — "
        "\n\n||Данный бот является полностью неофициальным и никак"
        "не связан с РУДН."
        "\nПо всем претензиям, вопросам и предложениям обращайтесь ||",  # todo feedback channel
        parse_mode=telegram.constants.ParseMode.MARKDOWN_V2
    )


async def video_note_dmed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # async with AsyncSession(engine) as session:
    db_user: User = await session.scalar(select(User).filter_by(id=update.effective_user.id))

    if db_user.instant_forward:
        await forward_video_note(update.effective_user, update.message, db_user)
        await update.message.reply_text("отправлено!", quote=True)
        return
    else:
        keyboard = [[InlineKeyboardButton("Отправить", callback_data="send")]]
        await update.message.reply_text("класс дебил!", quote=True, reply_markup=InlineKeyboardMarkup(keyboard))


async def forward_video_note_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    video_note = query.message.reply_to_message
    author = video_note.from_user
    # await video_note.reply_text("оно?", quote=True)
    # channel = await context.bot.get_chat(CHANNEL_ID)
    await forward_video_note(author, video_note, instant_forward_user=False)


async def forward_video_note(author, video_note_message: tgMessage, db_user: Optional[User] = None, instant_forward_user: Optional[bool] = None):
    channel_message = await video_note_message.forward(CHANNEL_ID)
    admin_chat_message = await video_note_message.forward(ADMIN_CHAT_ID)
    await admin_chat_message.reply_text(
        f"Автор: {author.mention_markdown_v2()}"
        f"\nМоментальная отправка: {('Да' if db_user.instant_forward else 'Нет') if db_user else ('Да' if instant_forward_user else 'Нет')}",
        quote=True, parse_mode=telegram.constants.ParseMode.MARKDOWN_V2)
    # async with AsyncSession(engine) as session:
    db_message = Message(
        message_id=channel_message.id,
        channel_id=channel_message.chat_id,
        user_id=author.id
    )
    session.add(db_message)
    await session.commit()


def main():
    application = ApplicationBuilder().token(getenv("BOT_TOKEN")).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(MessageHandler(filters.VIDEO_NOTE & filters.ChatType.PRIVATE, video_note_dmed))
    application.add_handler(CallbackQueryHandler(forward_video_note_callback, pattern="send"))

    logging.info("Starting the bot")
    application.run_polling()


if __name__ == '__main__':
    main()
