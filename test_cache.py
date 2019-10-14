import unittest
from datetime import datetime, timedelta

try:
    from django.http import HttpRequest
except ImportError:
    class HttpRequest:
        pass
    
from .cache import (
    cachekey, cache, cache_in_instance, cache_in_request,
    request_cache, prefix, arguments)

from .simplecache import Cache


class A_Class(object):
    "Just a test class"

    def a_method(self):
        "Just a test method"
        pass

    @classmethod
    def a_classmethod(cls):
        "Just a test classmethod"
        pass

    @staticmethod
    def a_staticmethod():
        "Just a test staticmethod"
        pass


def a_function(a, b, c=3, d=4):
    "Just a test function"
    pass


class TestCacheHelpers(unittest.TestCase):
    """
    Test `lib.cache.cache` decorator helpers.
    """

    def test_prefix(self):

        # prefix for function
        self.assertEqual(
            prefix(a_function),
            'lib.test_cache:a_function:')

        # prefix for class instance method
        self.assertEqual(
            prefix(A_Class().a_method),
            'lib.test_cache.A_Class:a_method:')

        # prefix for classmethod
        self.assertEqual(
            prefix(A_Class.a_classmethod),
            'lib.test_cache.A_Class:a_classmethod:')

        # prefix for staticmethod (missing class name)
        self.assertEqual(
            prefix(A_Class.a_staticmethod),
            'lib.test_cache:a_staticmethod:')

    def test_arguments(self):

        # default values should also be returned
        self.assertEqual(
            arguments(a_function, 1, 2, d=44), [1, 2, 3, 44])

        # should be independent of caller argument order
        self.assertEqual(
            arguments(a_function, 1, d=44, c=33, b=22), [1, 22, 33, 44])


class TestCacheDecorator(unittest.TestCase):
    """
    Test `lib.cache.cache` decorator.
    """

    def test_cache_without_arguments(self):

        # test non-cached function for baseline behavior
        def testfunc():
            return str(datetime.now())
        self.assertNotEqual(testfunc(), testfunc())

        # test cached version of same function
        @cache(_cache=Cache())
        def testfunc():
            return str(datetime.now())
        self.assertEqual(testfunc(), testfunc())

    def test_cache_with_arguments(self):

        # test non-cached function for baseline behavior
        def testfunc(a, b=1):
            return str(datetime.now() + timedelta(days=a + b))
        self.assertNotEqual(testfunc(1, 2), testfunc(1, 2))

        # test cached version of same function
        @cache(_cache=Cache())
        def testfunc(a, b=1):
            return str(datetime.now() + timedelta(days=a + b))
        self.assertEqual(testfunc(1, 2), testfunc(1, 2))

        # different arguments should result in different values
        self.assertNotEqual(testfunc(2, 1), testfunc(3, 1))

    def test_cache_delete(self):

        @cache(_cache=Cache())
        def testfunc(a, b=1):
            return str(datetime.now() + timedelta(days=a + b))

        result1 = testfunc(1, 2)

        # deleting a non-existing key should be a no-op
        testfunc.cache_delete(10, 20)
        result2 = testfunc(1, 2)
        self.assertEqual(result1, result2)

        # deleting an existing key should force a new result
        testfunc.cache_delete(1, 2)
        result3 = testfunc(1, 2)
        self.assertEqual(result1, result2)
        self.assertNotEqual(result1, result3)

    def test_cache_clear(self):

        # start with a shared cache
        shared_cache = Cache()

        @cache(_cache=shared_cache)
        def testfunc1(a, b=1):
            return str(datetime.now() + timedelta(days=a + b))

        @cache(_cache=shared_cache)
        def testfunc2(a, b=1):
            return str(datetime.now() + timedelta(days=a + b))

        # cache begins with zero entries
        _cache = testfunc1.cache._cache
        self.assertEqual(len(_cache), 0)

        # create 10 cache entries for each test function
        args_list = [(n, n + 1) for n in range(10)]
        for a, b in args_list:
            testfunc1(a, b)
            testfunc2(a, b)
        self.assertEqual(len(_cache), 20)

        # testfunc1.cache_clear() should remove only the testfunc1 entries
        testfunc1.cache_clear()
        self.assertEqual(len(_cache), 10)

        # testfunc2.cache_clear() should remove what's left
        testfunc2.cache_clear()
        self.assertEqual(len(_cache), 0)

    def test_do_not_cache_marker(self):

        marker = object()

        def cache_toggle(func, *args, **kwargs):
            if args[0]:
                return marker
            return cachekey(func, *args, **kwargs)

        @cache(_cache=Cache(), _key=cache_toggle, _marker=marker)
        def testfunc(key_marker=False, return_marker=False):
            return marker if return_marker else str(datetime.now())

        cached_result = testfunc()

        # confirm baseline behavior with _key and _marker
        self.assertEqual(testfunc(), cached_result)

        # confirm _key=marker skips the cache
        self.assertNotEqual(testfunc(key_marker=True), cached_result)
        self.assertEqual(testfunc(), cached_result)

        # confirm function_result=marker skips the cache and returns marker
        result = testfunc(return_marker=True)
        self.assertEqual(result, marker)
        self.assertNotEqual(result, cached_result)
        self.assertEqual(testfunc(), cached_result)


