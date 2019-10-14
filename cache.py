import logging
from inspect import getargspec, getcallargs, isfunction

from decorator import decorator

try:
    from django.conf import settings
    from django.core.cache import cache as CACHE
    TTL = getattr(settings, 'CACHE_DEFAULT_TTL', 900)
    LOGGER_PREFIX = getattr(settings, 'LOGGER_PREFIX', '')
    DEBUG_LOG = __name__ in getattr(settings, 'DEBUG_LOG', '')
except ImportError:
    from .simplecache import Cache
    CACHE = Cache()
    TTL = 0  # TTL is ignored in the simplecache
    LOGGER_PREFIX = ''
    DEBUG_LOG = False

logger = logging.getLogger(LOGGER_PREFIX + __name__)

if DEBUG_LOG:
    def log(*args, **kwargs):
        logger.debug(*args, **kwargs)
else:
    def log(*args, **kwargs):
        pass


def prefix(func):
    """
    A cachekey helper function. Return a prefix which is unique for a function,
    classmethod, or instance method.

    Caution: When used with staticmethods, the parent class name cannot be
    returned so there may be prefix collisions with another similarly-named
    function or class staticmethod defined with the same module.
    """
    cached_prefix = getattr(func, '_prefix', False)
    if cached_prefix:
        return cached_prefix

    _classname = classname(func)
    if _classname:
        _classname = '.' + _classname

    _module = func.__module__ or ''

    return _module + _classname + ':' + func.__name__ + ':'


def classname(func):
    """
    A cachekey helper function. If the argument value is an instance method
    or classmethod, return the parent class name, otherwise return an empty
    string.
    """
    if isfunction(func):
        return ''
    try:
        return getattr(func.__self__, '__name__', func.im_class.__name__)
    except AttributeError:
        return ''


def arguments(func, *args, **kwargs):
    """
    A cachekey helper function. Collect the arguments passed into a function
    and return as a single list.

    The `decorator` function already merges all keyword arguments into `args`
    (including any default values) so `kwargs` is primarily retained to ease
    calls from outside the decorated function.
    """
    arglist = getattr(func, '_arglist', False)
    if not arglist:
        arglist = getargspec(func).args
    if len(args) == len(arglist):
        return list(args)
    callargs = getcallargs(func, *args, **kwargs)
    return [callargs.get(arg) for arg in arglist]


def cachekey(func, *args, **kwargs):
    """
    Return a cache key which is unique for a function call, including arguments.

    The default cachekey implementation just ignores the instance argument.
    Alternative cachekey implementations may use the instance to add
    additional instance variable values to the key.
    """
    args2 = arguments(func, *args, **kwargs)

    # ignoring `instance`
    instance_index = getattr(func, '_instance_index', False)
    if instance_index is not False:
        args2.pop(instance_index)

    return prefix(func) + str(args2)


def cachekey_static(func, *args, **kwargs):
    """
    Return a cache key which is unique for a function, not including arguments.

    Optionally, add a `cachekey` keyword argument to function to create multiple
    cache buckets for the same function.
    """
    return prefix(func) + kwargs.get('cachekey', '')


def cachekey_request_user_ip(func, *args, **kwargs):
    """
    Return a cache key containing the user id and remote IP address from
    the current `request`.

    The fastest response assumes the request object is the first argument
    in the function call. If that assumption fails, we fall back on searching
    for `request` with `inspect.getcallargs`. Either way the calculation
    is still very fast but a quick benchmark suggests that the fast response
    can be about 16 times quicker.
    """
    try:
        args2 = (args[0].user.id, args[0].META['REMOTE_ADDR'])
    except AttributeError:
        callargs = getcallargs(func, *args, **kwargs)
        request = callargs.get('request', args[0])
        args2 = (request.user.id, request.META['REMOTE_ADDR'])
    return prefix(func) + str(args2)


def cache(seconds=TTL, _cache=CACHE, _key=cachekey, _marker=None):
    """
    Function decorator to cache the result in a cache (by default, the Django
    default cache) for the given number of seconds.

    The function result should only depend on its parameters and all
    parameters should be hashable (at least for the default key function).

    To signal a non-cacheable result, either the cachekey function or the
    decorated function can return a do-not-cache `_marker`.

    To delete a specific cache entry, call `cache_delete` with the same
    function arguments used to generate the cachekey:

        func.cache_delete(*args, **kwargs)

    To delete all the cache entries for this function:

        func.cache_clear()  # requires a custom backend `clear_prefix` method

    Caution: The RedisCache performance impact of deleting a very large number
    of keys via `func.cache_delete` is unknown. You may need to split up large
    deletes into batches. See `clear_prefix` implementation for an example.

    The cache backend interface is also directly accessible via `func.cache`.
    """
    def _decorator(func):
        func._arglist = getargspec(func).args
        func._prefix = prefix(func)

        def cache_delete(*args, **kwargs):
            key = _key(func, *args, **kwargs)
            log('cleared cache value for %s key', key)
            _cache.delete(key)

        def cache_clear():
            if hasattr(_cache, 'delete_pattern'):
                _cache.delete_pattern(func._prefix + '*')
            elif hasattr(_cache, 'clear_prefix'):
                _cache.clear_prefix(func._prefix)

        def wrapper(func, *args, **kwargs):
            key = _key(func, *args, **kwargs)
            if key is _marker:
                log('skipped cache check for %s key', key)
                return func(*args, **kwargs)
            result = _cache.get(key, _marker)
            if result is _marker:
                log('calculated a new value for %s key', key)
                result = func(*args, **kwargs)
                if result is not _marker:
                    _cache.set(key, result, seconds)
            else:
                log('obtained the cached value for %s key', key)
            return result

        newfunc = decorator(wrapper, func)
        newfunc.cache = _cache
        newfunc.cache_delete = cache_delete
        newfunc.cache_clear = cache_clear
        newfunc._arglist = func._arglist
        newfunc._prefix = func._prefix
        return newfunc

    return _decorator


