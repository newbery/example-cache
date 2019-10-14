

class Cache(object):
    """
    The cache decorator expects the following interface from the _cache
    backend, which is supported by the default Django cache, with one
    addition; the `clear_prefix` method which deletes only those entries
    matching the current backend `key_prefix` plus the decorated function
    `prefix` (the standard `clear` method clears *all* keys which is not
    usually what we want). If the `clear_prefix` method is missing, the
    decorator function `func.cache_clear()` will just be a no-op.

    Note that cache expiry is not implemented in this class. Any expiry
    value passed in will be ignored. So this is mostly for very transient
    caches as otherwise we risk blowing up the memory requirements.
    
    TODO: This should probably be reimplemented using the MutableMapping
    abstract class but as it's only used for testing purposes right now,
    converting this is not high-priority.
    """

    def __init__(self, version=1, key_prefix=''):
        self._cache = {}
        self.version = version
        self.key_prefix = key_prefix

    def make_key(self, key, version=None):
        version = version or self.version
        return '%s:%s:%s' % (self.key_prefix, version, key)

    def get(self, key, default=None):
        return self._cache.get(self.make_key(key), default)

    def set(self, key, value, seconds):
        self._cache[self.make_key(key)] = value

    def delete(self, key):
        _key = self.make_key(key)
        if _key in self._cache:
            del self._cache[_key]

    def delete_many(self, *keys):
        for key in keys:
            self.delete(key)

    def clear_prefix(self, prefix):
        if prefix:
            prefix = self.make_key(prefix)
            for key in self._cache.keys():
                if key.startswith(prefix):
                    del self._cache[key]
