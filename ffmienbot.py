import asyncio
import os
from os import getenv
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram import Message as tgMessage
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, ConversationHandler
from telegram.ext import filters
import telegram
import logging
from db import enum, ChannelEnum

from db import User, Message, InputMessage, engine, select, func, async_sessionmaker

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)


@enum.unique
class DataConsts(enum.Enum):
    SUGGESTION_IN_WORK = 1
    INSTANT_FORWARD = 2


class ForumThread:
    POST_SUGGESTIONS = 178
    POST_SENT = 166
    GOSSIP_SUGGESTIONS = 301


POST_MESSAGE, GOSSIP_MESSAGE = range(2)

ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
CIRCLES_CHANNEL_ID = os.getenv("CIRCLES_CHANNEL_ID")
CIRCLES_DISCUSSION_CHAT_ID = os.getenv("CIRCLES_DISCUSSION_CHAT_ID")
GOSSIPS_CHANNEL_ID = os.getenv("GOSSIPS_CHANNEL_ID")

logging.debug(' '.join([ADMIN_CHAT_ID, CIRCLES_CHANNEL_ID, CIRCLES_DISCUSSION_CHAT_ID, GOSSIPS_CHANNEL_ID]))

Session = async_sessionmaker(bind=engine)
session = Session()


def author_info(author: telegram.User, db_user: Optional[User] = None, instant_forward_user: Optional[bool] = None):
    return f"Автор: {author.mention_markdown_v2()}" \
           f"\nМоментальная отправка: {('Да' if db_user.instant_forward else 'Нет') if db_user else ('Да' if instant_forward_user else 'Нет')}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Приветствую в боте ФФМиЕН!"
        "\n\nДанный бот предназначен пока что только для кругов а вообще нет, не только"
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
        "\n• /asd \<запрос\> — "
        "\n\n||Данный бот является полностью неофициальным и никак"
        "не связан с РУДН."
        "\nПо всем претензиям, вопросам и предложениям обращайтесь ||",  # todo feedback channel
        parse_mode=telegram.constants.ParseMode.MARKDOWN_V2
    )


async def suggest_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("валяй пост в круги")
    return POST_MESSAGE


async def suggest_gossip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("валяй сплетню")
    return GOSSIP_MESSAGE


async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("отменил")
    return ConversationHandler.END


async def dont_suggest_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    response_message = query.message

    await response_message.edit_text(text="Предложение отменено", reply_markup=None)
    await query.answer("Предложение отменено")


async def gossip_dmed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("✅ Отправить", callback_data=f"suggestion-send-{ChannelEnum.gossips}"), InlineKeyboardButton("❌ Отменить", callback_data=f"dont-suggest")]]
    await update.message.reply_text("Отправить на рассмотрение?", quote=True, reply_markup=InlineKeyboardMarkup(keyboard))

    return ConversationHandler.END


async def circles_post_dmed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # async with AsyncSession(engine) as session:
    db_user: User = await session.scalar(select(User).filter_by(id=update.effective_user.id))

    if db_user.instant_forward:
        keyboard = [[InlineKeyboardButton("✅ Отправить", callback_data="instant-send")]]
        await update.message.reply_text("Отправить?", quote=True, reply_markup=InlineKeyboardMarkup(keyboard))

        # channel_message = await forward_video_note(update.effective_user, update.message, db_user)
        # keyboard = [[InlineKeyboardButton("Удалить нахуй", callback_data="delete")]]
        # await update.message.reply_text(f"Отправлено! {channel_message.link}", quote=True, reply_markup=InlineKeyboardMarkup(keyboard))
        # return
    else:
        keyboard = [[InlineKeyboardButton("✅ Отправить", callback_data=f"suggestion-send-{ChannelEnum.circles}"), InlineKeyboardButton("❌ Отменить", callback_data=f"dont-suggest")]]
        await update.message.reply_text("Отправить на рассмотрение?", quote=True, reply_markup=InlineKeyboardMarkup(keyboard))

    return ConversationHandler.END


