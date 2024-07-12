from types import NoneType
from typing import Optional, Tuple, Union
from git import Commit, Repo
import os
import shutil
import subprocess
import re
import requests
import json
import time
import xml.etree.ElementTree as ET

from yaml_helper import YamlCreator

from mhm.utils.file_utils import FileUtils
from performance_analysis import PerformanceAnalysis

GIT_TOKEN = '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'

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class BenchmarkExecutor:

    def __init__(self, project_name: str, project_path: str) -> None:
        self.project_name = project_name
        self.project_path = project_path

        self.repo = Repo(self.project_path)

    def execute(self, jmh_dependency: dict, current_commit_hash: str, previous_commit_hash: str,
                changed_methods: list[str], target_package: str, git_info: dict,
                required_dependencies: list[dict] = [],
                custom_commands: Optional[dict] = None) -> Tuple[bool, Optional[dict]]:
        """
        Execute the benchmarks for the given project
        Steps:
            1. Checkout the commit
            2. Modify the pom.xml file to check Java compiling version (update to 17 if it is 6 or less)
            3. Add required dependencies to the project's pom.xml file (optional)
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

        # Variables
        project_benchmark_directory = jmh_dependency['benchmark_directory']
        if custom_commands and "benchmark" in custom_commands and "cwd" in custom_commands["benchmark"]:
            project_benchmark_directory = custom_commands["benchmark"]["cwd"]
        project_benchmark_name = jmh_dependency['benchmark_name']
        previous_benchmark_hash = ""
        is_prev_benchmark_built = True
        is_current_benchmark_built = True
        has_same_benchmarks = False

        for commit_hash in [previous_commit_hash, current_commit_hash]:
            print(f"Checking out to {'current' if commit_hash == current_commit_hash else 'previous'} commit...")

            # Checkout the commit
            self.repo.git.checkout(commit_hash, force=True)
            commit = self.repo.commit(commit_hash)

            print("Checking if benchmark has previously executed...")
            has_benchmark_executed, benchmark_history, benchmark_hash = self.__has_benchmark_previously_executed(commit, project_benchmark_directory)
            print('\tYes' if has_benchmark_executed else '\tNo', benchmark_hash)

            has_same_benchmarks = (previous_benchmark_hash != "" and previous_benchmark_hash == benchmark_hash)

            # # Modify the pom.xml file to check Java compiling version
            # print("Updating compile version...")
            # ucv = self.__update_compile_version(self.project_path, commit, "11")
            # if not ucv:
            #     print(f'{commit.hexsha} can\'t update compile version')
            #     return False, None

            # print("Adding required dependencies...")
            # ard = self.__add_required_dependencies(self.project_path, required_dependencies)
            # if not ard:
            #     print(f'{commit.hexsha} can\'t add required dependencies')
            #     return False, None

            # Check whether the project is buildable
            print("Checking if project is buildable...")
            is_buildable = self.__is_project_buildable(project_path=self.project_path, owner=git_info['owner'],
                                                       build_anyway=(commit_hash == current_commit_hash),
                                                       repo_name=git_info['repo'], commit_sha=commit.hexsha)
            if not is_buildable:
                print(f'{bcolors.FAIL}Project in {commit.hexsha} is not buildable{bcolors.ENDC}')
                return False, None
            
            print(f"{bcolors.OKGREEN}Project in {commit.hexsha} is buildable{bcolors.ENDC}")

            print("Building benchmarks...")
            benchmark = self.__build_benchmarks(self.project_path, project_benchmark_directory, 
                                                commit_hash, build_anyway=(commit_hash == current_commit_hash),
                                                custom_command = custom_commands["benchmark"] if custom_commands and "benchmark" in custom_commands else None)
            if not benchmark:
                if commit_hash == current_commit_hash:
                    is_prev_benchmark_built = False
                else:
                    is_current_benchmark_built = False

                print(f'{bcolors.FAIL}Can\'t build benchmarks for {"current" if commit_hash == current_commit_hash else "previous"} commit{bcolors.ENDC}')
            print(f'{bcolors.OKGREEN}{"Current" if commit_hash == current_commit_hash else "Previous"} commit benchmarks are built{bcolors.ENDC}')

            previous_benchmark_hash = benchmark_hash

        # If both benchmarks are not built, return    
        if not is_prev_benchmark_built and not is_current_benchmark_built:
            print(f'Both benchmarks are not built')
            return False, None
        
        if is_prev_benchmark_built:
            if has_same_benchmarks and is_current_benchmark_built:
                commit_to_use_for_benchmark = current_commit_hash
            else:
                commit_to_use_for_benchmark = previous_commit_hash
        else:
            commit_to_use_for_benchmark = current_commit_hash

        # Wait a bit (3 seconds) after building the benchmarks for the files to be written
        time.sleep(3)

        print("Getting list of benchmarks...")
        benchmark_jar_path, list_of_benchmarks = self.__get_list_of_benchmarks(self.project_path, project_benchmark_directory, project_benchmark_name)
        if not list_of_benchmarks:
            print(f'Can\'t get list of benchmarks')
            return False, None

        print("Getting target methods...")
        target_methods = []
        if not has_benchmark_executed:
            for benchmark in list_of_benchmarks:
                tm = self.__get_target_methods(self.project_path, target_package, commit.hexsha, benchmark_jar_path, benchmark)
                if not tm:
                    print(f'Can\'t get target methods')
                    continue

                target_methods.append({
                    'benchmark': benchmark,
                    'methods': tm
                })

            self.__save_benchmark_history(self.project_name, target_methods, benchmark_hash)
        else:
            target_methods = benchmark_history

        print("Checking if benchmark is targeting changed methods...")

        chosen_benchmarks = {}
        for tm in target_methods:
            tm_benchmark = tm['benchmark']
            tm_methods = tm['methods']

            is_targeting, targets = self.__is_benchmark_targeting_changed_methods(changed_methods, tm_methods)
            if is_targeting:
                chosen_benchmarks[tm_benchmark] = targets

        if not chosen_benchmarks:
            print(f'{commit.hexsha} didn\'t execute any benchmarks')
            return False, None

        # Empty the execution directory first
        config_directory = os.path.join('results', self.project_name, commit.hexsha, 'execution')
        os.makedirs(config_directory, exist_ok=True)
        for file in os.listdir(config_directory):
            os.remove(os.path.join(config_directory, file))

        chosen_benchmarks = self.__minimize_and_distribute_methods(chosen_benchmarks)
        for benchmark, methods in chosen_benchmarks.items():
            print(f'Benchmark {benchmark} is targeting {len(methods)} methods')
            YamlCreator().create_yaml(
                log_file=os.path.join(config_directory, f'{benchmark}_log.log'),
                target_package=target_package,
                instrument=methods,
                ignore=[],
                yaml_file=os.path.join(config_directory, f'{benchmark}_config.yaml')
            )

        performance_results = {}
        for commit_hash in [current_commit_hash, previous_commit_hash]:
            print(f"Checking out to {'current' if commit_hash == current_commit_hash else 'previous'} commit...")
            # Checkout the commit. If already checked out, no need to checkout again

            # Use the commit_to_use_for_benchmark to determine which benchmark files to use
            if commit_to_use_for_benchmark != commit_hash:
                # Temporarily checkout commit_to_use_for_benchmark to get its benchmarks
                self.repo.git.checkout(commit_to_use_for_benchmark, force=True)
                temp_benchmark_dir = os.path.join('/tmp', project_benchmark_directory)
                shutil.copytree(os.path.join(self.project_path, project_benchmark_directory), temp_benchmark_dir)
                self.repo.git.checkout(commit_hash, force=True)
                shutil.rmtree(os.path.join(self.project_path, project_benchmark_directory))
                shutil.copytree(temp_benchmark_dir, os.path.join(self.project_path, project_benchmark_directory))
                shutil.rmtree(temp_benchmark_dir)
            else:
                self.repo.git.checkout(commit_hash, force=True)

            # Rebuid the commit object
            # self.__update_compile_version(self.project_path, self.repo.commit(commit_hash), "1.8")
            # self.__add_required_dependencies(self.project_path, required_dependencies)
            self.__is_project_buildable(project_path=self.project_path, owner=git_info['owner'], repo_name=git_info['repo'], commit_sha=commit_hash, build_anyway=True)
            self.__build_benchmarks(self.project_path, project_benchmark_directory, commit_hash, build_anyway=True,
                                    custom_command = custom_commands["benchmark"] if custom_commands and "benchmark" in custom_commands else None)

            commit = self.repo.commit(commit_hash)

            print("Running benchmarks...")
        #     performance_data = self.__run_benchmark_and_get_performance_data(self.project_path, benchmark_jar_path, config_directory)
        #     if not performance_data:
        #         print(f'Error while running benchmarks for getting performance data')
        #         return False, None

        #     performance_results[commit_hash] = performance_data

        # # Remove the execution directory
        # for file in os.listdir(config_directory):
        #     os.remove(os.path.join(config_directory, file))

        return True, performance_results

    def __is_project_buildable(self, project_path: str, owner, repo_name, commit_sha, build_anyway = False) -> bool:        
        # Check if in the history, the build is successful
        if not os.path.exists(os.path.join('results', self.project_name, 'build_history.json')):
            with open(os.path.join('results', self.project_name, 'build_history.json'), 'w') as f:
                json.dump({}, f)

        with open(os.path.join('results', self.project_name, 'build_history.json'), 'r') as f:
            build_history = json.load(f)

        if commit_sha in build_history and not build_anyway:
            return build_history[commit_sha]

        def is_github_builable() -> bool:
            headers = {"Authorization": f"token {GIT_TOKEN}"}
            commit_url = f"https://api.github.com/repos/{owner}/{repo_name}/commits/{commit_sha}"
            status_url = f"{commit_url}/status"

            # Get build statuses
            statuses_response = requests.get(status_url, headers=headers)
            status_data = statuses_response.json()

            if 'state' in status_data:
                if status_data['state'] == "failure" or status_data['state'] == "error":
                    print(f"\tGitHub build status is failure")
                    return False

                print(f"\tGitHub build status is {status_data['state']}")
            return True

        if not is_github_builable():
            # Save the result
            build_history[commit_sha] = False
            with open(os.path.join('results', self.project_name, 'build_history.json'), 'w') as f:
                json.dump(build_history, f)

            return False

        print(f"\tBuilding the project locally...")
        process = subprocess.run([
            'mvn',
            'clean',
            'install',
            '-DskipTests',
            '-Dmaven.javadoc.skip=true',
            '-Dcheckstyle.skip=true',
            '-Denforcer.skip=true',
            '-Dfindbugs.skip=true',
            '-Dlicense.skip=true'
        ], cwd=project_path, capture_output=True, shell=False, timeout=180)

        if process.returncode != 0:
            # Save the result
            build_history[commit_sha] = False
            with open(os.path.join('results', self.project_name, 'build_history.json'), 'w') as f:
                json.dump(build_history, f)

            return False

        # Save the result
        build_history[commit_sha] = True
        with open(os.path.join('results', self.project_name, 'build_history.json'), 'w') as f:
            json.dump(build_history, f)

        return True

    def __build_benchmarks(self, project_path: str, benchmark_directory: str, 
                           commit_sha: str, build_anyway:bool = False,
                           custom_command: Optional[dict] = None) -> bool:
        # Check if in the history, the build is successful
        if not os.path.exists(os.path.join('results', self.project_name, 'benchmark_build_history.json')):
            with open(os.path.join('results', self.project_name, 'benchmark_build_history.json'), 'w') as f:
                json.dump({}, f)

        with open(os.path.join('results', self.project_name, 'benchmark_build_history.json'), 'r') as f:
            build_history = json.load(f)

        if commit_sha in build_history and not build_anyway:
            return build_history[commit_sha]
        
        command = ['mvn', 
                   'clean', 
                   'package', 
                   '-Dlicense.skip=true']
        cwd = os.path.join(project_path, benchmark_directory)

        if custom_command:
            command = custom_command['command'].split()
            cwd = os.path.join(project_path, custom_command['cwd'])

        process = subprocess.run(command, cwd=cwd, capture_output=True, shell=False)

        if process.returncode != 0:
            return False

        # Save the result
        build_history[commit_sha] = True
        with open(os.path.join('results', self.project_name, 'benchmark_build_history.json'), 'w') as f:
            json.dump(build_history, f)

        return True

    def __get_list_of_benchmarks(self, project_path: str, benchmark_directory: str, benchmark_name: str) -> Tuple[str, list[str]]:        
        benchmark_jar_path = None
        if benchmark_name == '' or not os.path.exists(os.path.join(project_path, benchmark_directory, 'target', f'{benchmark_name}.jar')):
            for root, _, files in os.walk(os.path.join(project_path, benchmark_directory)):
                for file in files:
                    if file.endswith('.jar'):
                        if any(substring in file.lower() for substring in ('shade', 'original', 'source', 'sources', 'javadoc', 'tests', 'test', 'snapshot')):
                            continue
                        benchmark_jar_path = os.path.join(root, file)
                        break

        else:
            benchmark_jar_path = os.path.join(project_path, benchmark_directory, 'target', f'{benchmark_name}.jar')

        if not benchmark_jar_path:
            return '', []

        process = subprocess.run([
            'java',
            '-jar',
            benchmark_jar_path,
            '-l'
        ], capture_output=True, shell=False)

        if process.returncode != 0:
            return '', []

        return benchmark_jar_path, [line.strip() for line in process.stdout.decode('utf-8').strip().splitlines()[1:]]

    def __has_benchmark_previously_executed(self, commit: Commit, benchmarks_directory: str) -> Tuple[bool, list, str]:
        """
        Steps:
            1. Get the benchmark directory
            2. Calculate the hash of the directory
            3. Check whether the hash exists in the previous results
            4. If it exists, return True; otherwise, return False
        """

        benchmark_directory = os.path.join(self.project_path, benchmarks_directory, 'src', 'main')
        benchmark_hash = FileUtils.get_folder_hash(benchmark_directory)

        history_path = os.path.join('results', self.project_name, 'benchmark_history.json')
        if not os.path.exists(history_path):
            return False, [], benchmark_hash

        with open(history_path, 'r') as f:
            history = json.load(f)

        if benchmark_hash in history and len(history[benchmark_hash]) > 0:
            return True, history[benchmark_hash], benchmark_hash

        return False, [], benchmark_hash

    def __save_benchmark_history(self, project_name, target_methods: list[dict], benchmark_hash: str) -> None:
        history_path = os.path.join('results', project_name, 'benchmark_history.json')
        if not os.path.exists(history_path):
            with open(history_path, 'w') as f:
                json.dump({}, f)

        with open(history_path, 'r') as f:
            history = json.load(f)

        history[benchmark_hash] = target_methods

        with open(history_path, 'w') as f:
            json.dump(history, f)

    def __get_target_methods(self, project_path: str, project_package: str, commit_id: str, benchmark_jar_path: str, benchmark_name: str) -> Union[NoneType, list[str]]:
        log_path = os.path.join('results', self.project_name,
                                commit_id, 'visited', f'{benchmark_name}.log')
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

        config_path = os.path.join('results', self.project_name, commit_id, 'visited', f'{benchmark_name}.yaml')
        os.makedirs(os.path.dirname(config_path), exist_ok=True)

        if os.path.exists(log_path):
            # Remove the log file
            os.remove(log_path)

        YamlCreator().create_yaml(
            log_file=log_path,
            target_package=project_package,
            instrument=[],
            ignore=[],
            only_visited=True,
            yaml_file=config_path
        )

        process = subprocess.run([
            'java',
            '-Dlog4j2.contextSelector=org.apache.logging.log4j.core.async.AsyncLoggerContextSelector',
            f'-javaagent:java-instrumentation-agent-1.0.jar=config={config_path}',
            '-jar',
            benchmark_jar_path,
            '-f', '1',
            '-wi', '0',
            '-i', '1',
            '-r', '1',
            benchmark_name
        ], capture_output=True, shell=False)

        if process.returncode != 0:
            print(process.stderr.decode('utf-8'))
            return None

        target_methods = set()

        # Read the log file
        with open(os.path.join(log_path), 'r') as f:
            for line in f:
                target_methods.add(
                    ' '.join(line.strip().split(' ')[2:]).split('(')[0].strip())

        return list(target_methods)

    def __is_benchmark_targeting_changed_methods(self, changed_methods: list, target_functions: list[str]) -> Tuple[bool, list[str]]:
        # Preprocess the target functions once and store the results in a set
        tf = {f.split('(')[0].strip().split(' ')[-1].strip() for f in target_functions}

        # Use set comprehension to directly add the matching methods
        chosen_methods = {method for method in changed_methods if method.split('(')[0].strip().split(' ')[-1].strip() in tf}

        return len(chosen_methods) > 0, list(chosen_methods)

    def __minimize_and_distribute_methods(self, benchmarks: dict[str, list[str]]) -> dict[str, list[str]]:
        # Create a set of all methods to be covered
        all_methods = set()
        for methods in benchmarks.values():
            all_methods.update(methods)

        # Create a list of benchmarks sorted by the number of unique methods they cover in descending order
        sorted_benchmarks = sorted(benchmarks.items(), key=lambda x: len(x[1]), reverse=True)

        selected_benchmarks = {}
        covered_methods = set()

        # Select benchmarks iteratively
        while covered_methods != all_methods:
            for benchmark, methods in sorted_benchmarks:
                # Calculate the new methods this benchmark will cover
                new_methods = set(methods) - covered_methods
                if new_methods:
                    # Select this benchmark and assign it the new methods
                    selected_benchmarks[benchmark] = new_methods
                    covered_methods.update(new_methods)
                    # Remove the selected benchmark from the list
                    sorted_benchmarks = [b for b in sorted_benchmarks if b[0] != benchmark]
                    break

        # Covert set to list
        selected_benchmarks = {k: list(v) for k, v in selected_benchmarks.items()}

        return selected_benchmarks

    def __update_compile_version(self, project_path: str, commit: Commit, version: str) -> bool:
        # Iterate through all files
        for root, dirs, files in os.walk(project_path):
            for file in files:
                if file.endswith('pom.xml'):
                    try:
                        pom_path = os.path.join(root, file)  # type: ignore
                        with open(pom_path, 'r') as f:
                            pom_content = f.read()
                    except:
                        return True

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
                                            if source.text is not None:
                                                try:
                                                    source_version = float(source.text)
                                                    if source_version < float(version):
                                                        source.text = str(version)
                                                except ValueError:
                                                    break
                                                    # source.text = str(version)
                                        for target in configuration.findall('target'):
                                            if target.text is not None:
                                                try:
                                                    target_version = float(target.text)
                                                    if target_version < float(version):
                                                        target.text = str(version)
                                                except ValueError:
                                                    break
                                                    # target.text = str(version)

                        with open(pom_path, 'w') as f:
                            f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
                            f.write(ET.tostring(root, encoding='utf-8').decode('utf-8'))

                    except Exception as e:
                        print(e)
                        return True

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

    def __run_benchmark_and_get_performance_data(self, project_path: str, benchmark_jar_path: str, config_directory) -> Union[NoneType, dict]:
        # Open all of the config files
        configs = [file for file in os.listdir(config_directory) if file.endswith('.yaml')]

        performance_data = {}
        for config in configs:
            benchmark_name = config.replace('_config.yaml', '')
            config_path = os.path.join(config_directory, config)

            # Remove the previous log file (if exists)
            log_path = os.path.join(config_directory, f'{benchmark_name}_log.log')
            if os.path.exists(log_path):
                os.remove(log_path)

            process = subprocess.run([
                'java',
                '-Dlog4j2.contextSelector=org.apache.logging.log4j.core.async.AsyncLoggerContextSelector',
                f'-javaagent:java-instrumentation-agent-1.0.jar=config={config_path}',
                '-jar',
                benchmark_jar_path,
                '-f', '5',
                '-wi', '0',
                '-i', '5',
                benchmark_name
            ], capture_output=True, shell=False)

            if process.returncode != 0:
                return None

            # Analyze the performance
            method_performances = PerformanceAnalysis(log_path).analyze()
            performance_data[benchmark_name] = method_performances

        return performance_data
