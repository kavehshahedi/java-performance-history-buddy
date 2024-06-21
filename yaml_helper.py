from ruamel.yaml import YAML

from typing import Optional, List


class Configuration:
    class Logging:
        def __init__(self, level: Optional[str] = None, file: Optional[str] = None):
            self.level = level
            self.file = file

    class TargetMethods:
        def __init__(self, instrument: Optional[List[str]] = None, ignore: Optional[List[str]] = None):
            self.instrument = instrument
            self.ignore = ignore

    def __init__(self, logging: Optional['Configuration.Logging'] = None, instrumentation: Optional['Configuration.Instrumentation'] = None):
        self.logging = logging
        self.instrumentation = instrumentation

    class Instrumentation:
        def __init__(self, target_package: Optional[str] = None, target_methods: Optional['Configuration.TargetMethods'] = None):
            self.target_package = target_package
            self.target_methods = target_methods


class YamlCreator:

    def __init__(self):
        pass

    def config_representer(self, dumper, data):
        return dumper.represent_dict({
            'logging': data.logging,
            'instrumentation': data.instrumentation,
        })

    def logging_representer(self, dumper, data):
        return dumper.represent_dict({
            'level': data.level,
            'file': data.file,
        })

    def instrumentation_representer(self, dumper, data):
        return dumper.represent_dict({
            'target_package': data.target_package,
            'target_methods': data.target_methods,
        })

    def target_methods_representer(self, dumper, data):
        return dumper.represent_dict({
            'instrument': data.instrument,
            'ignore': data.ignore,
        })

    def create_yaml(self, log_file: str, target_package: str, instrument: List[str], ignore: List[str], yaml_file: str):
        yaml = YAML()

        yaml.representer.add_representer(Configuration, self.config_representer)
        yaml.representer.add_representer(
            Configuration.Logging, self.logging_representer)
        yaml.representer.add_representer(
            Configuration.Instrumentation, self.instrumentation_representer)
        yaml.representer.add_representer(
            Configuration.TargetMethods, self.target_methods_representer)

        # Create and populate Configuration instance
        config = Configuration(
            logging=Configuration.Logging(level='fine', file=log_file),
            instrumentation=Configuration.Instrumentation(
                target_package=target_package,
                target_methods=Configuration.TargetMethods(
                    instrument=instrument,
                    ignore=ignore
                )
            )
        )

        # Convert Configuration instance to YAML
        with open(yaml_file, 'w') as f:
            yaml.dump(config, f)
