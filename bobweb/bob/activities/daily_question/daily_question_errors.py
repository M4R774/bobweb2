class DailyQuestionWinnerSetError(Exception):
    localized_msg = None


class LastQuestionWinnerAlreadySet(DailyQuestionWinnerSetError):
    """ Author's message could not be set as winning answer as the question already has a answer set as winning one """
    localized_msg = 'Kysymys tallennettu. Voittoa ei pystytty tallentamaan, sillä edellisen kysymyksen voittaja ' \
                    'on jo merkattu.'


class NoAnswerFoundToPrevQuestion(DailyQuestionWinnerSetError):
    """ Author's message could not be set as winning answer as no answer found to last question by author """
    localized_msg = 'Kysymys tallennettu. Ei vastausta edelliseen kysymykseen jota merkata ' \
                    'voittaneeksi. Jos olet vastannut tässä ryhmässä merkitse vastausviestisi ' \
                    'vastaamalla (reply) siihen komennolla \'/vastaus\'. Tallennetut vastaukset ' \
                    'eivät vaikuta pisteiden laskentaan, vaan pisteet lasketaan esitettyjen ' \
                    'kysymysten määrästä'
