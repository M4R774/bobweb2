#!/usr/bin/env python
import asyncio
import logging
import os
import re
import sys
import random

import pytz
import requests
import datetime
from zoneinfo import ZoneInfo

import telegram.error
from asgiref.sync import sync_to_async
from telegram import Update
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext

import scheduler

sys.path.append('../web')  # needed for sibling import
import django

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "web.settings"
)

django.setup()
from bobapp.models import Chat, TelegramUser, ChatMember, Bob, GitUser
import rules_of_acquisition

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

logger = logging.getLogger(__name__)
ranks = []


def message_handler(update: Update, context=None):
    del context
    update_chat_in_db(update)
    update_user_in_db(update)

    if update.message is not None and update.message.text is not None:
        if update.message.reply_to_message is not None:
            reply_handler(update)
        elif update.message.text == "1337":
            leet_command(update)
        elif update.message.text.startswith((".", "/", "!")):
            command_handler(update)
        elif re.search(r'..*\s.vai\s..*', update.message.text) is not None:
            or_command(update)
        elif update.message.text.lower() == "huutista":
            update.message.reply_text('...joka tuutista! 😂')
        else:
            low_probability_reply(update)


def command_handler(update):
    incoming_message_text = update.message.text
    chat = Chat.objects.get(id=update.effective_chat.id)

    is_ruoka_command = (incoming_message_text[1:] == "ruoka")
    is_space_command = (incoming_message_text[1:] == "space")
    is_user_command = (incoming_message_text[1:] == "käyttäjät")
    is_kuulutus_command = incoming_message_text[1:].startswith("kuulutus")
    is_aika_command = (incoming_message_text[1:] == "aika")
    is_weather_command = incoming_message_text[1:].startswith("sää")
    is_rules_of_acquisition = (incoming_message_text[1:].startswith("sääntö"))

    if update.message.reply_to_message is not None:
        reply_handler(update)
    elif is_ruoka_command and chat.ruoka_enabled:
        ruoka_command(update)
    elif is_space_command and chat.space_enabled:
        space_command(update)
    elif is_user_command:
        users_command(update)  # TODO: Admin vivun taakse
    elif is_kuulutus_command:
        broadcast_toggle_command(update)
    elif is_aika_command and chat.time_enabled:
        time_command(update)
    elif is_rules_of_acquisition:
        rules_of_acquisition_command(update)
    elif is_weather_command and chat.weather_enabled:
        weather_command(update)


def reply_handler(update):
    if update.message.reply_to_message.from_user.is_bot:
        # Reply to bot, so most probably to me! (TODO: Figure out my own ID and use that instead)
        if update.message.reply_to_message.text.startswith("Git käyttäjä "):
            process_entities(update)


def process_entities(update):
    if Bob.objects.get(id=1).global_admin is not None:
        if update.effective_user.id == Bob.objects.get(id=1).global_admin.id:
            for message_entity in update.message.entities:
                process_entity(message_entity, update)
        else:
            update.message.reply_text("Et oo vissiin global_admin? ")
    else:
        update.message.reply_text("Globaalia adminia ei ole asetettu.")


def process_entity(message_entity, update):
    commit_author_email, commit_author_name, git_user = get_git_user_and_commit_info()
    if message_entity.type == "text_mention":
        user = TelegramUser.objects.get(id=message_entity.user.id)
        git_user.tg_user = user
    elif message_entity.type == "mention":
        username = re.search('@(.*)', update.message.text)
        telegram_users = TelegramUser.objects.filter(username=str(username.group(1)).strip())

        if telegram_users.count() > 0:
            git_user.tg_user = telegram_users[0]
        else:
            update.message.reply_text("En löytänyt tietokannastani ketään tuon nimistä. ")
    git_user.save()
    promote_or_praise(git_user, update.message.bot)


def leet_command(update: Update):
    now = datetime.datetime.now(pytz.timezone('Europe/Helsinki'))
    chat = Chat.objects.get(id=update.effective_chat.id)
    sender = ChatMember.objects.get(chat=update.effective_chat.id,
                                    tg_user=update.effective_user.id)
    if chat.latest_leet != now.date() and \
            now.hour == 13 and \
            now.minute == 37:
        chat.latest_leet = now.date()
        chat.save()
        reply_text = promote(sender)
    else:
        reply_text = demote(sender)
    update.message.reply_text(reply_text, quote=False)


