import os
import json

from jphb.utils.file_utils import FileUtils


class ProjectModificationService:
    """
    This module is responsible for fixing specific issues in the projects.
    These issues are all in a way that are not general, and may not be used in other projects.

    For example, in the zipkin project, there is a dependency that is not compatible with the latest version of the package.
        - The package.json file in zipkin-ui has a dependency on bootstrap-sass with the version ^3.3.7.
        - Based on the documentations, the ^ symbol should be removed to make it compatible with the latest version.
    """

    def __init__(self, project_name: str, project_path: str) -> None:
        self.project_name = project_name
        self.project_path = project_path

    def fix_issues(self) -> None:
        if self.project_name == 'zipkin':
            self.__fix_zipkin_issues()

    def __fix_zipkin_issues(self) -> None:
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