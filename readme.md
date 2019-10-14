# Generalized cache decorator

**DEPRECATED**: This is no longer recommended for general use. I will
probably re-implement what I need from this on top of the excellent
[cachetools](https://pypi.org/project/cachetools/) library.

I'll leave this version here as example code for discussion and presentation
purposes.

Requires https://pypi.org/project/decorator

The motivation for this code was a desire to create an alternative version of
a Django-style cache interface providing consistent caching semantics for
multiple usecases and supporting arbitrary caching backends.

I also wanted to use it in the classic memoization style where I could just
apply a decorator to any function or method, and have it auto-generate cache
keys based on the call argument signature.

The result worked very well and helped me to quickly address some performance
bottlenecks in legacy code until I could get around to refactoring to clean
things up.

Note that as-is, this code is potentially not thread-safe or multiprocess-safe.
If this is a potential issue, you may need to implement some proper locking.

The Python 3.2+ standard library now has built-in support for an lru_cache
decorator (also available as a backport for Python >=2.6) which should probably
be considered as an alternative if you are looking for similar functionality
although it only supports an in-memory cache attached to the decorated function.

Or even better, check out [cachetools](https://pypi.org/project/cachetools/)