def promote(sender):
    if sender.rank < len(ranks) - 1:
        sender.rank += 1
        up = u"\U0001F53C"
        reply_text = "Asento! " + str(sender.tg_user) + " ansaitsi ylennyksen arvoon " + \
                     ranks[sender.rank] + "! " + up + " Lepo. "
    else:
        sender.prestige += 1
        reply_text = "Asento! " + str(sender.tg_user) + \
                     " on saavuttanut jo korkeimman mahdollisen sotilasarvon! Näin ollen " + str(sender.tg_user) + \
                     " lähtee uudelle kierrokselle. Onneksi olkoon! " + \
                     "Juuri päättynyt kierros oli hänen " + str(sender.prestige) + ". Lepo. "
        sender.rank = 0
    sender.save()
    return reply_text


def demote(sender):
    if sender.rank > 0:
        sender.rank -= 1
    down = u"\U0001F53D"
    reply_text = "Alokasvirhe! " + str(sender.tg_user) + " alennettiin arvoon " + \
                 ranks[sender.rank] + ". " + down
    sender.save()
    return reply_text


def ruoka_command(update: Update) -> None:
    """
    Send a message when the command /ruoka is issued.
    Returns link to page in https://www.soppa365.fi
    """

    with open("recipes.txt", "r") as recipe_file:
        recipes = recipe_file.readlines()

    reply_text = random.choice(recipes)

    update.message.reply_text(reply_text, quote=False)


def space_command(update: Update) -> None:
    """
    Send a message when the command /space is issued.
    Queries next spacex launch time from public API:
    https://github.com/r-spacex/SpaceX-API
    """
    helsinki_tz = ZoneInfo('Europe/Helsinki')
    try:
        r = requests.get('https://api.spacexdata.com/v4/launches/next')
        r = r.json()
        name = r.get('name', None)
        launch_date = r.get('date_utc', None)
        waiting_time = "T-: "
        if launch_date:
            launch_date = datetime.datetime.fromisoformat(launch_date[:-1])
            delta = launch_date - datetime.datetime.now()
            days, hours, minutes = delta.days, delta.seconds // 3600, delta.seconds // 60 % 60
            if days > 0:
                waiting_time += "{} päivää, ".format(days)
            if hours > 0:
                waiting_time += "{} tuntia ja ".format(hours)
            if minutes > 0:
                waiting_time += "{} minuuttia.".format(minutes)
            launch_date = launch_date.astimezone(helsinki_tz).strftime('%d.%m.%Y klo %H:%M:%S (Helsinki)')
        reply_text = 'Seuraava SpaceX laukaisu {}:\n{}\n{}\n'.format(name, launch_date, waiting_time)
    except requests.exceptions.RequestException:
        reply_text = 'Ei tietoa seuraavasta lähdöstä :( API ehkä rikki.'

    update.message.reply_text(reply_text, quote=False)


def users_command(update: Update):
    chat_members = ChatMember.objects.filter(chat=update.effective_chat.id)
    reply_text = ""
    # code in place if we want to get the chat name and use it
    # chat_name = str(update.effective_chat.title)
    # if chat_name != "None":
    #    reply_text = chat_name + " -ryhmän käyttäjät " + "\U0001F913 " + "\n" + "\n"
    # else:
    #    reply_text = "Käyttäjät " + "\U0001F913 " + "\n" + "\n"
    reply_text = "*Käyttäjät* " + "\U0001F913 " + "\n" + "\n" + \
                 "*Nimi* ⌇ Arvo ⌇ Kunnia ⌇ Viestit" + "\n"  # nerd face emoji
    for chat_member in chat_members:
        reply_text += "*" + str(chat_member) + " ⌇*" + " " + \
                      str(chat_member.rank) + " ⌇ " + \
                      str(chat_member.prestige) + " ⌇ " + \
                      str(chat_member.message_count) + "\n"
    update.message.reply_markdown(reply_text, quote=False)


