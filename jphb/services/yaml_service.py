from ruamel.yaml import YAML
import os

from typing import Optional, List


class Configuration:
    class Logging:
        def __init__(self, level: Optional[str] = None, file: Optional[str] = None, add_timestamp_to_file_names: bool = False):
            self.level = level
            self.file = file
            self.add_timestamp_to_file_names = add_timestamp_to_file_names

    class TargetMethods:
        def __init__(self, instrument: Optional[List[str]] = None, ignore: Optional[List[str]] = None):
            self.instrument = instrument
            self.ignore = ignore

    def __init__(self, logging: Optional['Configuration.Logging'] = None, instrumentation: Optional['Configuration.Instrumentation'] = None):
        self.logging = logging
        self.instrumentation = instrumentation

    class Instrumentation:
        def __init__(self, target_package: Optional[str] = None, target_methods: Optional['Configuration.TargetMethods'] = None, only_visisted: bool = False, instrument_main_method: bool = False):
            self.target_package = target_package
            self.target_methods = target_methods
            self.only_visisted = only_visisted
            self.instrument_main_method = instrument_main_method


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
            'addTimestampToFileNames': data.add_timestamp_to_file_names
        })

    def instrumentation_representer(self, dumper, data):
        return dumper.represent_dict({
            'targetPackage': data.target_package,
            'targetMethods': data.target_methods,
            'onlyCheckVisited': data.only_visisted,
            'instrumentMainMethod': data.instrument_main_method
        })

    def target_methods_representer(self, dumper, data):
        return dumper.represent_dict({
            'instrument': data.instrument,
            'ignore': data.ignore,
        })

    def create_yaml(self,
                    log_file: str,
                    target_package: str,
                    instrument: List[str],
                    ignore: List[str],
                    yaml_file: str,
                    add_timestamp_to_file_names: bool = False,
                    only_visited: bool = False,
                    instrument_main_method: bool = False):
        yaml = YAML()

        yaml.representer.add_representer(Configuration, self.config_representer)
        yaml.representer.add_representer(
            Configuration.Logging, self.logging_representer)
        yaml.representer.add_representer(
            Configuration.Instrumentation, self.instrumentation_representer)
        yaml.representer.add_representer(
            Configuration.TargetMethods, self.target_methods_representer)
        
        # If directory does not exist, create it
        os.makedirs(os.path.dirname(yaml_file), exist_ok=True)

        # Create and populate Configuration instance
        config = Configuration(
            logging=Configuration.Logging(level='fine', file=log_file, add_timestamp_to_file_names=add_timestamp_to_file_names),
            instrumentation=Configuration.Instrumentation(
                target_package=target_package,
                target_methods=Configuration.TargetMethods(
                    instrument=instrument,
                    ignore=ignore
                ),
                only_visisted=only_visited,
                instrument_main_method=instrument_main_method
            )
        )

        # Convert Configuration instance to YAML
        with open(yaml_file, 'w') as f:
            yaml.dump(config, f)