async def suggest_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get(DataConsts.SUGGESTION_IN_WORK, None):
        return
    context.user_data[DataConsts.SUGGESTION_IN_WORK] = True
    try:
        query = update.callback_query
        message_type = ChannelEnum.gossips if query.data.endswith(str(ChannelEnum.gossips)) else ChannelEnum.circles
        message = query.message.reply_to_message
        author = message.from_user

        db_input_message: InputMessage = await session.scalar(select(InputMessage).filter_by(message_id=message.id))
        if db_input_message:
            await query.answer("Данное сообщение уже было предложено")
            return

        keyboard = [[InlineKeyboardButton("✅ Одобрить", callback_data="approve-suggestion"), InlineKeyboardButton("❌ Отказать", callback_data="reject-suggestion")]]
        message_in_suggestions = await message.forward(
            ADMIN_CHAT_ID,
            message_thread_id=ForumThread.GOSSIP_SUGGESTIONS if message_type == ChannelEnum.gossips else ForumThread.POST_SUGGESTIONS
        )
        await message_in_suggestions.reply_text(
            author_info(author, instant_forward_user=False),
            reply_markup=InlineKeyboardMarkup(keyboard),
            message_thread_id=ForumThread.GOSSIP_SUGGESTIONS if message_type == ChannelEnum.gossips else ForumThread.POST_SUGGESTIONS,
            parse_mode=telegram.constants.ParseMode.MARKDOWN_V2
        )
        await query.edit_message_text("Отправлено в предложку", reply_markup=None)
        await query.answer("Отправлено в предложку")

        session.add(InputMessage(
            message_id=message.id,
            user_id=author.id,
            suggestion_message_id=message_in_suggestions.id,
            reply_message_id=query.message.id,
            channel=message_type
        ))
        await session.commit()
    finally:
        context.user_data[DataConsts.SUGGESTION_IN_WORK] = False


# async def suggestion_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     pass


async def instant_post_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    video_note = query.message.reply_to_message
    author = video_note.from_user
    db_user: User = await session.scalar(select(User).filter_by(id=update.effective_user.id))

    if db_user.instant_forward:
        channel_message = await forward_video_note(context, author, video_note, instant_forward_user=False)

        keyboard = [[InlineKeyboardButton("Удалить нахуй блять", callback_data="delete")]]  # todo
        await query.edit_message_text(f"Отправлено!\n{channel_message.link}", reply_markup=None)
        await query.answer("Отправлено")
        return
    else:
        # await
        pass


async def handle_suggestion_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    message = query.message.reply_to_message
    callback_user = query.from_user

    input_message: InputMessage = await session.scalar(select(InputMessage).filter_by(suggestion_message_id=message.id))

    async def forward(chat_id: int | str):
        chat_id = int(chat_id)
        if input_message.channel == ChannelEnum.circles:
            channel_message: telegram.Message = await context.bot.forward_message(chat_id=chat_id, from_chat_id=ADMIN_CHAT_ID,
                                                                message_id=input_message.suggestion_message_id)
        else:
            channel_message: telegram.MessageId = await context.bot.copy_message(chat_id=chat_id, from_chat_id=ADMIN_CHAT_ID, message_id=input_message.suggestion_message_id)
        session.add(
            Message(message_id=channel_message.message_id, channel_id=chat_id, user_id=input_message.user_id))
        # await session.commit()
        post_link = f"[Ссылка на пост](" + (channel_message.link if isinstance(channel_message, telegram.Message) else f"https://t.me/c/{str(chat_id)[4:]}/{channel_message.message_id}") + ')'
        await query.message.edit_text(f"Одобрено {callback_user.mention_markdown_v2()}\n{post_link}",
                                      parse_mode=telegram.constants.ParseMode.MARKDOWN_V2)
        await context.bot.send_message(
            chat_id=input_message.user_id,
            text=f"Ваш пост был одобрен\n{post_link}",
            reply_to_message_id=input_message.message_id,
            parse_mode=telegram.constants.ParseMode.MARKDOWN_V2
        )
        await session.commit()
        # for msg in discussion_messages:
        #     if msg
        # await context.bot.edit_message_text(text="", chat_id=input_message.user_id, message_id=input_message.reply_message_id)
        return

    if query.data == "approve-suggestion":
        if input_message.channel == ChannelEnum.gossips:
            return await forward(GOSSIPS_CHANNEL_ID)
        else:
            return await forward(CIRCLES_CHANNEL_ID)
    elif query.data == "reject-suggestion":
        await query.message.edit_text("Отклонено")
        await context.bot.send_message(chat_id=input_message.user_id, text="Отклонено", reply_to_message_id=input_message.message_id)
        return


