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


ranks = [
    "siviilipalvelusmies",
    "alokas",
    "sotamies",
    "aliupseerioppilas",
    "korpraali",
    "ylimatruusi",
    "alikersantti",
    "upseerioppilas",
    "kersantti",
    "upseerikokelas",
    "ylikersantti",
    "vääpeli",
    "pursimies",
    "ylivääpeli",
    "sotilasmestari",
    "vänrikki",
    "aliluutnantti",
    "luutnantti",
    "yliluutnantti",
    "kapteeni",
    "kapteeniluutnantti",
    "majuri",
    "komentajakapteeni",
    "everstiluutnantti",
    "komentaja",
    "eversti",
    "kommodori",
    "prikaatinkenraali",
    "kenraalimajuri",
    "kontra-amiraali",
    "kenraaliluutnantti",
    "vara-amiraali",
    "amiraali",
    "kenraali",
    "ylipäällikkö",
    "sotajumala",
    "supersotajumala",
    "ylisotajumala",
]
