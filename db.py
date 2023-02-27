import asyncio
from os import getenv
from typing import List, Optional
from uuid import uuid4
from uuid import UUID as pyUUID
from datetime import date, datetime
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Integer, String, ForeignKey, SmallInteger, CHAR, Uuid, Date, select, BigInteger, func
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column, relationship
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

SCHEMA = "public"


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

    id: Mapped[pyUUID] = mapped_column(Uuid, primary_key=True, insert_default=uuid4)
    message_id: Mapped[int] = mapped_column(BigInteger)
    channel_id: Mapped[int] = mapped_column(BigInteger)
    user_id: Mapped[BigInteger] = mapped_column(ForeignKey(f"{SCHEMA}.{User.__tablename__}.id"))

    user: Mapped[User] = relationship()


engine = create_async_engine(
        getenv("DATABASE_URL"),
        echo=True,
    )
