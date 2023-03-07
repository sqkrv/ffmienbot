import logging
from os import getenv
from typing import Optional

import telegram
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import async_sessionmaker
from telegram import Message as tgMessage
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, \
    ConversationHandler
from telegram.ext import filters

from db import User, Message, InputMessage, engine
from db import enum, ChannelEnum


@enum.unique
class DataConsts(enum.Enum):
    SUGGESTION_IN_WORK = 1
    INSTANT_FORWARD = 2


class ForumThread:
    POST_SUGGESTIONS = 178
    POST_SENT = 166
    GOSSIP_SUGGESTIONS = 301


POST_MESSAGE, GOSSIP_MESSAGE = range(2)

ADMIN_CHAT_ID = getenv("ADMIN_CHAT_ID")
CIRCLES_CHANNEL_ID = getenv("CIRCLES_CHANNEL_ID")
CIRCLES_DISCUSSION_CHAT_ID = getenv("CIRCLES_DISCUSSION_CHAT_ID")
GOSSIPS_CHANNEL_ID = getenv("GOSSIPS_CHANNEL_ID")
ENV = getenv("ENV")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO if ENV == 'dev' else logging.WARNING
)

logging.debug(' '.join([ADMIN_CHAT_ID, CIRCLES_CHANNEL_ID, CIRCLES_DISCUSSION_CHAT_ID, GOSSIPS_CHANNEL_ID]))


