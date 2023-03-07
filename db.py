import enum
from datetime import datetime
from os import getenv
from uuid import UUID as pyUUID

from sqlalchemy import ForeignKey, Uuid, BigInteger, TIMESTAMP, Enum
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column, relationship
from sqlalchemy.schema import FetchedValue

SCHEMA = "public"


class ChannelEnum(enum.Enum):
    circles = 'circles'
    gossips = 'gossips'

    def __str__(self):
        return self.value


class Base(DeclarativeBase):
    # __abstract__ = True
    __table_args__ = {"schema": SCHEMA}


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(unique=True)
    first_name: Mapped[str]
    last_name: Mapped[str]
    bot: Mapped[bool] = mapped_column(nullable=False, default=False)
    instant_forward: Mapped[bool] = mapped_column(nullable=False, default=False)


class Message(Base):
    __tablename__ = "message"

    id: Mapped[pyUUID] = mapped_column(Uuid, primary_key=True, server_default=FetchedValue())
    message_id: Mapped[int] = mapped_column(BigInteger)
    channel_id: Mapped[int] = mapped_column(BigInteger)
    user_id: Mapped[BigInteger] = mapped_column(ForeignKey(f"{SCHEMA}.{User.__tablename__}.id"))
    timestamp: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=FetchedValue())

    user: Mapped[User] = relationship()


class InputMessage(Base):
    __tablename__ = "input_message"

    message_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[BigInteger] = mapped_column(ForeignKey(f"{SCHEMA}.{User.__tablename__}.id"))
    timestamp: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=FetchedValue())
    suggestion_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reply_message_id: Mapped[int] = mapped_column(BigInteger)
    channel: Mapped[ChannelEnum] = mapped_column(Enum(ChannelEnum, name="channel"))

    user: Mapped[User] = relationship()


engine = create_async_engine(
    getenv("DATABASE_URL"),
    echo=False
)
