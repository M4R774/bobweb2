import datetime
import re

from telegram import Update

from bobweb.bob import async_http
from bobweb.bob.resources.bob_constants import fitz
from bobweb.bob.utils_common import has, send_bot_is_typing_status_update


# TODO: Kontekstin hallinta:
#   - Tokenrajan hallinta
#   - Tiivistelmien kirjoittaminen silloin tällöin
#   - Kuuma ja kylmä muisti?
#   - Jokaiselle chätille erikseen muisti

system_message = (
"You are Bob-bot, an AI-powered Telegram bot in a friend group known as 'Band of Brothers' (Bob). "
"Follow the instructions as closely as you can. "  # TODO: Tietoa päivämäärästä yms.
)

chats_contexts = {}

async def handle_ai(update: Update):
    print("##### AI aloittaa viestin käsittelyn #####")  # TODO: Poista tää
    if not has(update.effective_message.text):
        return
    message = update.effective_user.first_name + ": " + update.effective_message.text
    if not update.effective_chat in chats_contexts:
        chats_contexts[update.effective_chat] = []
    chats_contexts[update.effective_chat].append(message)
    messages_as_single_string = ""
    for message in chats_contexts[update.effective_chat]:
        messages_as_single_string = messages_as_single_string + message + "\n"
    prompt = (
        "Olet Bob-bot, Band of Brothers kaveriporukan oma telegram botti. "
        "Tässä on tähänastinen keskustelu: \n" +

        messages_as_single_string +

        "Sinä olet Bob-bot. Liittyykö keskustelu sinuun? "

        "Pohdi asiaa ensin kirjoittamalla 5 sanan luonnos ajattelustasi."
        
        "Älä mieti vielä varsinaista vastausta, mieti vain,"
        "liittyykö keskustelu sinuun."

        "Jos keskustelu liittyy sinuun <respond>. "
        
        "Jos keskustelu ei liity sinuun, vastaa <donotrespond>."
    )
    messages = ([{
        "role": "system",
        "content": system_message,
    },{
        "role": "user",
        "content": prompt
    }])
    payload = {
        "model": "LoTUs5494/mistral-small-3.1:latest",
        "messages": messages,
        "stream": False
    }
    api_url = "http://localhost:11434/api/chat"
    response = await async_http.post(url=api_url, json=payload)
    if response.status != 200:
        print("Status != 200")
        print(response)
        return

    # Toinen kierros
    json = await response.json()
    print(json["message"]["content"])
    match = re.search(r"<respond>", json["message"]["content"])
    if match:
        prompt = (
                "Olet Bob-bot, Band of brothers kaveriporukan telegram botti. "
                "Tässä on tähänastinen keskustelu: \n" +
                messages_as_single_string +
                "Bob-botin sanomat viestit ovat sinun lähettämiä. "
                "Vastaa viimeisimpään viestiin. ")
        messages = ([{
            "role": "system",
            "content": system_message,
        }, {
            "role": "user",
            "content": prompt
        }])
        await send_bot_is_typing_status_update(update.effective_chat)
        payload = {
            "model": "LoTUs5494/mistral-small-3.1:latest",
            "messages": messages,
            "stream": False
        }
        response = await async_http.post(url=api_url, json=payload)
        json = await response.json()
        ai_message = json["message"]["content"]
        print(ai_message)

        # Kolmas kierros
        prompt = (
                "Olet Bob-bot, Band of brothers kaveriporukan telegram botti. "
                "Tässä on tähänastinen keskustelu: \n" +
                messages_as_single_string +
                "Olet päättänyt osallistua keskusteluun tällaisella viestillä:" +
                ai_message + "\n"
                "Tiivistä viestisi niin lyhyeksi kuin mahdollista ja poista turha hölinä. "
                "Vastauksesi ei saa sisältää mitään muuta kuin tiivistetyn viestin. ")
        messages = ([{
            "role": "system",
            "content": system_message,
        }, {
            "role": "user",
            "content": prompt
        }])
        await send_bot_is_typing_status_update(update.effective_chat)
        payload = {
            "model": "LoTUs5494/mistral-small-3.1:latest",
            "messages": messages,
            "stream": False
        }
        response = await async_http.post(url=api_url, json=payload)
        json = await response.json()
        ai_message = json["message"]["content"]
        chats_contexts[update.effective_chat].append("Bob-bot: " + ai_message)
        await update.effective_chat.send_message(ai_message)

