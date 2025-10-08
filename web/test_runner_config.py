from django.test.runner import DiscoverRunner
from unittest import TestLoader


# Configuring the test runner
ALL_TEST_FILE_PATTERNS = ['test_*.py', '*_tests.py']


class MultiPatternTestLoader(TestLoader):
    # Custom test loader which searches files with multiple patterns
    def __init__(self, all_file_patterns=None):
        super().__init__()
        if all_file_patterns is None:
            raise ValueError("all_file_patterns must be provided")
        self.all_file_patterns = all_file_patterns

    def _match_path(self, path, full_path, pattern):
        # Check for both patterns
        for pattern in self.all_file_patterns:
            if super()._match_path(path, full_path, pattern):
                return True
        return False


class ExtendedTestRunner(DiscoverRunner):
    # Extended test runner
    test_loader = MultiPatternTestLoader(ALL_TEST_FILE_PATTERNS)
