from components.api.tool_router import _get_unknown_config_fields


class TestGetUnknownConfigFields:
    def test_nested_dict(self):
        parsed_config = {"one": {"two": {"existing_key1": "value1"}}}
        user_passed_config = {
            "one": {"two": {"existing_key1": "value1", "nonexisting_key1": "value2"}}
        }
        expected_fields = ["one.two.nonexisting_key1"]

        gotten_fields = _get_unknown_config_fields(
            user_passed_config=user_passed_config, parsed_config=parsed_config
        )

        assert gotten_fields == expected_fields

    def test_nested_list(self):
        parsed_config = {"one": {"two": [{"existing_key1": "value1"}]}}
        user_passed_config = {
            "one": {"two": [{"existing_key1": "value1", "nonexisting_key1": "value2"}]}
        }
        expected_fields = ["one.two[0].nonexisting_key1"]

        gotten_fields = _get_unknown_config_fields(
            user_passed_config=user_passed_config, parsed_config=parsed_config
        )

        assert gotten_fields == expected_fields

    def test_toplevel_key(self):
        parsed_config = {"one": {"two": "value"}}
        user_passed_config = {"one": {"two": "value"}, "nonexisting_key1": "value1"}
        expected_fields = ["nonexisting_key1"]

        gotten_fields = _get_unknown_config_fields(
            user_passed_config=user_passed_config, parsed_config=parsed_config
        )

        assert gotten_fields == expected_fields