def broadcast_toggle_command(update):
    chat = Chat.objects.get(id=update.effective_chat.id)
    if update.message.text.casefold() == "/kuulutus on".casefold():
        chat.broadcast_enabled = True
        update.message.reply_text("Kuulutukset ovat nyt päällä tässä ryhmässä.", quote=False)
    elif update.message.text.casefold() == "/kuulutus off".casefold():
        chat.broadcast_enabled = False
        update.message.reply_text("Kuulutukset ovat nyt pois päältä.", quote=False)
    else:
        update.message.reply_text("Käyttö: \n"
                                  "'/kuulutus on' - Kytkee kuulutukset päälle \n"
                                  "'/kuulutus off' - Kytkee kuulutukset pois päältä\n")
        if chat.broadcast_enabled:
            update.message.reply_text("Tällä hetkellä kuulutukset ovat päällä.", quote=False)
        else:
            update.message.reply_text("Tällä hetkellä kuulutukset ovat pois päältä.", quote=False)
    chat.save()


async def broadcast_command(update):
    message = update.message.text
    await broadcast(update.bot, message)


def time_command(update: Update):
    date_time_obj = date_time_obj = datetime.datetime.now(pytz.timezone('Europe/Helsinki')).strftime('%H:%M:%S.%f')[:-4]
    time_stamps_str = str(date_time_obj)
    reply_text = '\U0001F551 ' + time_stamps_str
    update.message.reply_text(reply_text, quote=False)


def weather_command(update):
    city_parameter = update.message.text.replace(update.message.text.split()[0], "").lstrip()
    if city_parameter != "":
        reply_text = fetch_and_format_weather_data(city_parameter)
        if reply_text is not None:
            chat_member = ChatMember.objects.get(chat=update.effective_chat.id, tg_user=update.effective_user.id)
            chat_member.latest_weather_city = city_parameter
            chat_member.save()
    else:
        chat_member = ChatMember.objects.get(chat=update.effective_chat.id, tg_user=update.effective_user.id)
        if chat_member.latest_weather_city is not None:
            reply_text = fetch_and_format_weather_data(chat_member.latest_weather_city)
        else:
            reply_text = "Määrittele kaupunki kirjoittamalla se komennon perään. "

    if reply_text is None:
        reply_text = "Kaupunkia ei löydy."
    update.message.reply_text(reply_text, quote=False)


def fetch_and_format_weather_data(city_parameter):
    base_url = "https://api.openweathermap.org/data/2.5/weather?"
    complete_url = base_url + "appid=" + os.getenv("OPEN_WEATHER_API_KEY") + "&q=" + city_parameter
    response = requests.get(complete_url)
    x = response.json()
    if x["cod"] != "404":
        y = x["main"]
        w = x["wind"]
        s = x["sys"]
        z = x["weather"]
        offset = 127397  # country codes start here in unicode list order
        country = chr(ord(s["country"][0]) + offset) + chr(ord(s["country"][1]) + offset)
        delta = datetime.timedelta(seconds=x["timezone"])
        timezone = datetime.timezone(delta)
        localtime = datetime.datetime.utcnow() + delta
        current_temperature = round(y["temp"] - 273.15, 1)  # kelvin to celsius
        current_feels_like = round(y["feels_like"] - 273.15, 1)  # kelvin to celsius
        current_wind = w["speed"]
        current_wind_direction = wind_direction(w['deg'])
        weather_description = replace_weather_description_with_emojis(z[0]["description"])
        weather_string = (country + " " + city_parameter +
                          "\n🕒 " + localtime.strftime("%H:%M (") + str(timezone) + ")" +
                          "\n🌡 " + str(current_temperature) + " °C (tuntuu " + str(current_feels_like) + " °C)"
                                                                                                          "\n💨 " + str(
                    current_wind) + " m/s " + str(current_wind_direction) +
                          "\n" + str(weather_description))
        reply_text = weather_string
    else:
        reply_text = None
    return reply_text


