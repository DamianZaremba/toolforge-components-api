import pytest


def cases(params_str, *params_defs):
    """Simple wrapper around parametrize to add test titles in a more readable way.

    Use like:
    >>> @cases(
    >>>     "param1,param2",
    >>>     ["Test something", ["param1value1", "param2value1"]],
    >>>     ["Test something else", ["param1value2", "param2value2"]],
    >>> )
    >>> def test_mytest(param1, param2):
    >>>     ...

    So it shows in pytest like:
    ```
    tests/test_this_file.py::test_mytest[Test something] PASSED
    tests/test_this_file.py::test_mytest[Test something else] PASSED
    ```
    """
    test_names = [name for name, _ in params_defs]
    test_params = [params for _, params in params_defs]
    print(f"Parametrizing with: {params_str}\n{test_params}\nids={test_names}")

    def wrapper(func):
        return pytest.mark.parametrize(params_str, test_params, ids=test_names)(func)

    return wrapper
