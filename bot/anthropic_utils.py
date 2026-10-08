import logging
from typing import Optional

import anthropic
from anthropic import AsyncAnthropic

from bot import config

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 4096

SAFETY_SYSTEM_ERROR_MSG = ("Anthropic: Pyyntösi hylättiin turvajärjestelmämme seurauksena. Viestissäsi saattaa "
                           "olla tekstiä, joka ei ole sallittu turvajärjestelmämme toimesta.")


# Custom Exception for errors caused by response generation
class ResponseGenerationException(Exception):
    def __init__(self, response_text):
        self.response_text = response_text  # Text that is sent back to chat


def ensure_anthropic_api_key_set():
    """ Checks that anthropic api key is set. Raises ResponseGenerationException if not. """
    if config.anthropic_api_key is None or config.anthropic_api_key == '':
        logger.error('ANTHROPIC_API_KEY is not set. No response was generated.')
        raise ResponseGenerationException('Anthropic API key is missing from environment variables')


def to_anthropic_messages(messages: list[dict]) -> tuple[Optional[str], list[dict]]:
    """ Converts OpenAI style chat messages to Anthropic format. Anthropic has no system role, so system messages are
        returned separately. Image blocks are converted from 'image_url' blocks to Anthropic 'image' blocks. """
    system_parts: list[str] = []
    converted: list[dict] = []
    for message in messages:
        content = message['content']
        blocks = [{'type': 'text', 'text': content}] if isinstance(content, str) else content
        if message['role'] == 'system':
            system_parts.extend(b['text'] for b in blocks if b.get('type') == 'text')
            continue
        converted.append({'role': message['role'], 'content': [_to_anthropic_block(b) for b in blocks]})
    return ('\n\n'.join(system_parts) or None), converted


def _to_anthropic_block(block: dict) -> dict:
    if block.get('type') != 'image_url':
        return block
    url: str = block['image_url']['url']
    if url.startswith('data:') and ';base64,' in url:
        header, data = url.split(';base64,', 1)
        return {'type': 'image', 'source': {'type': 'base64', 'media_type': header[len('data:'):], 'data': data}}
    return {'type': 'image', 'source': {'type': 'url', 'url': url}}


def extract_text(response) -> str:
    """ Joins text blocks of the response. Skips other blocks, e.g. web search tool use and results. """
    return ''.join(block.text for block in response.content if block.type == 'text')


async def create_message(*, model: str, messages: list[dict], system: Optional[str] = None,
                         max_tokens: int = DEFAULT_MAX_TOKENS, tools: Optional[list[dict]] = None):
    """ Calls the Anthropic messages api. All errors are converted to ResponseGenerationException that has
        a user friendly message. """
    kwargs = {'model': model, 'messages': messages, 'max_tokens': max_tokens}
    if system:
        kwargs['system'] = system
    if tools:
        kwargs['tools'] = tools

    try:
        client = AsyncAnthropic(api_key=config.anthropic_api_key)
        response = await client.messages.create(**kwargs)
    except anthropic.BadRequestError as e:
        _log(logging.INFO, e)
        raise ResponseGenerationException(SAFETY_SYSTEM_ERROR_MSG)
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
        _log(logging.ERROR, e)
        raise ResponseGenerationException("Virhe autentikoitumisessa Anthropic järjestelmään. "
                                          "Tarkista API-avaimesi.")
    except anthropic.RateLimitError as e:
        _log(logging.INFO, e)
        raise ResponseGenerationException("Anthropic: Palveluntarjoajan käyttöraja on saavutettu.")
    except (anthropic.InternalServerError, anthropic.APIConnectionError) as e:
        _log(logging.INFO, e)
        raise ResponseGenerationException("Anthropic palvelu ei ole käytettävissä tai se on juuri nyt ruuhkautunut. "
                                          "Ole hyvä ja yritä hetken päästä uudelleen.")
    except Exception as e:
        logger.error(f"Error: {e}")
        raise ResponseGenerationException("Vastauksen generointi epäonnistui.")

    if response.stop_reason == 'refusal':
        logger.info("Anthropic : response refused by the model")
        raise ResponseGenerationException(SAFETY_SYSTEM_ERROR_MSG)
    return response


def _log(level: int, e: Exception) -> None:
    logger.log(level=level, msg=f"Anthropic : {getattr(e, 'status_code', None)} : {getattr(e, 'message', e)}")