# async def discussion_chat_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     logging.debug(update.message)
#     db_message: Message = await session.scalar(select(Message).filter_by(message_id=update.message.id, channel_id=update.message.sender_chat.id))
#     if db_message:
#         await update.message.reply_text("тут инфа об авторе")


async def forward_video_note(context: ContextTypes.DEFAULT_TYPE, author, video_note_message: tgMessage, db_user: Optional[User] = None, instant_forward_user: Optional[bool] = None, ):
    channel_message = await video_note_message.forward(CIRCLES_CHANNEL_ID)
    admin_chat_message = await video_note_message.forward(ADMIN_CHAT_ID)
    await admin_chat_message.reply_text(author_info(author, db_user, instant_forward_user), message_thread_id=ForumThread.POST_SENT, quote=True, parse_mode=telegram.constants.ParseMode.MARKDOWN_V2)
    # async for message in await context.bot.get_chat(channel_message.chat.linked_chat_id)
    # async for message in (await context.bot.get_chat(DISCUSSION_CHAT_ID)):  # todo how to send comments

    # await context.bot.send_message()
    # await admin_chat_message.reply_text(
    #     f"Автор: {author.mention_markdown_v2()}"
    #     f"\nМоментальная отправка: {('Да' if db_user.instant_forward else 'Нет') if db_user else ('Да' if instant_forward_user else 'Нет')}",
    #     message_thread_id=PForum, quote=True, parse_mode=telegram.constants.ParseMode.MARKDOWN_V2)
    # async with AsyncSession(engine) as session:
    db_message = Message(
        message_id=channel_message.id,
        channel_id=channel_message.chat_id,
        user_id=author.id
    )
    session.add(db_message)
    await session.commit()

    return channel_message


post_filters = filters.VIDEO_NOTE | filters.PHOTO | filters.VIDEO | filters.TEXT


def main():
    application = ApplicationBuilder().token(getenv("BOT_TOKEN")).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help_command))
    # application.add_handler(MessageHandler(filters.VIDEO_NOTE & filters.ChatType.PRIVATE, video_note_dmed))
    application.add_handler(CallbackQueryHandler(instant_post_callback, pattern="instant-send"))
    application.add_handler(CallbackQueryHandler(suggest_callback, pattern=rf"suggestion-send-({ChannelEnum.circles}|{ChannelEnum.gossips})"))
    application.add_handler(CallbackQueryHandler(dont_suggest_callback, pattern="dont-suggest"))
    # application.add_handler(CallbackQueryHandler(suggestion_cancel_callback, pattern="suggestion-cancel"))
    application.add_handler(CallbackQueryHandler(handle_suggestion_callback, pattern="approve-suggestion"))
    application.add_handler(CallbackQueryHandler(handle_suggestion_callback, pattern="reject-suggestion"))
    # application.add_handler(MessageHandler(filters.Chat(CIRCLES_DISCUSSION_CHAT_ID) & filters.IS_AUTOMATIC_FORWARD, discussion_chat_message))

    post_suggestion_handler = ConversationHandler(
        entry_points=[CommandHandler("suggest_post", suggest_post)],
        states={
            POST_MESSAGE: [MessageHandler(post_filters & filters.ChatType.PRIVATE & ~filters.COMMAND, circles_post_dmed)]
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
    )
    application.add_handler(post_suggestion_handler)

    gossip_suggestion_handler = ConversationHandler(
        entry_points=[CommandHandler("suggest_gossip", suggest_gossip)],
        states={
            GOSSIP_MESSAGE: [MessageHandler((post_filters | filters.VOICE) & filters.ChatType.PRIVATE & ~filters.COMMAND, gossip_dmed)]
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
    )
    application.add_handler(gossip_suggestion_handler)

    logging.info("Starting the bot")
    application.run_polling()


if __name__ == '__main__':
    main()
