from os import getenv

from dotenv import load_dotenv

if __name__ == '__main__':
    load_dotenv()
    from ffmienbot import FfmienBot

    ffmienbot = FfmienBot(getenv("BOT_TOKEN"))
    ffmienbot.run()
