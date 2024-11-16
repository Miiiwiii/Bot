from importlib import import_module
from highrise.__main__ import *
import time
import traceback

# BOT SETTINGS #
bot_file_name = "musicbot"
bot_class_name = "xenoichi"
room_id = "6734a2767752b4b0c66f796a"
#6734a2767752b4b0c66f796a #OG ROOM
#65c56b54ac42f2f98821e501 #HANGMAN
bot_token = "5befe10e60c41182eb4718c03093445e3d92fe674d1a107a2f21b4b478d5557d"

my_bot = BotDefinition(getattr(import_module(bot_file_name), bot_class_name)(), room_id, bot_token)

while True:
    try:
        definitions = [my_bot]
        arun(main(definitions))
    except Exception as e:
        print(f"An exception occurred: {e}")
        traceback.print_exc()
        time.sleep(5)
