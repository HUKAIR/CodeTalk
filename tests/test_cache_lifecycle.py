import unittest

from codetalk.cache import Cache


class TestCacheLifecycle(unittest.TestCase):
    def test_context_manager_closes_idempotently(self):
        with Cache(":memory:") as cache:
            self.assertIsNotNone(cache.conn)
        self.assertIsNone(cache.conn)
        cache.close()
        self.assertIsNone(cache.conn)


if __name__ == "__main__":
    unittest.main()
