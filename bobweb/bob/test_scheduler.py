from unittest import TestCase, mock
from unittest.mock import patch

from bobweb.bob.scheduler import Scheduler


class Test(TestCase):
    def setUp(self) -> None:
        pass

    def test_scheduler(self):
        with patch('asyncio.get_event_loop') as mock_asyncio:
            scheduler = Scheduler(None)
