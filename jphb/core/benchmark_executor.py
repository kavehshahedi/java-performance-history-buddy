from types import NoneType
from typing import Optional, Tuple, Union
from git import Repo
import os
import shutil
import subprocess
import time
import sys

from jphb.services.yaml_service import YamlCreator

from jphb.services.pom_service import PomService
from jphb.services.mvn_service import MvnService
from jphb.services.lttng_service import LTTngService

from jphb.utils.file_utils import FileUtils
from jphb.utils.printer import Printer
from jphb.core.performance_analysis import PerformanceAnalysis


class BenchmarkExecutor:

    def __init__(self, project_name: str, project_path: str, **kwargs) -> None:
        self.project_name = project_name
        self.project_path = project_path

        self.repo = Repo(self.project_path)

        self.printer_indent = kwargs.get('printer_indent', 0)

        self.jib_path = os.path.join(sys.path[0], 'jphb', 'resources', 'jib.jar')

        self.use_lttng = kwargs.get('use_lttng', False)

    def __replace_benchmarks(self, from_commit_hash: str, to_commit_hash: str, benchmark_directory: str) -> None:
        self.repo.git.checkout(from_commit_hash, force=True)
        temp_benchmark_dir = os.path.join('/tmp', benchmark_directory)
        shutil.copytree(os.path.join(self.project_path, benchmark_directory), temp_benchmark_dir)
        self.repo.git.checkout(to_commit_hash, force=True)
        shutil.rmtree(os.path.join(self.project_path, benchmark_directory))
        shutil.copytree(temp_benchmark_dir, os.path.join(self.project_path, benchmark_directory))
        shutil.rmtree(temp_benchmark_dir)

    def execute(self, jmh_dependency: dict,
                current_commit_hash: str,
                previous_commit_hash: str,
                changed_methods: dict[str, list[str]],
                target_package: str,
                java_version: dict,
                custom_benchmark: Optional[dict] = None) -> Tuple[bool, Optional[dict]]:
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
        self.project_benchmark_directory = jmh_dependency['benchmark_directory']
        self.project_benchmark_name = jmh_dependency['benchmark_name']
        self.project_benchmark_module = None
        if custom_benchmark:
            self.project_benchmark_directory = custom_benchmark.get('directory', self.project_benchmark_directory)
            self.project_benchmark_module = custom_benchmark.get('module', None)

        # Global variables
        self.java_version = java_version['version']

        # Print the variables
        Printer.info(f'Info: {current_commit_hash}', num_indentations=self.printer_indent)
        Printer.info(f'Benchmark directory: {self.project_benchmark_directory}', num_indentations=self.printer_indent)
        Printer.info(f'Benchmark name: {self.project_benchmark_name}', num_indentations=self.printer_indent)
        Printer.info(f'Java version: {self.java_version}', num_indentations=self.printer_indent)
        Printer.separator(num_indentations=self.printer_indent)

        commit = self.repo.commit(current_commit_hash)

        # Iterate through the commits (previous and current)
        is_previous_benchmark_built = True
        is_current_benchmark_built = True
        for commit_hash in [previous_commit_hash, current_commit_hash]:
            Printer.info(f'Checking out to {"current" if commit_hash == current_commit_hash else "previous"} commit...', num_indentations=self.printer_indent)

            # Checkout the commit
            self.repo.git.checkout(commit_hash, force=True)

            # If the Java version should be updated, update the pom.xml file
            if java_version['should_update_pom']:
                pom_service = PomService(pom_source=os.path.join(self.project_path, 'pom.xml'))
                pom_service.set_java_version(self.java_version)

            if self.project_benchmark_module:
                # Check whether the benchmarks are buildable
                Printer.info(f'Checking if benchmarks with custom module are buildable...', num_indentations=self.printer_indent+1)
                is_benchmark_buildable = self.__build_benchmarks_with_module(module=self.project_benchmark_module,
                                                                            benchmark_commit_hash=commit_hash,
                                                                            build_anyway=(commit_hash == current_commit_hash),
                                                                            java_version=self.java_version)

                if not is_benchmark_buildable:
                    Printer.error(f'Benchmarks are not buildable', num_indentations=self.printer_indent+2)
                    return False, None
                
                Printer.success(f'Benchmarks are buildable', num_indentations=self.printer_indent+2)
            else:
                # Check whether the project is buildable
                Printer.info(f'Checking if project is buildable...', num_indentations=self.printer_indent+1)
                is_project_buildable = self.__build_project(build_anyway=(commit_hash == current_commit_hash),
                                                            java_version=self.java_version,
                                                            commit_hash=commit_hash)
                if not is_project_buildable:
                    Printer.error(f'Project is not buildable', num_indentations=self.printer_indent+2)
                    return False, None

                Printer.success(f'Project is buildable', num_indentations=self.printer_indent+2)
    
                # Check whether the benchmarks are buildable
                Printer.info(f'Checking if benchmarks are buildable...', num_indentations=self.printer_indent+1)
                is_benchmark_buildable = self.__build_benchmarks(benchmark_directory=self.project_benchmark_directory,
                                                                benchmark_commit_hash=commit_hash,
                                                                build_anyway=(commit_hash == current_commit_hash),
                                                                java_version=self.java_version)            
                if not is_benchmark_buildable:
                    Printer.error(f'Benchmarks are not buildable', num_indentations=self.printer_indent+2)
                    if commit_hash == current_commit_hash:
                        is_current_benchmark_built = False
                    else:
                        is_previous_benchmark_built = False
                else:
                    Printer.success(f'Benchmarks are buildable', num_indentations=self.printer_indent+2)

            # Check the hash of the benchmarks folder
            if commit_hash == current_commit_hash:
                current_benchmark_directory_hash = FileUtils.get_folder_hash(os.path.join(self.project_path, self.project_benchmark_directory, 'src', 'main'))
            else:
                previous_benchmark_directory_hash = FileUtils.get_folder_hash(os.path.join(self.project_path, self.project_benchmark_directory, 'src', 'main'))
                
        # If both benchmarks are not built, return    
        if not is_previous_benchmark_built and not is_current_benchmark_built:
            Printer.error(f'Both benchmarks are not built', num_indentations=self.printer_indent+1)
            return False, None
        
        # Check if the benchmarks are the same
        has_same_benchmarks = (current_benchmark_directory_hash == previous_benchmark_directory_hash) # type: ignore
        Printer.info(f'Benchmarks are the same: {has_same_benchmarks}', num_indentations=self.printer_indent+1)
        
        if is_previous_benchmark_built:
            if has_same_benchmarks and is_current_benchmark_built:
                commit_to_use_for_benchmark = current_commit_hash
            else:
                commit_to_use_for_benchmark = previous_commit_hash
        else:
            commit_to_use_for_benchmark = current_commit_hash

        # If the commit to use for the benchmark is not the current commit, replace the benchmarks
        if commit_to_use_for_benchmark != current_commit_hash:
            Printer.info(f'Replacing the benchmarks with the other commit...', num_indentations=self.printer_indent)
            self.__replace_benchmarks(from_commit_hash=commit_to_use_for_benchmark,
                                      to_commit_hash=current_commit_hash,
                                      benchmark_directory=self.project_benchmark_directory)
            status = self.__build_benchmarks(benchmark_directory=self.project_benchmark_directory,
                                             benchmark_commit_hash=current_commit_hash,
                                             build_anyway=True, # Since we need to run the benchmarks, we build them anyway
                                             java_version=self.java_version)            
            if not status:
                Printer.error(f'Benchmarks are not compatible with the other commit', num_indentations=self.printer_indent+1)
                return False, None
            
            Printer.success(f'Benchmarks are replaced with the other commit', num_indentations=self.printer_indent+1)

        # Wait a bit (2 seconds) after building the benchmarks for the files to be written
        time.sleep(2)

        # Get the benchmark history
        Printer.info('Checking if benchmark has previously executed...', num_indentations=self.printer_indent+1)
        hash_to_check = FileUtils.get_folder_hash(os.path.join(self.project_path, self.project_benchmark_directory, 'src', 'main'))
        has_benchmark_executed, benchmark_history = self.__has_benchmark_previously_executed(hash_to_check=hash_to_check)
        if has_benchmark_executed:
            Printer.success(f'Benchmark has previously executed', num_indentations=self.printer_indent+2)
        else:
            Printer.warning(f'Benchmark has not previously executed', num_indentations=self.printer_indent+2)

        Printer.info('Getting list of benchmarks...', num_indentations=self.printer_indent)
        benchmark_jar_path, list_of_benchmarks = self.__get_list_of_benchmarks(benchmark_directory=self.project_benchmark_directory,
                                                                               benchmark_name=self.project_benchmark_name,
                                                                               java_version=self.java_version)
        if not list_of_benchmarks:
            Printer.error(f'Can\'t get list of benchmarks', num_indentations=self.printer_indent+1)
            return False, None

        # Get the target methods for each benchmark
        Printer.info('Getting target methods...', num_indentations=self.printer_indent)
        target_methods = []
        if not has_benchmark_executed:
            for i, benchmark_name in enumerate(list_of_benchmarks):
                tm = self.__get_target_methods(project_package=target_package,
                                               java_version=self.java_version,
                                               commit_hash=commit.hexsha,
                                               benchmark_jar_path=benchmark_jar_path,
                                               benchmark_name=benchmark_name)
                if not tm:
                    Printer.error(f'({i+1}/{len(list_of_benchmarks)}) Can\'t get target methods for {benchmark_name}', num_indentations=self.printer_indent+1)
                    continue

                Printer.success(f'({i+1}/{len(list_of_benchmarks)}) Got target methods for {benchmark_name}', num_indentations=self.printer_indent+1)

                target_methods.append({
                    'benchmark': benchmark_name,
                    'methods': tm
                })

            self.__save_benchmark_history(target_methods=target_methods,
                                          benchmark_hash=hash_to_check)
        else:
            Printer.success(f'Got the target methods from the history', num_indentations=self.printer_indent+1)
            target_methods = benchmark_history

        # Check if the benchmarks are targeting the changed methods
        Printer.info('Checking if benchmark is targeting changed methods...', num_indentations=self.printer_indent)
        chosen_benchmarks:dict[str, dict[str, list[str]]] = {}
        for tm in target_methods:
            tm_benchmark = tm['benchmark']
            tm_methods = tm['methods']

            is_targeting, targets = self.__is_benchmark_targeting_changed_methods(changed_methods=changed_methods,
                                                                                  target_methods=tm_methods)
            
            # If the benchmark is targeting the changed methods, add it to the chosen benchmarks for running
            if is_targeting:
                chosen_benchmarks[tm_benchmark] = targets

        # If no benchmarks are targeting the changed methods, return (i.e., skip the commit)
        if not chosen_benchmarks:
            Printer.warning(f'No benchmarks are targeting the changed methods', num_indentations=self.printer_indent+1)
            return False, None

        # We want to minimize the number of benchmarks for running
        chosen_benchmarks = self.__minimize_and_distribute_methods(benchmarks=chosen_benchmarks)

        performance_results = {}
        for commit_hash_, chosen_benchmarks_ in chosen_benchmarks.items():
            # Empty the execution directory first
            config_directory = os.path.join('results', self.project_name, 'commits', commit.hexsha, 'execution', commit_hash_)
            FileUtils.create_directory(config_directory, remove_contents=True)

            for benchmark, methods in chosen_benchmarks_.items():
                Printer.success(f'Benchmark {benchmark} is targeting {len(methods)} methods', num_indentations=self.printer_indent+1)

                # Create the YAML file
                YamlCreator().create_yaml(
                    log_file=os.path.join(config_directory, 'ust', f'{benchmark}.log'),
                    target_package=target_package,
                    instrument=methods,
                    ignore=[],
                    instrument_main_method=False,
                    add_timestamp_to_file_names=True,
                    use_hash=True,
                    yaml_file=os.path.join(config_directory, f'{benchmark}.yaml')
                )

            # Run the benchmarks
            Printer.info(f'Checking out to {"current" if commit_hash_ == current_commit_hash else "previous"} commit...', num_indentations=self.printer_indent)
            # Checkout the commit. If already checked out, no need to checkout again

            if commit_hash_ != current_commit_hash:
                self.repo.git.checkout(commit_hash_, force=True)

                # If the Java version should be updated, update the pom.xml file
                if java_version['should_update_pom']:
                    pom_service = PomService(pom_source=os.path.join(self.project_path, 'pom.xml'))
                    pom_service.set_java_version(self.java_version)

                if not has_same_benchmarks and commit_to_use_for_benchmark != current_commit_hash:
                    Printer.info(f'Replacing the benchmarks with the other commit...', num_indentations=self.printer_indent)
                    self.__replace_benchmarks(from_commit_hash=commit_to_use_for_benchmark,
                                                to_commit_hash=commit_hash_,
                                                benchmark_directory=self.project_benchmark_directory)

                if self.project_benchmark_module:
                    is_benchmark_buildable = self.__build_benchmarks_with_module(module=self.project_benchmark_module,
                                                                                benchmark_commit_hash=commit_hash_,
                                                                                build_anyway=True,
                                                                                java_version=self.java_version)
                else:  
                    self.__build_project(commit_hash=commit_hash_,
                                        build_anyway=True, # Since we need to run the benchmarks, we build them anyway
                                        java_version=self.java_version)
                    self.__build_benchmarks(benchmark_directory=self.project_benchmark_directory,
                                            benchmark_commit_hash=commit_hash_,
                                            build_anyway=True, # Since we need to run the benchmarks, we build them anyway
                                            java_version=self.java_version)
                
            Printer.info('Running benchmarks...', num_indentations=self.printer_indent+1)
            performance_data = self.__run_benchmark_and_get_performance_data(benchmark_jar_path=benchmark_jar_path,
                                                                             config_directory=config_directory,
                                                                             java_version=self.java_version)
            if not performance_data:
                Printer.error(f'Error while running benchmarks for getting performance data', num_indentations=self.printer_indent+2)
                return False, None
            Printer.success(f'Benchmarks are executed successfully', num_indentations=self.printer_indent+2)

            performance_results[commit_hash_] = performance_data

        # NOTE: Not sure if we need to remove the execution directory for now
        # # Remove the execution directory
        # for file in os.listdir(config_directory):
        #     os.remove(os.path.join(config_directory, file))

        return True, performance_results

    def __build_project(self, commit_hash: str,
                        java_version:str = '11',
                        build_anyway = False) -> bool:        
        # Check if in the history, the build is successful
        history_path = os.path.join('results', self.project_name, 'build_history.json')
        build_history = FileUtils.read_json_file(history_path)

        if commit_hash in build_history and not build_anyway:
            return build_history[commit_hash]

        Printer.info(f'Building the project locally with Java {self.java_version}', num_indentations=self.printer_indent+2)
        mvn_service = MvnService()
        status, jv = mvn_service.install(cwd=self.project_path,
                                         java_version=java_version,
                                         verbose=False,
                                         retry_with_other_java_versions=True)

        # Save the result
        build_history[commit_hash] = status
        FileUtils.write_json_file(history_path, build_history)

        # Update the Java version is the build is successful
        if status:
            if jv != self.java_version:
                Printer.info(f'Java version is updated to {jv}', num_indentations=self.printer_indent+3)
                self.java_version = jv

        return status

    def __build_benchmarks(self, benchmark_directory: str, # The directory where the benchmarks are located
                           benchmark_commit_hash: str, # The commit SHA of the benchmark. In this pipeline, we use the previous release commit sha
                           build_anyway:bool = False, # If True, the build will be done regardless of the history
                           java_version: str = '11', # The Java version to be used for building the benchmarks
                           custom_command: Optional[dict] = None) -> bool: # The custom command to build the benchmarks
        # Check if in the history, the build is successful
        history_path = os.path.join('results', self.project_name, 'benchmark_build_history.json')
        build_history = FileUtils.read_json_file(history_path)

        # Check if the build has already been done
        if benchmark_commit_hash in build_history and not build_anyway:
            return build_history[benchmark_commit_hash]
        
        # Basically, the baseline command has been indicated in MvnService class. If there is a custom command, it will be used.
        command = None
        cwd = os.path.join(self.project_path, benchmark_directory)
        if custom_command:
            command = custom_command['command'].split()
            cwd = os.path.join(self.project_path, custom_command['cwd'])

        # Build the benchmarks (i.e., package)
        Printer.info(f'Building the benchmarks locally with Java {java_version}', num_indentations=self.printer_indent+2)
        mvn_service = MvnService()
        status, jv = mvn_service.package(cwd=cwd,
                                         custom_command=command,
                                         java_version=java_version,
                                         verbose=False,
                                         retry_with_other_java_versions=True)

        # Save the result
        build_history[benchmark_commit_hash] = True
        FileUtils.write_json_file(history_path, build_history)

        # Update the Java version is the build is successful
        if status:
            if jv != self.java_version:
                self.java_version = jv

        return status
    
    def __build_benchmarks_with_module(self, benchmark_commit_hash: str,
                                       module: str,
                                       java_version:str = '11',
                                       build_anyway = False) -> bool:        
        # Check if in the history, the build is successful
        history_path = os.path.join('results', self.project_name, 'benchmark_build_history.json')
        build_history = FileUtils.read_json_file(history_path)

        # Check if the build has already been done
        if benchmark_commit_hash in build_history and not build_anyway:
            return build_history[benchmark_commit_hash]

        Printer.info(f'Building the benchmarks with custom module locally with Java {java_version}', num_indentations=self.printer_indent+2)
        mvn_service = MvnService()
        status, jv = mvn_service.package_module(cwd=self.project_path,
                                                module=module,
                                                java_version=java_version,
                                                verbose=False,
                                                retry_with_other_java_versions=True)

        # Save the result
        build_history[benchmark_commit_hash] = status
        FileUtils.write_json_file(history_path, build_history)

        # Update the Java version is the build is successful
        if status:
            if jv != self.java_version:
                Printer.info(f'Java version is updated to {jv}', num_indentations=self.printer_indent+3)
                self.java_version = jv

        return status

    def __get_list_of_benchmarks(self, benchmark_directory: str,
                                 benchmark_name: str,
                                 java_version:str) -> Tuple[str, list[str]]:        
        benchmark_jar_path = None
        candidate_jars = []
        if benchmark_name == '' or not os.path.exists(os.path.join(self.project_path, benchmark_directory, 'target', f'{benchmark_name}')):
            for root, _, files in os.walk(os.path.join(self.project_path, benchmark_directory)):
                for file in files:
                    if file.endswith('.jar'):
                        if any(substring in file.lower() for substring in ('shade', 'original', 'source', 'sources', 'javadoc', 'tests', 'test', 'snapshot')):
                            continue
                        candidate_jars.append(os.path.join(root, file))

        else:
            benchmark_jar_path = os.path.join(self.project_path, benchmark_directory, 'target', f'{benchmark_name}')
                
        while not benchmark_jar_path:
            if not candidate_jars:
                return '', []
            
            candidate_jar = candidate_jars.pop()
            try:
                mvn_service = MvnService()
                env = mvn_service.update_java_home(java_version)
                process = subprocess.run([
                        'java',
                        '-jar',
                        candidate_jar,
                        '-l'
                    ], capture_output=True, shell=False, timeout=2, env=env)
                
                if process.returncode ==0:
                    output = process.stdout.decode('utf-8').strip()
                    if 'benchmarks:' in output.lower():
                        benchmark_jar_path = candidate_jar
                        self.project_benchmark_name = os.path.basename(benchmark_jar_path)
                        break
            except:
                continue

        if not benchmark_jar_path:
            return '', []

        try:
            mvn_service = MvnService()
            env = mvn_service.update_java_home(java_version)
            process = subprocess.run([
                    'java',
                    '-jar',
                    benchmark_jar_path,
                    '-l'
                ], capture_output=True, shell=False, timeout=2, env=env)
            
            if process.returncode != 0:
                return '', []
            
            output = process.stdout.decode('utf-8').strip()
            lines = output.splitlines()
            
            # Find the index of the line starting with 'Benchmarks:'
            start_index = next((i for i, line in enumerate(lines) if line.lower().startswith('benchmarks:')), None)
            
            if start_index is not None:
                # Extract the benchmark names starting from the line after 'Benchmarks:'
                benchmark_names = [line.strip() for line in lines[start_index + 1:] if line.strip()]
                return benchmark_jar_path, benchmark_names
            else:
                return '', []
            
        except:
            return '', []
    
    def __has_benchmark_previously_executed(self, hash_to_check: str) -> Tuple[bool, list]:
        history_path = os.path.join('results', self.project_name, 'benchmark_history.json')
        history = FileUtils.read_json_file(history_path)

        if hash_to_check in history and len(history[hash_to_check]) > 0:
            return True, history[hash_to_check]

        return False, []

    def __save_benchmark_history(self, target_methods: list[dict],
                                 benchmark_hash: str) -> None:
        history_path = os.path.join('results', self.project_name, 'benchmark_history.json')
        history = FileUtils.read_json_file(history_path)
        history[benchmark_hash] = target_methods
        FileUtils.write_json_file(history_path, history)

    def __get_target_methods(self, project_package: str,
                             java_version: str,
                             commit_hash: str,
                             benchmark_jar_path: str,
                             benchmark_name: str) -> Union[NoneType, list[str]]:
        log_path = os.path.join('results', self.project_name, 'commits', commit_hash, 'visited', f'{benchmark_name}.log')
        config_path = os.path.join('results', self.project_name, 'commits', commit_hash, 'visited', f'{benchmark_name}.yaml')
        
        # Create a directory for the log and config files. If the directory already exists, continue.
        FileUtils.create_directory(os.path.dirname(log_path))

        # If the log file exists from previous runs, remove it first.
        if FileUtils.is_path_exists(log_path):
            FileUtils.remove_path(log_path)

        # Create the YAML file for the Java instrumentation agent
        YamlCreator().create_yaml(
            log_file=log_path,
            target_package=project_package,
            instrument=[],
            ignore=[],
            only_visited=True,
            yaml_file=config_path,
            add_timestamp_to_file_names=True
        )

        mvn_service = MvnService()
        env = mvn_service.update_java_home(java_version)
        command = [
            'java',
            '-Dlog4j2.contextSelector=org.apache.logging.log4j.core.async.AsyncLoggerContextSelector',
            f'-javaagent:{self.jib_path}=config={config_path}',
            '-jar',
            benchmark_jar_path,
            '-f', '1',
            '-wi', '0',
            '-i', '1',
            '-r', '1s',
            benchmark_name
        ]
        
        try:
            process = subprocess.run(command, capture_output=True, shell=False, env=env, timeout=60)
        except subprocess.TimeoutExpired:
            return None

        if process.returncode != 0:
            return None

        target_methods = set()

        converted_trace_data = PerformanceAnalysis.get_trace_data_well_formatted(log_path)
        for line in converted_trace_data:
            target_methods.add(
                ' '.join(line.strip().split(' ')[2:]).split('(')[0].strip())

        return list(target_methods)

    def __is_benchmark_targeting_changed_methods(self, changed_methods: dict[str, list[str]], # The list of changed methods in the commit
                                                 target_methods: list[str] # The list of methods that the benchmark executes
                                                 ) -> Tuple[bool, dict[str, list[str]]]:
        # Preprocess the target functions once and store the results in a set
        tf = {f.split('(')[0].strip().split(' ')[-1].strip() for f in target_methods}
        tf = {f.split('$')[0] for f in tf}

        # We have a reduced version of target functions, which contains only the method names without their declarations
        tf_reduced = {f.split('.')[-1] for f in tf}

        chosen_methods = {commit_hash: [] for commit_hash in changed_methods.keys()}
        for commit_hash, methods in changed_methods.items():
            # Use set comprehension to directly add the matching methods
            for method_ in methods:
                shortened = method_.split('(')[0].strip().split(' ')[-1].strip()
                if '.' in shortened:
                    if shortened in tf:
                        chosen_methods[commit_hash].append(method_)
                else:
                    if shortened in tf_reduced:
                        chosen_methods[commit_hash].append(method_)

        return len(list(chosen_methods.values())[0]) > 0, chosen_methods

    def __minimize_and_distribute_methods(self, benchmarks: dict[str, dict[str, list[str]]]) -> dict[str, dict[str, list[str]]]:
        # Create a set of all methods to be covered
        all_methods = set()
        for method_dict in benchmarks.values():
            for methods in method_dict.values():
                all_methods.update(methods)

        # Create a list of benchmarks sorted by the number of unique methods they cover in descending order
        sorted_benchmarks = sorted(
            ((benchmark, {method_id: methods for method_id, methods in method_dict.items()})
            for benchmark, method_dict in benchmarks.items()),
            key=lambda x: len({method for methods in x[1].values() for method in methods}),
            reverse=True
        )

        selected_benchmarks = {}
        covered_methods = set()

        # Select benchmarks iteratively
        while covered_methods != all_methods:
            for benchmark, method_dict in sorted_benchmarks:
                # Calculate the new methods this benchmark will cover
                new_methods = {method for methods in method_dict.values() for method in methods} - covered_methods
                if new_methods:
                    # Assign new methods to their respective commit hashes in the selected benchmarks
                    for method_id, methods in method_dict.items():
                        if any(method in new_methods for method in methods):
                            if method_id not in selected_benchmarks:
                                selected_benchmarks[method_id] = {}
                            if benchmark not in selected_benchmarks[method_id]:
                                selected_benchmarks[method_id][benchmark] = []
                            selected_benchmarks[method_id][benchmark].extend(
                                method for method in methods if method in new_methods
                            )
                    covered_methods.update(new_methods)
                    # Remove the selected benchmark from the list
                    sorted_benchmarks = [b for b in sorted_benchmarks if b[0] != benchmark]
                    break

        return selected_benchmarks

    def __run_benchmark_and_get_performance_data(self, benchmark_jar_path: str,
                                                 config_directory: str,
                                                 java_version: str) -> Union[NoneType, dict]:
        # Open all of the config files
        configs = [file for file in os.listdir(config_directory) if file.endswith('.yaml')]

        performance_data = {}
        for config in configs:
            benchmark_name = config.replace('.yaml', '')
            config_path = os.path.join(config_directory, config)

            # Remove the previous log file (if exists)
            log_path = os.path.join(config_directory, 'ust', f'{benchmark_name}.log')
            if os.path.exists(log_path):
                os.remove(log_path)

            # Check if we need to use LTTng
            if self.use_lttng:
                lttng_service = LTTngService(project_name=self.project_name,
                                             output_path=config_directory)
                lttng_service.start()

            # Run the benchmark
            mvn_service = MvnService()
            env = mvn_service.update_java_home(java_version)
            process = subprocess.run([
                'java',
                '-Dlog4j2.contextSelector=org.apache.logging.log4j.core.async.AsyncLoggerContextSelector',
                f'-javaagent:{self.jib_path}=config={config_path}',
                '-jar',
                benchmark_jar_path,
                '-f', '3',
                '-wi', '0',
                '-i', '5',
                benchmark_name
            ], capture_output=True, shell=False, env=env)

            # Stop the LTTng tracing (if enabled)
            if self.use_lttng:
                lttng_service.stop()

            if process.returncode != 0:
                return None

            # Analyze the performance
            method_performances = PerformanceAnalysis(log_path).analyze()
            performance_data[benchmark_name] = method_performances

        return performance_data
