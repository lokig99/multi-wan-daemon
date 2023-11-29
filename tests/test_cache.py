# Tests for the cache module
import datetime
import time
import unittest

from context import cache


class CacheTest(unittest.TestCase):
    def setUp(self):
        self.cache = cache.Cache()

    def test_expires_in(self):
        self.assertIsNone(self.cache.expires_in('k1'))
        self.cache['k1'] = 'v1', 1
        self.assertEqual(self.cache.expires_in('k1'), 1)

    def test_key_timeout(self):
        self.cache['k1'] = 'v1', 1
        self.assertEqual(self.cache['k1'], 'v1')
        time.sleep(1)
        self.assertIsNone(self.cache['k1'])

    def test_key_insertion(self):
        self.cache['k1'] = 'v1', 1
        self.assertEqual(self.cache['k1'], 'v1')
        self.cache['k1'] = 'v2', 1
        self.assertEqual(self.cache['k1'], 'v2')

    def test_key_deletion(self):
        self.cache['k1'] = 'v1', 1
        self.assertEqual(self.cache['k1'], 'v1')
        del self.cache['k1']
        self.assertIsNone(self.cache['k1'])

    def test_key_exists(self):
        self.cache['k1'] = 'v1', 1
        self.assertTrue('k1' in self.cache)
        self.assertFalse('k2' in self.cache)

    def test_key_timeout_value_validation(self):
        with self.assertRaises(ValueError):
            self.cache['k1'] = 'v1', -1
        with self.assertRaises(TypeError):
            self.cache['k1'] = 'v1', 'invalid'

    def test_string_representation(self):
        self.cache['k1'] = 'v1', 1
        self.assertEqual(
            str(self.cache), f"{{'k1': ('v1', {self.cache.expiration_time('k1')})}}")

    def test_expiration_date(self):
        self.cache['k1'] = 'v1', 1
        self.assertEqual(self.cache.expiration_datetime('k1'),
                         datetime.datetime.fromtimestamp(time.time() + 1))

    def test_expiration_date_key_not_found(self):
        self.assertIsNone(self.cache.expiration_datetime('k1'))