def replace_weather_description_with_emojis(description):
    dictionary_of_weather_emojis = {
        'snow': ['lumisadetta', '🌨'],
        'rain': ['sadetta', '🌧'],
        'fog': ['sumua', '🌫'],
        'smoke': ['savua', '🌫'],
        'mist': ['usvaa', '🌫'],
        'haze': ['utua', '🌫'],
        'clear sky': ['poutaa', '🌞'],
        'thunderstorm': ['ukkosta', '🌩'],
        'few clouds': ['melkein selkeää', '☀ ☁'],
        'scattered clouds': ['puolipilvistä', '☁'],
        'broken clouds': ['melko pilvistä', '☁☁'],
        'overcast clouds': ['pilvistä', '☁☁☁'],
        'drizzle': ['tihkusadetta', '💧']
    }
    for i, j in dictionary_of_weather_emojis.items():
        if i in description:
            description = j[1] + " " + j[0]
    return description


def wind_direction(degrees):
    directions = ['pohjoisesta', 'koillisesta', 'idästä', 'kaakosta', 'etelästä', 'lounaasta', 'lännestä', 'luoteesta']
    cardinal = round(degrees / (360 / len(directions)))
    return directions[cardinal % len(directions)]


def or_command(update):
    options = re.split(r'\s.vai\s', update.message.text)
    options = [i.strip() for i in options]
    reply = random.choice(options)
    reply = reply.rstrip("?")
    if reply and reply is not None:
        update.message.reply_text(reply)


def rules_of_acquisition_command(update):
    rule_number = update.message.text.split(" ")[1]
    try:
        update.message.reply_text(rules_of_acquisition.dictionary[int(rule_number)], quote=False)
    except (KeyError, ValueError) as e:
        logger.info("Rule not found with key: \"" + str(e) + "\" Sending random rule instead.")
        random_rule_number = random.choice(list(rules_of_acquisition.dictionary))
        random_rule = rules_of_acquisition.dictionary[random_rule_number]
        update.message.reply_text(str(random_rule_number) + ". " + random_rule, quote=False)


def low_probability_reply(update, integer=0):  # added int argument for unit testing
    if integer == 0:
        random_int = random.randint(1, 10000)  # 0,01% probability
    else:
        random_int = integer
    if random_int == 1:
        reply_text = "Vaikuttaa siltä että olette todella onnekas " + "\U0001F340"  # clover emoji
        update.message.reply_text(reply_text, quote=True)


@sync_to_async
def broadcast(bot, message):
    if message is not None and message != "":
        chats = Chat.objects.all()
        for chat in chats:
            if chat.broadcast_enabled:
                try:
                    bot.sendMessage(chat.id, message)
                except telegram.error.BadRequest as e:
                    logger.error("Tried to broadcast to chat with id " + str(chat.id) +
                                 " but Telegram-API responded with \"BadRequest: " + str(e) + "\"")


def broadcast_and_promote(updater):
    try:
        bob_db_object = Bob.objects.get(id=1)
    except Bob.DoesNotExist:
        bob_db_object = Bob(id=1, uptime_started_date=datetime.datetime.now())
    broadcast_message = os.getenv("COMMIT_MESSAGE")
    loop = asyncio.get_event_loop()
    if broadcast_message != bob_db_object.latest_startup_broadcast_message and broadcast_message != "":
        # TODO: Make this a task
        loop.run_until_complete(broadcast(updater.bot, broadcast_message))
        bob_db_object.latest_startup_broadcast_message = broadcast_message
        promote_committer_or_find_out_who_he_is(updater)
    else:
        loop.run_until_complete(broadcast(updater.bot, "Olin vain hiljaa hetken. "))
    bob_db_object.save()


@sync_to_async
def get_bob():
    return Bob.objects.get(id=1)


def promote_committer_or_find_out_who_he_is(updater):
    commit_author_email, commit_author_name, git_user = get_git_user_and_commit_info()

    if git_user.tg_user is not None:
        promote_or_praise(git_user, updater.bot)
    else:
        reply_message = "Git käyttäjä " + str(commit_author_name) + " " + str(commit_author_email) + \
                        " ei ole minulle tuttu. Onko hän joku tästä ryhmästä?"
        asyncio.run(broadcast(updater.bot, reply_message))


