from types import NoneType
from typing import Tuple, Union
from git import Commit, Repo
import os
import subprocess
import time
import re
import json
import xml.etree.ElementTree as ET

from yaml_helper import YamlCreator


class BenchmarkExecutor:

    def __init__(self, project_name: str, project_path: str) -> None:
        self.project_name = project_name
        self.project_path = project_path

        self.repo = Repo(self.project_path)

    def execute(self, project_benchmark_directory: str, commits: list[str], required_dependencies: list[dict] = []) -> None:
        """
        Execute the benchmarks for the given project
        Steps:
            1. Checkout the commit
            2. Modify the pom.xml file to check Java compiling version (update to 17 if it is 6 or less)
            3. Add required dependencies to the project's pom.xml file
            4. Check whether the project is buildable (i.e., build the project)
            5. Build the benchmarks
            6. Get the list of benchmarks
            7. Get the target methods for each benchmark (i.e., the aim is to find the benchmarks that target the methods that are changed in the commit)
            8. For the candidate benchmarks, create a YAML file that contains the configuration for the Java instrumentation agent
            9. Execute the benchmarks with the Java instrumentation agent
            10. Collect the results

        Args:
            project_benchmark_directory (str): The directory where the benchmarks are located
            commits (list[Commit]): The list of commits to be executed
            required_dependencies (list[dict], optional): The list of required dependencies to be added to the project's pom.xml file. Defaults to [].
        """

        for commit in commits:

            start_time = time.time()

            # Checkout the commit
            self.repo.git.checkout(commit, force=True)
            commit = self.repo.commit(commit)

            # Modify the pom.xml file to check Java compiling version
            ucv = self.__update_compile_version(self.project_path, commit, 11)
            if not ucv:
                print(f'{commit.hexsha} can\'t update compile version')
                continue

            ard = self.__add_required_dependencies(self.project_path, required_dependencies)
            if not ard:
                print(f'{commit.hexsha} can\'t add required dependencies')
                continue

            # Check whether the project is buildable
            is_buildable = self.__is_project_buildable(self.project_path)
            if not is_buildable:
                print(f'{commit.hexsha} is not buildable')
                continue

            benchmark = self.__build_benchmarks(self.project_path, project_benchmark_directory)
            if not benchmark:
                print(f'{commit.hexsha} can\'t build benchmarks')
                continue

            benchmark_jar_path, list_of_benchmarks = self.__get_list_of_benchmarks(self.project_path, project_benchmark_directory)
            if not list_of_benchmarks:
                print(f'{commit.hexsha} can\'t get list of benchmarks')
                continue

            target_methods = []
            for benchmark in list_of_benchmarks:
                tm = self.__get_target_methods(self.project_path, 'org.HdrHistogram', commit.hexsha, benchmark_jar_path, benchmark)
                if not tm:
                    print(f'{commit.hexsha} can\'t get target methods')
                    continue

                target_methods.extend(tm)

            is_targeting, targets = self.__is_benchmark_targeting_changed_methods(self.project_name, commit.hexsha, target_methods)
            if is_targeting:
                print(f'{commit.hexsha} is targeting changed methods with {len(targets)} methods')
                YamlCreator().create_yaml(
                    log_file=f'{self.project_name}_{commit.hexsha}.log',
                    target_package='org.HdrHistogram',
                    instrument=targets,
                    ignore=[],
                    yaml_file=f'{self.project_name}_{commit.hexsha}_config.yaml'
                )

            print(f'{commit.hexsha} took {time.time() - start_time} seconds')

    def __is_project_buildable(self, project_path: str) -> bool:
        process = subprocess.run([
            'mvn',
            'clean',
            'install',
            '-DskipTests',
            '-Dmaven.javadoc.skip=true',
            '-Dcheckstyle.skip=true',
            '-Denforcer.skip=true'
        ], cwd=project_path, capture_output=False, shell=True)

        if process.returncode != 0:
            return False

        return True

    def __build_benchmarks(self, project_path: str, benchmark_directory: str) -> bool:
        process = subprocess.run([
            'mvn',
            'clean',
            'package'
        ], cwd=os.path.join(project_path, benchmark_directory), capture_output=False, shell=True)

        if process.returncode != 0:
            return False

        return True

    def __get_list_of_benchmarks(self, project_path: str, benchmark_directory: str) -> Tuple[str, list[str]]:
        benchmark_jar_path = None
        for root, dirs, files in os.walk(os.path.join(project_path, benchmark_directory)):
            for file in files:
                if file.endswith('.jar'):
                    if 'shade' in file or 'original' in file or 'sources' in file or 'javadoc' in file or 'tests' in file or 'test' in file:
                        continue
                    benchmark_jar_path = os.path.join(root, file)
                    break

        if not benchmark_jar_path:
            return '', []

        process = subprocess.run([
            'java',
            '-jar',
            benchmark_jar_path,
            '-l'
        ], capture_output=True, shell=True)

        if process.returncode != 0:
            return '', []

        return benchmark_jar_path, [line.strip() for line in process.stdout.decode('utf-8').strip().splitlines()[1:]]

    def __get_target_methods(self, project_path: str, project_package: str, commit_id: str, benchmark_jar_path: str, benchmark_name: str) -> Union[NoneType, list[str]]:
        log_path = os.path.join('results', self.project_name,
                                commit_id, f'visited_{benchmark_name}.log')
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

        if os.path.exists(log_path):
            # Remove the log file
            os.remove(log_path)

        process = subprocess.run([
            'java',
            '-Dlog4j2.contextSelector=org.apache.logging.log4j.core.async.AsyncLoggerContextSelector',
            f'-javaagent:java-instrumentation-agent-1.0.jar=package={project_package},onlyCheckVisited=true,logFileName={log_path}',
            '-jar',
            benchmark_jar_path,
            '-f', '1',
            '-wi', '0',
            '-i', '1',
            '-r', '1',
            benchmark_name
        ], capture_output=True, shell=True)

        if process.returncode != 0:
            return None

        target_methods = set()

        # Read the log file
        with open(os.path.join(log_path), 'r') as f:
            for line in f:
                target_methods.add(
                    ' '.join(line.strip().split(' ')[2:]).split('(')[0].strip())

        return list(target_methods)

    def __is_benchmark_targeting_changed_methods(self, project_name: str, commit_id: str, target_functions: list[str]) -> Tuple[bool, list[str]]:
        changed_methods_path = os.path.join(
            'results', project_name, commit_id, 'method_changes.json')
        if not os.path.exists(changed_methods_path):
            return False, []

        with open(changed_methods_path, 'r') as f:
            changed_methods = json.load(f)

        chosen_methods = set()

        for changes in list(changed_methods.values()):
            for method in changes['methods']:
                # method = method.split('(')[0].strip()

                if method.split('(')[0].strip() in target_functions:
                    chosen_methods.add(method)

        return len(chosen_methods) > 0, list(chosen_methods)

    def __update_compile_version(self, project_path: str, commit: Commit, version: int) -> bool:
        # Iterate through all files
        for root, dirs, files in os.walk(project_path):
            for file in files:
                if file.endswith('pom.xml'):
                    pom_path = os.path.join(root, file)  # type: ignore
                    with open(pom_path, 'r') as f:
                        pom_content = f.read()

                    # Update source and target version only for maven-compiler-plugin
                    try:
                        # Remove the namespace
                        pom_content = re.sub(
                            r'\sxmlns="[^"]+"', '', pom_content, count=1)

                        root = ET.fromstring(pom_content)

                        for plugin in root.findall('.//plugin'):
                            for artifact_id in plugin.findall('artifactId'):
                                if artifact_id.text == 'maven-compiler-plugin':
                                    for configuration in plugin.findall('configuration'):
                                        for source in configuration.findall('source'):
                                            if source.text == '1.6':
                                                source.text = str(version)
                                        for target in configuration.findall('target'):
                                            if target.text == '1.6':
                                                target.text = str(version)

                        with open(pom_path, 'w') as f:
                            f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
                            f.write(ET.tostring(root, encoding='utf-8').decode('utf-8'))

                    except Exception as e:
                        print(e)
                        return False

        return True

    def __add_required_dependencies(self, project_path: str, dependencies: list[dict]) -> bool:
        # Iterate through all files
        for root, dirs, files in os.walk(project_path):
            for file in files:
                if file.endswith('pom.xml'):
                    pom_path = os.path.join(root, file)
                    with open(pom_path, 'r') as f:
                        pom_content = f.read()

                    for dependency in dependencies:
                        if f'<dependency>\n\t\t<groupId>{dependency["group_id"]}</groupId>\n\t\t<artifactId>{dependency["artifact_id"]}</artifactId>\n\t\t<version>{dependency["version"]}</version>\n\t</dependency>' in pom_content:
                            continue

                        try:
                            pom_content = re.sub(
                                r'</dependencies>', f'<dependency>\n\t\t<groupId>{dependency["group_id"]}</groupId>\n\t\t<artifactId>{dependency["artifact_id"]}</artifactId>\n\t\t<version>{dependency["version"]}</version>\n\t</dependency>\n</dependencies>', pom_content)
                            with open(pom_path, 'w') as f:
                                f.write(pom_content)
                        except Exception as e:
                            print(e)
                            return False

        return True
