import logging

import litellm
from litellm import (
    ContentPolicyViolationError,
    AuthenticationError,
    RateLimitError,
    ServiceUnavailableError
)

logger = logging.getLogger(__name__)

# Custom Exception for errors caused by LLM prompting
class ResponseGenerationException(Exception):
    def __init__(self, response_text):
        self.response_text = response_text  # Text that is sent back to chat


async def acompletion(*args, **kwargs):
    try:
        response = await litellm.acompletion(*args, **kwargs)
    except ContentPolicyViolationError as e:
        error_response_to_user = (f"{e.llm_provider}: Pyyntösi hylättiin turvajärjestelmämme seurauksena. Viestissäsi saattaa "
                                    "olla tekstiä, joka ei ole sallittu turvajärjestelmämme toimesta.")
        log_message = f"{e.llm_provider} : {e.status_code} : {e.message}"
        log_level = logging.INFO
        logger.log(level=log_level, msg=log_message)
        raise ResponseGenerationException(error_response_to_user)
    except AuthenticationError as e:
        error_response_to_user = f"Virhe autentikoitumisessa {e.llm_provider} järjestelmään."
        log_message = f"{e.llm_provider} : {e.status_code} : {e.message}"
        log_level = logging.ERROR
        logger.log(level=log_level, msg=log_message)
        raise ResponseGenerationException(error_response_to_user)
    except RateLimitError as e:
        error_response_to_user = f"{e.llm_provider}: Käytettävissä oleva kiintiö on käytetty."
        log_message = f"{e.llm_provider} : {e.status_code} : {e.message}"
        log_level = logging.INFO
        logger.log(level=log_level, msg=log_message)
        raise ResponseGenerationException(error_response_to_user)
    except ServiceUnavailableError as e:
        error_response_to_user = (f"{e.llm_provider} palvelu ei ole käytettävissä tai se on juuri nyt ruuhkautunut. "
                                  "Ole hyvä ja yritä hetken päästä uudelleen.")
        log_message = f"{e.llm_provider} : {e.status_code} : {e.message}"
        log_level = logging.INFO
        logger.log(level=log_level, msg=log_message)
        raise ResponseGenerationException(error_response_to_user)
    except Exception as e:
        error_response_to_user = "Vastauksen generointi epäonnistui."
        log_message = f"Error: {e}"
        log_level = logging.ERROR
        logger.log(level=log_level, msg=log_message)
        raise ResponseGenerationException(error_response_to_user)
    else:
        return response
