import functools
import warnings


def send_deprecation_warning(message: str):
    warnings.warn(message, category=DeprecationWarning, stacklevel=2)


def deprecated(custom_message=None):
    """Decorator to mark functions or classes as deprecated with an optional custom message.
    It will emit a warning when the function or class is used."""

    def decorator(obj):
        if isinstance(obj, type):  # Check if it's a class
            # Class deprecation
            orig_init = obj.__init__

            @functools.wraps(orig_init)
            def new_init(self, *args, **kwargs):
                message = custom_message if custom_message else f"Call to deprecated class {obj.__name__}."
                send_deprecation_warning(message)
                orig_init(self, *args, **kwargs)

            obj.__init__ = new_init
            return obj
        else:
            # Function deprecation
            @functools.wraps(obj)
            def new_func(*args, **kwargs):
                message = custom_message if custom_message else f"Call to deprecated function {obj.__name__}."
                send_deprecation_warning(message)
                return obj(*args, **kwargs)

            return new_func

    return decorator


def singleton(cls):
    """
    A singleton decorator. Returns a wrapper objects. A call on that object
    returns a single instance object of decorated class. Use the __wrapped__
    attribute to access decorated class directly in unit tests
    """

    cls.__INSTANCE__ = None

    def singleton_new(singleton_cls):
        if cls.__INSTANCE__ is None:
            # If no instance exists yet, create one
            cls.__INSTANCE__ = super(cls, cls).__new__(cls)
        # Return the single instance
        return cls.__INSTANCE__

    cls.__new__ = singleton_new

    return cls