def cache_in_instance(_instance='instance', _key=cachekey, _marker=None):
    """
    Instance method memoize decorator to cache the result during the lifetime
    of the current class instance. This gives us a more generalized version
    of Django's `cached_property` decorator that can be be used for instance
    methods with parameters that should be included in the cache key.

    This decorator can also be used to cache the result of a function
    which includes the relevant class instance as the first argument or
    as a keyword argument by default named 'instance'.

    The method or function result should only depend on its parameters
    (except for `instance`), and all parameters (except for 'instance')
    should be hashable (at least for the default key function). If there
    are instance variables that should be included in the cache key, then
    those variables should be added to the function argument list or added
    to a custom `_key` function.

    To signal a non-cacheable result, either the cachekey function or the
    decorated method or function can return a do-not-cache `_marker`.
    Also, no caching will occur if the instance passed into the decorated
    function or method is None.

    Usage (method):

        class MyClass(object):
            @cache_in_instance()
            def my_method(self, arg1, arg2):
                ...
                return value

        To delete a single cache entry:
            MyClass.my_method.cache_delete(self, arg1, arg2)

        To clear the instance cache:
            MyClass.my_method.cache_clear(self)

    Usage (function):

        @cache_in_instance()
        def my_function(instance, arg1, arg2):
            ...
            return value

        @cache_in_instance()
        def my_function_with_kwarg_instance(arg1, arg2, instance=instance):
            ...
            return value

        To delete a single cache entry:
            my_function.cache_delete(instance, arg1, arg2)

        To clear the instance cache:
            my_function.cache_clear(instance)

    """
    def get_instance_cache(instance):
        if instance is None:
            return {}
        if not hasattr(instance, '_instance_cache'):
            instance._instance_cache = {}
        return instance._instance_cache

    def _decorator(func):

        # `decorator` function merges all keyword arguments into 'args'
        # list so `instance` value may be anywhere in the list
        arglist = getargspec(func).args
        instance_index = 0
        if _instance in arglist:
            instance_index = arglist.index(_instance)

        func._instance_index = instance_index
        func._instance_name = _instance
        func._arglist = arglist
        func._prefix = prefix(func)

        def cache_delete(instance, *args, **kwargs):
            cache = get_instance_cache(instance)
            args = [instance] + list(args)
            key = _key(func, *args, **kwargs)
            log('cleared cache value for %s key', key)
            cache.pop(key, None)

        def cache_clear(instance):
            cache = get_instance_cache(instance)
            key_prefix = prefix(func)
            keys = [k for k in cache.keys() if k.startswith(key_prefix)]
            for key in keys:
                log('cleared cache value for %s key', key)
                cache.pop(key, None)

        def wrapper(func, *args, **kwargs):
            cache = get_instance_cache(args[instance_index])
            key = _key(func, *args, **kwargs)
            if key is _marker:
                log('skipped cache check for %s key', key)
                return func(*args, **kwargs)
            if key in cache:
                log('obtained the cached value for %s key', key)
                return cache[key]
            log('calculated a new value for %s key', key)
            result = func(*args, **kwargs)
            if result is not _marker:
                cache[key] = result
            return result

        newfunc = decorator(wrapper, func)
        newfunc.cache = lambda i: get_instance_cache(i)
        newfunc.cache_delete = cache_delete
        newfunc.cache_clear = cache_clear
        newfunc._instance_index = instance_index
        newfunc._instance_name = _instance
        newfunc._arglist = func._arglist
        newfunc._prefix = func._prefix
        return newfunc

    return _decorator


def cache_in_request(_key=cachekey, _marker=None):
    """
    Convenience wrapper around `cache_in_instance` to cache result of
    decorated function into the current request. The request instance
    must be passed into the function as the first argument or as a keyword
    argument named 'request'.

    See `cache_in_instance` for usage.
    """
    return cache_in_instance(_instance='request', _key=_key, _marker=_marker)


def request_cache(request, key, value=None):
    """
    A simple request cache using the same cache dictionary as the
    `cache_in_request` decorator. Pass in `value` to set a cached
    value for the given key during the lifetime of the request.
    """
    if not hasattr(request, '_instance_cache'):
        request._instance_cache = {}
    cache = request._instance_cache
    key = 'ncc.cache:request_cache:' + key
    if value is not None:
        cache[key] = value
        return value
    return cache.get(key)
