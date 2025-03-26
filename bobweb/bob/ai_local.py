import re

from telegram import Update

from bobweb.bob import async_http
from bobweb.bob.utils_common import has, send_bot_is_typing_status_update

# TODO:
#   - Tokenrajan hallinta
#   - Tiivistelmien kirjoittaminen silloin tällöin
#   - Kuuma ja kylmä muisti?
#   - Käyttäjän nimimerkin määrittäminen
#   - Kuvien sun muiden hallinta
#   - Funktioiden määrittely, eli esim. osaisi itse kutsua .sää jne.
#   - Kontekstissa näkyvyys myös command viesteille
#   - Kunnon virheenhallinta ja lokitus
#   - System messageen tieto päivämäärästä yms. tärkeää

system_message = (
    "You are Bob-bot, an AI-powered chat bot in a friend group known as 'Band of Brothers' (Bob). "
    "Follow the instructions as closely as you can. "
)

chats_contexts = {}

async def handle_ai(update: Update):
    if not has(update.effective_message.text):
        return
    message = update.effective_user.first_name + ": " + update.effective_message.text
    if not update.effective_chat in chats_contexts:
        chats_contexts[update.effective_chat] = []
    chats_contexts[update.effective_chat].append(message)
    messages_as_single_string = ""
    for message in chats_contexts[update.effective_chat]:
        messages_as_single_string = messages_as_single_string + message + "\n"

    # Ensimmäinen kierros: Bob selvittää haluaako hän vastata viestiin
    prompt = (
        "You are Bob-bot, the chat bot for the Band of Brothers friend group. "
        "Here is the conversation so far:\n" +
        messages_as_single_string + "\n\n"
    
        "You are Bob, a chat bot. Your task is to determine if the latest message is specifically directed to you. "
        "Instead of simply looking for a designated identifier, analyze the context, tone, and content of the conversation to decide if the message is intended for you.\n\n"
    
        "Before formulating an actual reply, think aloud by writing a five-word summary of your internal thought process. "
        "This internal draft is for your own processing and will not be shared with users.\n\n"
    
        "If, based on your analysis, the latest message is directed to you, reply with <respond>. "
        "If it is not directed to you, reply with <donotrespond>."
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
    api_url = "http://10.84.9.11:11434/api/chat"
    response = await async_http.post(url=api_url, json=payload)
    if response.status != 200:
        # TODO: log error
        return

    # Toinen kierros: Bob haluaa vastata ja generoi vastauksen
    json = await response.json()
    match = re.search(r"<respond>", json["message"]["content"])
    if match:
        prompt = (
            "Olet Bob-bot, Band of brothers kaveriporukan telegram botti. "
            "Tässä on tähänastinen keskustelu: \n" +
            messages_as_single_string +
            "Bob-botin sanomat viestit ovat sinun lähettämiä. "
            "Vastaa viimeisimpään viestiin, "
            "mutta ennen lopullista vastausta tee vastauksesta 5 sanan luonnos ajattelun avuksi. "
            "Toimita lopullinen vastaus ##### erottimen jälkeen. " )
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

        match = re.search(r"#####\s*(.*)", ai_message, re.DOTALL)
        if match:
            ai_message = match.group(1)

        # Kolmas kierros: Bob tiivistää vastauksen niin lyhyeksi kuin pystyy
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

        if len(chats_contexts[update.effective_chat]) > 100:
            chats_contexts[update.effective_chat].pop(0)