class TestCacheInInstanceDecorator(unittest.TestCase):
    """
    Test `lib.cache.cache_in_instance` decorator.
    """

    def test_cache_with_arg_instance(self):

        class MyClass(object):
            def my_method(self, arg1, arg2):
                return arg1, arg2, str(datetime.now())

        # test non-cached function for baseline behavior
        def testfunc(instance, a, b):
            return instance.my_method(a, b)
        instance = MyClass()
        self.assertNotEqual(
            testfunc(instance, 1, 2),
            testfunc(instance, 1, 2))

        # test cached version of same function
        @cache_in_instance()
        def testfunc(instance, a, b):
            return instance.my_method(a, b)
        instance = MyClass()
        self.assertEqual(
            testfunc(instance, 1, 2),
            testfunc(instance, 1, 2))

        # different arguments should result in different values
        self.assertNotEqual(
            testfunc(instance, 2, 1),
            testfunc(instance, 3, 1))

        # there should now be three items in the cache
        self.assertEqual(len(testfunc.cache(instance)), 3)

    def test_cache_with_kwarg_instance(self):

        class MyClass(object):
            def my_method(self, arg1, arg2):
                return arg1, arg2, str(datetime.now())

        # test non-cached function for baseline behavior
        def testfunc(a, b, instance=None):
            return instance.my_method(a, b)
        instance = MyClass()
        self.assertNotEqual(
            testfunc(1, 2, instance=instance),
            testfunc(1, 2, instance=instance))

        # test cached version of same function
        @cache_in_instance()
        def testfunc(a, b, instance=None):
            return instance.my_method(a, b)
        instance = MyClass()
        self.assertEqual(
            testfunc(1, 2, instance=instance),
            testfunc(1, 2, instance=instance))

        # different arguments should result in different values
        self.assertNotEqual(
            testfunc(2, 1, instance=instance),
            testfunc(3, 1, instance=instance))

        # there should now be three items in the cache
        self.assertEqual(len(testfunc.cache(instance)), 3)

    def test_cache_method(self):

        # test non-cached method for baseline behavior
        class MyClass(object):
            def my_method(self, arg1, arg2):
                return arg1, arg2, str(datetime.now())
        instance = MyClass()
        self.assertNotEqual(
            instance.my_method(1, 2),
            instance.my_method(1, 2))

        # test cached version of same method
        class MyClass(object):
            @cache_in_instance()
            def my_method(self, arg1, arg2):
                return arg1, arg2, str(datetime.now())
        instance = MyClass()
        self.assertEqual(
            instance.my_method(1, 2),
            instance.my_method(1, 2))

        # different arguments should result in different values
        self.assertNotEqual(
            instance.my_method(2, 1),
            instance.my_method(3, 1))

        # there should now be three items in the cache
        self.assertEqual(len(instance.my_method.cache(instance)), 3)

    def test_cache_method_delete(self):

        class MyClass(object):
            @cache_in_instance()
            def my_method(self, arg1, arg2):
                return arg1, arg2, str(datetime.now())
        instance = MyClass()

        result1 = instance.my_method(1, 2)

        # deleting a non-existing key should be a no-op
        MyClass.my_method.cache_delete(instance, 10, 20)
        result2 = instance.my_method(1, 2)
        self.assertEqual(result1, result2)

        # deleting an existing key should force a new result
        MyClass.my_method.cache_delete(instance, 1, 2)
        result3 = instance.my_method(1, 2)
        self.assertEqual(result1, result2)
        self.assertNotEqual(result1, result3)

    def test_cache_method_clear(self):

        class MyClass(object):
            @cache_in_instance()
            def my_method1(self, arg1, arg2):
                return arg1, arg2, str(datetime.now())

            @cache_in_instance()
            def my_method2(self, arg1, arg2):
                return arg1, arg2, str(datetime.now())

        instance = MyClass()

        # create 10 cache entries for each test method
        args_list = [(n, n + 1) for n in range(10)]
        for a, b in args_list:
            instance.my_method1(a, b)
            instance.my_method2(a, b)
        _cache = instance._instance_cache
        self.assertEqual(len(_cache), 20)

        # my_method1.cache_clear() should remove only the my_method1 entries
        MyClass.my_method1.cache_clear(instance)
        self.assertEqual(len(_cache), 10)

        # my_method2.cache_clear() should remove what's left
        MyClass.my_method2.cache_clear(instance)
        self.assertEqual(len(_cache), 0)


class TestCacheInRequestDecorator(unittest.TestCase):
    """
    Test `lib.cache.cache_in_request` decorator.
    The most significant difference from `cache_in_instance`
    is the 'request' keyword.
    """

    def test_cache_with_kwarg_request(self):

        # test non-cached function for baseline behavior
        def testfunc(a, b, request=None):
            return a, b, str(datetime.now())
        request = HttpRequest()
        self.assertNotEqual(
            testfunc(1, 2, request=request),
            testfunc(1, 2, request=request))

        # test cached version of same function
        @cache_in_request()
        def testfunc(a, b, request=None):
            return a, b, str(datetime.now())
        request = HttpRequest()
        self.assertEqual(
            testfunc(1, 2, request=request),
            testfunc(1, 2, request=request))

        # different arguments should result in different values
        self.assertNotEqual(
            testfunc(2, 1, request=request),
            testfunc(3, 1, request=request))

        # there should now be three items in the cache
        self.assertEqual(len(testfunc.cache(request)), 3)


class TestRequestCache(unittest.TestCase):
    """
    Test `lib.cache.request_cache` function.
    It's just a convenient interface into a simple cache using
    the same dictionary as the `cache_in_request` decorator.
    """

    def test_request_cache(self):
        request = HttpRequest()

        # start with an empty cache
        self.assertIsNone(request_cache(request, 'testkey'))

        # initialize a cache value
        self.assertTrue(
            request_cache(request, 'testkey', 'testvalue'), 'testvalue')

        # should return the cached value now
        self.assertTrue(
            request_cache(request, 'testkey'), 'testvalue')

        # change the cached value
        self.assertTrue(
            request_cache(request, 'testkey', 'testvalue2'), 'testvalue2')
        self.assertTrue(
            request_cache(request, 'testkey'), 'testvalue2')
