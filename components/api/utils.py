# should be fine to modify this example config, but modification must pass ToolConfig validation
EXAMPLE_CONFIG = """
config_version: v1beta1
components:
    example_component:
        build: # similar builds service options: "toolforge build start <repository> --ref <ref>"
            ref: <string>
            repository: <string>
        component_type: continuous
        run: # similar jobs service options: "toolforge jobs run --command <command>"
            command: <string>
"""