def get_git_user_and_commit_info():
    commit_author_name = os.getenv("COMMIT_AUTHOR_NAME", "You should not see this")
    commit_author_email = os.getenv("COMMIT_AUTHOR_EMAIL", "You should not see this")
    if GitUser.objects.filter(name=commit_author_name, email=commit_author_email).count() <= 0:
        git_user = GitUser(name=commit_author_name, email=commit_author_email)
        git_user.save()
    else:
        git_user = GitUser.objects.get(name=commit_author_name, email=commit_author_email)
    return commit_author_email, commit_author_name, git_user


def promote_or_praise(git_user, bot):
    now = datetime.datetime.now(pytz.timezone('Europe/Helsinki'))
    tg_user = TelegramUser.objects.get(id=git_user.tg_user.id)

    if tg_user.latest_promotion_from_git_commit is None or \
            tg_user.latest_promotion_from_git_commit < now.date() - datetime.timedelta(days=6):
        committer_chat_memberships = ChatMember.objects.filter(tg_user=git_user.tg_user)
        for membership in committer_chat_memberships:
            promote(membership)
        asyncio.run(broadcast(bot, str(git_user.tg_user) + " ansaitsi ylennyksen ahkeralla työllä. "))
        tg_user.latest_promotion_from_git_commit = now.date()
        tg_user.save()
    else:
        # It has not been week yet since last promotion
        asyncio.run(broadcast(bot, "Kiitos " + str(git_user.tg_user) + ", hyvää työtä!"))



@sync_to_async
def send_file_to_global_admin(file, bot):
    if Bob.objects.get(id=1).global_admin is not None:
        bot.send_document(Bob.objects.get(id=1).global_admin.id, file)
    else:
        broadcast("Varmuuskopiointi pilveen epäonnistui, global_admin ei ole asetettu.")


def update_chat_in_db(update):
    # Check if the chat exists alredy or not in the database:
    if Chat.objects.filter(id=update.effective_chat.id).count() <= 0:
        chat = Chat(id=update.effective_chat.id)
        if int(update.effective_chat.id) < 0:
            chat.title = update.effective_chat.title
        chat.save()


def update_user_in_db(update):
    # TelegramUser
    telegram_users = TelegramUser.objects.filter(id=update.effective_user.id)
    if telegram_users.count() == 0:
        updated_user = TelegramUser(id=update.effective_user.id)
    else:
        updated_user = telegram_users[0]

    if update.effective_user.first_name is not None:
        updated_user.first_name = update.effective_user.first_name
    if update.effective_user.last_name is not None:
        updated_user.last_name = update.effective_user.last_name
    if update.effective_user.username is not None:
        updated_user.username = update.effective_user.username
    updated_user.save()

    # ChatMember
    chat_members = ChatMember.objects.filter(chat=update.effective_chat.id,
                                             tg_user=update.effective_user.id)
    if chat_members.count() == 0:
        chat_member = ChatMember(chat=Chat.objects.get(id=update.effective_chat.id),
                                 tg_user=TelegramUser.objects.get(id=update.effective_user.id),
                                 message_count=1)
    else:
        chat_member = chat_members[0]
        chat_member.message_count += 1
    chat_member.save()


# Reads the ranks.txt and returns it contents as a list
# TODO: make this idempotent
def read_ranks_file():
    file = open('../ranks.txt')
    for line in file:
        # strip removes all whitsespaces from end and beginning
        line = line.strip()
        ranks.append(line)
    file.close()
    return ranks


def init_bot():
    read_ranks_file()
    token = os.getenv("BOT_TOKEN")
    if token == "" or token is None:
        logger.critical("BOT_TOKEN env variable is not set. ")
        raise ValueError("BOT_TOKEN env variable is not set. ")
    print(token)

    # Create the Updater and pass it your bot's token.
    updater = Updater(token)

    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher
    # on different commands - answer in Telegram
    dispatcher.add_handler(MessageHandler(Filters.all, message_handler))  # KAIKKI viestit
    # on non command i.e message - echo the message on Telegram
    # dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, echo))

    broadcast_and_promote(updater)
    return updater


def main() -> None:
    updater = init_bot()
    updater.start_polling()  # Start the bot
    scheduler.Scheduler(updater)

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()