class FfmienBot:
    def __init__(
            self,
            bot_token: str,
    ):
        self._bot_token: str = bot_token
        Session = async_sessionmaker(bind=engine)
        self.session = Session()

    def _author_info(self, author: telegram.User, db_user: Optional[User] = None,
                     instant_forward_user: Optional[bool] = None):
        return f"Автор: {author.mention_markdown_v2()}" \
               f"\nМоментальная отправка: {('Да' if db_user.instant_forward else 'Нет') if db_user else ('Да' if instant_forward_user else 'Нет')}"

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Приветствую в боте ФФМиЕН\!"
            "\n\nНа данный момент данный бот предназначен для предложения "
            "постов в сеть телеграм\-каналов физмата\. Вы можете предложить пост "
            "в круги физмата, а можете предложить сплетни в "
            "[физматовские сплетни](https://t\.me/spletniffmien) 😉\."
            "\n\nДля помощи наберите /help\.",
            parse_mode=telegram.constants.ParseMode.MARKDOWN_V2
        )

        user = update.effective_user

        # async with AsyncSession(engine) as session:
        if await self.session.scalar(select(func.count()).select_from(User).filter_by(id=user.id)):
            return

        db_user = User(
            id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            bot=user.is_bot
        )
        self.session.add(db_user)
        try:
            await self.session.commit()
        finally:
            await self.session.rollback()

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "• /help — показать данной сообщение"
            "\n• /suggest\_post — предложить пост в КРУГИ НА ФИЗМАТЕ"
            "\n• /suggest\_gossip — предложить пост в [физматовские сплетни](https://t\.me/spletniffmien)"
            "\n\n||Данный бот является полностью неофициальным и никак "
            "не связан с РУДН и его руководством\."
            "\nПо всем вопросам и предложениям обращайтесь к @sqkrv||",
            parse_mode=telegram.constants.ParseMode.MARKDOWN_V2
        )

    async def suggest_post(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Отправьте (или перешлите) Ваш пост. Это может быть \"кружок\", фото, видео или текст.")
        return POST_MESSAGE

    async def suggest_gossip(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Отправьте Ваш материал на сплетню. Это может быть \"кружок\", фото, видео, текст или аудиосообщение.")
        return GOSSIP_MESSAGE

    async def cancel_conversation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Отменил процедуру")
        return ConversationHandler.END

    async def dont_suggest_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        response_message = query.message

        await response_message.edit_text(text="Предложение отменено", reply_markup=None)
        await query.answer("Предложение отменено")

    async def gossip_dmed(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [[InlineKeyboardButton("✅ Отправить", callback_data=f"suggestion-send-{ChannelEnum.gossips}"),
                     InlineKeyboardButton("❌ Отменить", callback_data=f"dont-suggest")]]
        await update.message.reply_text("Отправить на рассмотрение?", quote=True,
                                        reply_markup=InlineKeyboardMarkup(keyboard))

        return ConversationHandler.END

    async def circles_post_dmed(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # async with AsyncSession(engine) as session:
        db_user: User = await self.session.scalar(select(User).filter_by(id=update.effective_user.id))

        if db_user.instant_forward:
            keyboard = [[InlineKeyboardButton("✅ Отправить", callback_data="instant-send-post")]]
            await update.message.reply_text("Отправить?", quote=True, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            keyboard = [[InlineKeyboardButton("✅ Отправить", callback_data=f"suggestion-send-{ChannelEnum.circles}"),
                         InlineKeyboardButton("❌ Отменить", callback_data=f"dont-suggest")]]
            await update.message.reply_text("Отправить на рассмотрение?", quote=True,
                                            reply_markup=InlineKeyboardMarkup(keyboard))

        return ConversationHandler.END

    async def suggest_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if context.user_data.get(DataConsts.SUGGESTION_IN_WORK, None):
            return
        context.user_data[DataConsts.SUGGESTION_IN_WORK] = True
        try:
            query = update.callback_query
            message_type = ChannelEnum.gossips if query.data.endswith(str(ChannelEnum.gossips)) else ChannelEnum.circles
            message = query.message.reply_to_message
            author = message.from_user

            db_input_message: InputMessage = await self.session.scalar(
                select(InputMessage).filter_by(message_id=message.id))
            if db_input_message:
                await query.answer("Данное сообщение уже было предложено")
                return

            keyboard = [[InlineKeyboardButton("✅ Одобрить", callback_data="approve-suggestion"),
                         InlineKeyboardButton("❌ Отказать", callback_data="reject-suggestion")]]
            message_in_suggestions = await message.forward(
                ADMIN_CHAT_ID,
                message_thread_id=ForumThread.GOSSIP_SUGGESTIONS if message_type == ChannelEnum.gossips else ForumThread.POST_SUGGESTIONS
            )
            await message_in_suggestions.reply_text(
                self._author_info(author, instant_forward_user=False),
                reply_markup=InlineKeyboardMarkup(keyboard),
                message_thread_id=ForumThread.GOSSIP_SUGGESTIONS if message_type == ChannelEnum.gossips else ForumThread.POST_SUGGESTIONS,
                parse_mode=telegram.constants.ParseMode.MARKDOWN_V2
            )
            await query.edit_message_text("Отправлено в предложку", reply_markup=None)
            await query.answer("Отправлено в предложку")

            self.session.add(InputMessage(
                message_id=message.id,
                user_id=author.id,
                suggestion_message_id=message_in_suggestions.id,
                reply_message_id=query.message.id,
                channel=message_type
            ))
            try:
                await self.session.commit()
            finally:
                await self.session.rollback()
        finally:
            context.user_data[DataConsts.SUGGESTION_IN_WORK] = False

    # async def suggestion_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    #     pass

    async def instant_post_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        message = query.message.reply_to_message
        author = message.from_user
        db_user: User = await self.session.scalar(select(User).filter_by(id=update.effective_user.id))

        if db_user.instant_forward:
            channel_message = await message.forward(CIRCLES_CHANNEL_ID)
            await self._duplicate_post_to_topic(message, author, db_user)

            # async with AsyncSession(engine) as session:
            db_message = Message(
                message_id=channel_message.id,
                channel_id=channel_message.chat_id,
                user_id=author.id
            )
            self.session.add(db_message)
            try:
                await self.session.commit()
            finally:
                await self.session.rollback()

            keyboard = [[InlineKeyboardButton("Удалить нахуй блять", callback_data="delete")]]  # todo deletion of posted message
            await query.edit_message_text(f"Пост отправлен в канал\n{channel_message.link}", reply_markup=None)
            await query.answer("Отправлено")
            return
        else:
            await query.answer("Вам недоступен данный функционал")
            pass

    async def _duplicate_post_to_topic(self, message: telegram.Message, author: telegram.User, db_user: User):
        admin_chat_message = await message.forward(ADMIN_CHAT_ID, message_thread_id=ForumThread.POST_SENT)
        return await admin_chat_message.reply_text(self._author_info(author, db_user),
                                                   message_thread_id=ForumThread.POST_SENT, quote=True,
                                                   parse_mode=telegram.constants.ParseMode.MARKDOWN_V2)

    async def handle_suggestion_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        message_in_chat = query.message.reply_to_message
        og_message_author = message_in_chat.forward_from

        input_message: InputMessage = await self.session.scalar(
            select(InputMessage).filter_by(suggestion_message_id=message_in_chat.id))
        db_user: User = await self.session.scalar(select(User).filter_by(id=update.effective_user.id))

        callback_by_user = f"by {query.from_user.mention_markdown_v2()}"

        async def forward(chat_id: int | str):
            chat_id = int(chat_id)
            if input_message.channel == ChannelEnum.circles:
                channel_message: telegram.Message = await context.bot.forward_message(chat_id=chat_id,
                                                                                      from_chat_id=ADMIN_CHAT_ID,
                                                                                      message_id=input_message.suggestion_message_id)
                await self._duplicate_post_to_topic(message_in_chat, og_message_author, db_user)
            else:
                channel_message: telegram.MessageId = await context.bot.copy_message(chat_id=chat_id,
                                                                                     from_chat_id=ADMIN_CHAT_ID,
                                                                                     message_id=input_message.suggestion_message_id)
            self.session.add(Message(message_id=channel_message.message_id, channel_id=chat_id, user_id=input_message.user_id))
            # await self.session.commit()
            post_link = f"[Ссылка на пост](" + (channel_message.link if isinstance(channel_message,
                                                                                   telegram.Message) else f"https://t.me/c/{str(chat_id)[4:]}/{channel_message.message_id}") + ')'
            await query.message.edit_text(f"Одобрено {callback_by_user}\n{post_link}", parse_mode=telegram.constants.ParseMode.MARKDOWN_V2)
            await context.bot.send_message(
                chat_id=input_message.user_id,
                text=f"Ваш пост был одобрен\n{post_link}",
                reply_to_message_id=input_message.message_id,
                parse_mode=telegram.constants.ParseMode.MARKDOWN_V2
            )
            try:
                await self.session.commit()
            finally:
                await self.session.rollback()
            return

        if query.data == "approve-suggestion":
            if input_message.channel == ChannelEnum.gossips:
                await forward(GOSSIPS_CHANNEL_ID)
            else:
                await forward(CIRCLES_CHANNEL_ID)
            await query.answer("Пост был успешно отправлен")
        elif query.data == "reject-suggestion":
            await query.message.edit_text(f"Отклонено {callback_by_user}", parse_mode=telegram.constants.ParseMode.MARKDOWN_V2)
            await context.bot.send_message(chat_id=input_message.user_id, text="Пост был отклонен", reply_to_message_id=input_message.message_id)
            await query.answer("Уведомление об отклонении было отправлено")

    # async def discussion_chat_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    #     logging.debug(update.message)
    #     db_message: Message = await self.session.scalar(select(Message).filter_by(message_id=update.message.id, channel_id=update.message.sender_chat.id))
    #     if db_message:
    #         await update.message.reply_text("тут инфа об авторе")

    # async def forward_video_note(self, context: ContextTypes.DEFAULT_TYPE, author, video_note_message: tgMessage,
    #                              db_user: Optional[User] = None, instant_forward_user: Optional[bool] = None, ):
    #     channel_message = await video_note_message.forward(CIRCLES_CHANNEL_ID)
    #     admin_chat_message = await video_note_message.forward(ADMIN_CHAT_ID)
    #     await admin_chat_message.reply_text(self._author_info(author, db_user, instant_forward_user),
    #                                         message_thread_id=ForumThread.POST_SENT, quote=True,
    #                                         parse_mode=telegram.constants.ParseMode.MARKDOWN_V2)
    #
    #     # async with AsyncSession(engine) as session:
    #     db_message = Message(
    #         message_id=channel_message.id,
    #         channel_id=channel_message.chat_id,
    #         user_id=author.id
    #     )
    #     self.session.add(db_message)
    #     try:
    #         await self.session.commit()
    #     finally:
    #         await self.session.rollback()
    #
    #     return channel_message

    post_filters = filters.VIDEO_NOTE | filters.PHOTO | filters.VIDEO | filters.TEXT

    def run(self):
        application = ApplicationBuilder().token(self._bot_token).build()

        application.add_handler(CommandHandler('start', self.start))
        application.add_handler(CommandHandler('help', self.help_command))
        # application.add_handler(MessageHandler(filters.VIDEO_NOTE & filters.ChatType.PRIVATE, video_note_dmed))
        application.add_handler(CallbackQueryHandler(self.instant_post_callback, pattern="instant-send-post"))
        application.add_handler(CallbackQueryHandler(self.suggest_callback,
                                                     pattern=rf"suggestion-send-({ChannelEnum.circles}|{ChannelEnum.gossips})"))
        application.add_handler(CallbackQueryHandler(self.dont_suggest_callback, pattern="dont-suggest"))
        # application.add_handler(CallbackQueryHandler(suggestion_cancel_callback, pattern="suggestion-cancel"))
        application.add_handler(CallbackQueryHandler(self.handle_suggestion_callback, pattern="approve-suggestion"))
        application.add_handler(CallbackQueryHandler(self.handle_suggestion_callback, pattern="reject-suggestion"))
        # application.add_handler(MessageHandler(filters.Chat(CIRCLES_DISCUSSION_CHAT_ID) & filters.IS_AUTOMATIC_FORWARD, discussion_chat_message))

        post_suggestion_handler = ConversationHandler(
            entry_points=[CommandHandler("suggest_post", self.suggest_post)],
            states={
                POST_MESSAGE: [
                    MessageHandler(self.post_filters & filters.ChatType.PRIVATE & ~filters.COMMAND,
                                   self.circles_post_dmed)]
            },
            fallbacks=[CommandHandler("cancel", self.cancel_conversation)],
        )
        application.add_handler(post_suggestion_handler)

        gossip_suggestion_handler = ConversationHandler(
            entry_points=[CommandHandler("suggest_gossip", self.suggest_gossip)],
            states={
                GOSSIP_MESSAGE: [
                    MessageHandler((self.post_filters | filters.VOICE) & filters.ChatType.PRIVATE & ~filters.COMMAND,
                                   self.gossip_dmed)]
            },
            fallbacks=[CommandHandler("cancel", self.cancel_conversation)],
        )
        application.add_handler(gossip_suggestion_handler)

        logging.info("Starting the bot")
        application.run_polling()
