import os
import json
from typing import Optional

from jphb.utils.file_utils import FileUtils


class ProjectModificationService:
    """
    This module is responsible for fixing specific issues in the projects.
    These issues are all in a way that are not general, and may not be used in other projects.

    For example, in the zipkin project, there is a dependency that is not compatible with the latest version of the package.
        - The package.json file in zipkin-ui has a dependency on bootstrap-sass with the version ^3.3.7.
        - Based on the documentations, the ^ symbol should be removed to make it compatible with the latest version.
    """

    def __init__(self, project_name: str, project_path: str, project_benchmark_path: Optional[str] = None) -> None:
        self.project_name = project_name
        self.project_path = project_path
        self.project_benchmark_path = project_benchmark_path

    def fix_issues(self) -> None:
        match self.project_name:
            case 'zipkin':
                self.__fix_bootstrap_saas_version()
            case 'Chronicle-Core' | 'jersey':
                self.__fix_jmh_main_class()
            case _:
                pass

    def __fix_bootstrap_saas_version(self) -> None:
        npm_package_json_path = os.path.join(self.project_path, 'zipkin-ui', 'package.json')
        if not FileUtils.is_path_exists(npm_package_json_path):
            return
        
        with open(npm_package_json_path, 'r') as file:
            data = json.load(file)
        
        # Update one of the dependencies
        if 'dependencies' in data and 'bootstrap-sass' in data['dependencies']:
            if '^' in data['dependencies']['bootstrap-sass']:
                data['dependencies']['bootstrap-sass'] = data['dependencies']['bootstrap-sass'].replace('^', '')

                with open(npm_package_json_path, 'w') as file:
                    json.dump(data, file, indent=4)

    def __fix_jmh_main_class(self) -> None:
        if self.project_benchmark_path is None:
            return

        pom_path = os.path.join(self.project_path, self.project_benchmark_path, 'pom.xml')
        if not FileUtils.is_path_exists(pom_path):
            return

        import xml.etree.ElementTree as ET
        tree = ET.parse(pom_path)
        root = tree.getroot()

        # Define the XML namespace
        ns = {'maven': 'http://maven.apache.org/POM/4.0.0'}

        # Find the maven-shade-plugin configuration
        shade_plugin = root.find(".//maven:plugin[maven:artifactId='maven-shade-plugin']", ns)

        if shade_plugin is None:
            return

        # Check and update the mainClass
        transformer = shade_plugin.find(".//maven:transformer[@implementation='org.apache.maven.plugins.shade.resource.ManifestResourceTransformer']", ns)
        if transformer is None:
            return

        main_class = transformer.find("maven:mainClass", ns)
        if main_class is None or main_class.text != "org.openjdk.jmh.Main":
            if main_class is None:
                main_class = ET.SubElement(transformer, "mainClass")
            main_class.text = "org.openjdk.jmh.Main"
            
            # Write the changes back to the file
            ET.register_namespace('', ns['maven'])
            tree.write(pom_path, encoding="utf-8", xml_declaration=True)