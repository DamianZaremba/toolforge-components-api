from typing import Any


def matches_query(matches: dict[str, Any], config: dict[str, Any]) -> bool:
    """This function gets a dict with key strings and values, and returns if all of them match inside the given config. For example:

    query = {
        "key1.key2[].key3": "value1",
        "key1.key4": True,
    }

    Will match:
    {
        "key1": {
            "key2": [
                {"key3": "value1"},
            ]
            "key4": True,
        },
    }


    But not:
    {
        "key1": {
            "key2": [
                {"key3": "value2"},
            ]
            "key4": True,
        },
    }
    """
    return all(
        _path_matches(
            obj=config, keys_parts=keys_spec.split("."), expected_value=expected_value
        )
        for keys_spec, expected_value in matches.items()
    )


def _path_matches(obj: Any, keys_parts: list[str], expected_value: Any) -> bool:
    """Recursive is ok, as we don't expect to have very nested configs."""
    if not keys_parts:
        return bool(obj == expected_value)

    part = keys_parts[0]
    remaining = keys_parts[1:]

    if part.endswith("[]"):
        key = part[:-2]

        if not isinstance(obj, dict):
            return False

        value = obj.get(key)

        if not isinstance(value, list):
            return False

        return any(_path_matches(item, remaining, expected_value) for item in value)

    if not isinstance(obj, dict) or part not in obj:
        return False

    return _path_matches(obj[part], remaining, expected_value)
