from threading import local


_thread_local = local()


def set_current_user(user):
    _thread_local.user = user


def get_current_user():
    return getattr(_thread_local, "user", None)


def clear_current_user():
    if hasattr(_thread_local, "user"):
        delattr(_thread_local, "user")
