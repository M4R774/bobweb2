import random

from telegram.constants import ParseMode

from bobweb.bob.message_board import MessageWithPreview


async def create_good_night_message() -> MessageWithPreview:
    """ Creates message that contains good nights wishes """
    good_night_wish = random.choice(good_night_message_possible_content)
    emoji_list = random.sample(good_night_message_possible_emoji, 4)
    message = f'{emoji_list[0]}{emoji_list[1]} {good_night_wish} {emoji_list[2]}{emoji_list[3]}'
    return MessageWithPreview(message, None, ParseMode.MARKDOWN)


good_night_message_possible_emoji = ['💤', '🌃', '🧸', '🥱', '🛌', '🌉', '🌛', '🌚', '✨']
good_night_message_possible_content = [
    'Hyvää yötä ja kauniita unia',
    'Nuku hyvin ja herää virkeänä aamulla',
    'Silmät kiinni ja unimaailmaan',
    'Kauniita unia tähtien alla',
    'Yöpuulle ja levollisia hetkiä',
    'Sulje silmäsi ja anna unen viedä mukanaan',
    'Levollista yötä ja suloisia unia',
    'Hyvää yötä, huominen odottaa sinua',
    'Anna unen tuudittaa sinut rauhalliseen lepoon',
    'Nyt on aika nukkua ja kerätä voimia uuteen päivään',
    'Unet tuovat huomenna uusia seikkailuja',
    'Nuku rauhassa, maailma odottaa sinua aamulla',
    'Rentouttavaa yötä ja levollisia unia',
    'Sulje silmät ja vaivu unen pehmeään syliin',
    'Tähtien alla levollista unta',
    'Hyvää yötä ja unelmien matkoja',
    'Aika vetäytyä yöunille, hyvää yötä',
    'Anna unen viedä sinut kauniisiin maisemiin',
    'Nuku rauhassa, huominen on täynnä mahdollisuuksia',
    'Unimaailma kutsuu, nuku hyvin',
    'Unien aika, hyvää yötä',
    'Vaivu unen syliin ja anna mielen levätä',
    'Hyvää yötä, sulje silmäsi ja rauhoitu',
    'Anna unen rauhoittaa ja ladata voimasi',
    'Yön hiljaisuus on täydellinen hetki levätä, hyvää yötä',
    'Nyt on aika unohtaa päivän murheet, hyvää yötä',
    'Nuku syvään ja herää valmiina uuteen päivään',
    'Kääridy lämpimiin peittoihin ja anna unen tulla',
    'Hyvää yötä, kohta näet kauneimmat unet',
    'Toivotan sinulle rauhallista ja levollista yötä',
    'Nuku hyvin, aamu tuo uudet mahdollisuudet',
    'Hyvää yötä, unessa voit olla mitä tahansa',
    'Levollista unta ja rauhallista yötä sinulle',
    'Sulje silmäsi ja anna ajatusten hiljentyä uneen',
    'Yö tuo levon ja unet, hyvää yötä',
    'Vaivu rauhalliseen uneen ja näe kauniita unia',
    'Nyt on aika nukahtaa ja unohtaa kiireet, hyvää yötä',
    'Hyvää yötä, anna unen kuljettaa sinut seikkailuihin',
    'Yö antaa voimaa uuteen aamuun, nuku hyvin',
    'Nuku makeasti ja kerää voimia huomiseen'
]
