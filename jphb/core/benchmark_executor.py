from types import NoneType
from typing import Any, Optional, Tuple, Union
from git import Repo
import os
import shutil
import subprocess
import time
import sys
import re

from jphb.services.trace_parser import TraceParser
from jphb.services.yaml_service import YamlCreator

from jphb.services.pom_service import PomService
from jphb.services.mvn_service import MvnService
from jphb.services.lttng_service import LTTngService
from jphb.services.project_modification_service import ProjectModificationService

from jphb.utils.file_utils import FileUtils
from jphb.utils.Logger import Logger
from jphb.core.performance_analysis import PerformanceAnalysis


class BenchmarkExecutor:

    def __init__(self, project_name: str, project_path: str,
                 num_forks: int, num_iterations: int,
                 num_warmups: int, measurement_time: str,
                 max_instrumentations: int, **kwargs) -> None:
        self.project_name = project_name
        self.project_path = project_path

        self.num_forks = num_forks
        self.num_iterations = num_iterations
        self.num_warmups = num_warmups
        self.measurement_time = measurement_time
        self.max_instrumentations = max_instrumentations

        self.repo = Repo(self.project_path)

        self.printer_indent = kwargs.get('printer_indent', 0)

        self.jib_path = os.path.join(sys.path[0], 'jphb', 'resources', 'jib.jar')

        self.use_lttng = kwargs.get('use_lttng', False)

    def __clean_checkout(self, commit_hash: str) -> None:
        self.repo.git.clean('-fdx')
        self.repo.git.reset('--hard')
        self.repo.git.checkout(commit_hash, force=True)

    def __replace_benchmarks(self, from_commit_hash: str, to_commit_hash: str, benchmark_directory: str) -> None:
        self.__clean_checkout(from_commit_hash)
        temp_benchmark_dir = os.path.join('/tmp', benchmark_directory)
        shutil.copytree(os.path.join(self.project_path, benchmark_directory), temp_benchmark_dir)
        self.__clean_checkout(to_commit_hash)
        shutil.rmtree(os.path.join(self.project_path, benchmark_directory))
        shutil.copytree(temp_benchmark_dir, os.path.join(self.project_path, benchmark_directory))
        shutil.rmtree(temp_benchmark_dir)

    def execute(self, jmh_dependency: dict,
                current_commit_hash: str,
                previous_commit_hash: str,
                changed_methods: dict[str, list[str]],
                target_package: str,
                java_version: dict) -> Tuple[bool, Optional[dict]]:
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
        self.project_benchmark_directory = jmh_dependency.get('benchmark_directory', '')
        self.project_benchmark_name = jmh_dependency.get('benchmark_name', '')
        self.project_benchmark_module = jmh_dependency.get('benchmark_module', None)
        self.project_benchmark_args = jmh_dependency.get('args', None)

        if self.project_benchmark_args:
            if isinstance(self.project_benchmark_args, str):
                self.project_benchmark_args = self.project_benchmark_args.split()

        # Global variables
        self.java_version = java_version['version']

        # Print the variables
        Logger.info(f'Info: {current_commit_hash}', num_indentations=self.printer_indent)
        Logger.info(f'Benchmark directory: {self.project_benchmark_directory}', num_indentations=self.printer_indent)
        Logger.info(f'Benchmark name: {self.project_benchmark_name}', num_indentations=self.printer_indent)
        Logger.info(f'Java version: {self.java_version}', num_indentations=self.printer_indent)
        Logger.separator(num_indentations=self.printer_indent)

        commit = self.repo.commit(current_commit_hash)

        # Iterate through the commits (previous and current)
        is_previous_benchmark_built = True
        is_current_benchmark_built = True
        for commit_hash in [previous_commit_hash, current_commit_hash]:
            Logger.info(f'Checking out to {"current" if commit_hash == current_commit_hash else "previous"} commit...', num_indentations=self.printer_indent)

            # Checkout the commit
            self.__clean_checkout(commit_hash)

            # If the Java version should be updated, update the pom.xml file
            if java_version['should_update_pom']:
                self.__update_java_version_everywhere(self.java_version)

            if self.project_benchmark_module:
                # Check whether the benchmarks are buildable
                Logger.info(f'Checking if benchmarks with custom module are buildable...', num_indentations=self.printer_indent+1)
                is_benchmark_buildable = self.__build_benchmarks_with_module(module=self.project_benchmark_module,
                                                                            benchmark_commit_hash=commit_hash,
                                                                            build_anyway=(commit_hash == current_commit_hash),
                                                                            java_version=self.java_version)

                if not is_benchmark_buildable:
                    Logger.error(f'Benchmarks are not buildable', num_indentations=self.printer_indent+2)
                    return False, None
                
                Logger.success(f'Benchmarks are buildable', num_indentations=self.printer_indent+2)
            else:
                # Check whether the project is buildable
                Logger.info(f'Checking if project is buildable...', num_indentations=self.printer_indent+1)
                is_project_buildable = self.__build_project(build_anyway=(commit_hash == current_commit_hash),
                                                            java_version=self.java_version,
                                                            commit_hash=commit_hash)
                if not is_project_buildable:
                    Logger.error(f'Project is not buildable', num_indentations=self.printer_indent+2)
                    return False, None

                Logger.success(f'Project is buildable', num_indentations=self.printer_indent+2)
    
                # Check whether the benchmarks are buildable
                Logger.info(f'Checking if benchmarks are buildable...', num_indentations=self.printer_indent+1)
                is_benchmark_buildable = self.__build_benchmarks(benchmark_directory=self.project_benchmark_directory,
                                                                benchmark_commit_hash=commit_hash,
                                                                build_anyway=(commit_hash == current_commit_hash),
                                                                java_version=self.java_version)            
                if not is_benchmark_buildable:
                    Logger.error(f'Benchmarks are not buildable', num_indentations=self.printer_indent+2)
                    if commit_hash == current_commit_hash:
                        is_current_benchmark_built = False
                    else:
                        is_previous_benchmark_built = False
                else:
                    Logger.success(f'Benchmarks are buildable', num_indentations=self.printer_indent+2)

            # Check the hash of the benchmarks folder
            if commit_hash == current_commit_hash:
                current_benchmark_directory_hash = FileUtils.get_folder_hash(os.path.join(self.project_path, self.project_benchmark_directory, 'src', 'main'))
            else:
                previous_benchmark_directory_hash = FileUtils.get_folder_hash(os.path.join(self.project_path, self.project_benchmark_directory, 'src', 'main'))
                
        # If both benchmarks are not built, return    
        if not is_previous_benchmark_built and not is_current_benchmark_built:
            Logger.error(f'Both benchmarks are not built', num_indentations=self.printer_indent+1)
            return False, None
        
        # Check if the benchmarks are the same
        has_same_benchmarks = (current_benchmark_directory_hash == previous_benchmark_directory_hash) # type: ignore
        if has_same_benchmarks:
            Logger.info(f'Benchmarks are the same', num_indentations=self.printer_indent+1)
        else:
            Logger.warning(f'Benchmarks are not the same', num_indentations=self.printer_indent+1)
        
        if is_previous_benchmark_built:
            if has_same_benchmarks and is_current_benchmark_built:
                commit_to_use_for_benchmark = current_commit_hash
            else:
                commit_to_use_for_benchmark = previous_commit_hash
        else:
            commit_to_use_for_benchmark = current_commit_hash

        # If the commit to use for the benchmark is not the current commit, replace the benchmarks
        if commit_to_use_for_benchmark != current_commit_hash:
            Logger.info(f'Replacing the benchmarks with the other commit...', num_indentations=self.printer_indent)
            self.__replace_benchmarks(from_commit_hash=commit_to_use_for_benchmark,
                                      to_commit_hash=current_commit_hash,
                                      benchmark_directory=self.project_benchmark_directory)

            if self.project_benchmark_module:
                status = self.__build_benchmarks_with_module(module=self.project_benchmark_module,
                                                                            benchmark_commit_hash=current_commit_hash,
                                                                            build_anyway=True,
                                                                            java_version=self.java_version)
            else: 
                status = self.__build_benchmarks(benchmark_directory=self.project_benchmark_directory,
                                        benchmark_commit_hash=current_commit_hash,
                                        build_anyway=True,
                                        java_version=self.java_version)
                                
            if not status:
                Logger.warning(f'Benchmarks are not compatible with the other commit', num_indentations=self.printer_indent+1)
                
                # Revert changes (i.e., use original benchmarks)
                if is_current_benchmark_built:
                    Logger.info(f'Rolling back the benchmarks...', num_indentations=self.printer_indent+1)

                    self.__clean_checkout(current_commit_hash)
                    if self.project_benchmark_module:
                        self.__build_benchmarks_with_module(module=self.project_benchmark_module,
                                                            benchmark_commit_hash=current_commit_hash,
                                                            build_anyway=True,
                                                            java_version=self.java_version,
                                                            retry_with_other_java_versions=False)
                    else:
                        self.__build_project(build_anyway=True, # Since the benchmarks are not compatible, need to build the project again
                                            java_version=self.java_version,
                                            commit_hash=current_commit_hash,
                                            retry_with_other_java_versions=False)
                        self.__build_benchmarks(benchmark_directory=self.project_benchmark_directory,
                                                benchmark_commit_hash=current_commit_hash,
                                                build_anyway=True, # Since the benchmarks are not compatible, need to build the benchmarks again
                                                java_version=self.java_version,
                                                retry_with_other_java_versions=False)
                else:
                    # Since the benchmarks are not built, need to skip the commit
                    Logger.error(f'Benchmarks are not built', num_indentations=self.printer_indent+1)
                    return False, None
            
            Logger.success(f'Benchmarks are replaced with the other commit', num_indentations=self.printer_indent+1)

        # Wait a bit (2 seconds) after building the benchmarks for the files to be written
        time.sleep(2)

        # Get the benchmark history
        Logger.info('Checking if benchmark has previously executed...', num_indentations=self.printer_indent+1)
        hash_to_check = FileUtils.get_folder_hash(os.path.join(self.project_path, self.project_benchmark_directory, 'src', 'main'))
        has_benchmark_executed, benchmark_history = self.__has_benchmark_previously_executed(hash_to_check=hash_to_check)
        if has_benchmark_executed:
            Logger.success(f'Benchmark has previously executed', num_indentations=self.printer_indent+2)
        else:
            Logger.warning(f'Benchmark has not previously executed', num_indentations=self.printer_indent+2)

        Logger.info('Getting list of benchmarks...', num_indentations=self.printer_indent)
        benchmark_jar_path, list_of_benchmarks = self.__get_list_of_benchmarks(benchmark_directory=self.project_benchmark_directory,
                                                                               benchmark_name=self.project_benchmark_name,
                                                                               java_version=self.java_version)
        if not list_of_benchmarks:
            Logger.error(f'Can\'t get list of benchmarks', num_indentations=self.printer_indent+1)
            return False, None

        # Get the target methods for each benchmark
        Logger.info('Getting target methods...', num_indentations=self.printer_indent)
        target_methods = []
        if not has_benchmark_executed:
            for i, benchmark_name in enumerate(list_of_benchmarks):
                results = self.__get_target_methods(project_package=target_package,
                                               java_version=self.java_version,
                                               commit_hash=commit.hexsha,
                                               benchmark_jar_path=benchmark_jar_path,
                                               benchmark_name=benchmark_name)                       
                if not results:
                    Logger.error(f'({i+1}/{len(list_of_benchmarks)}) Can\'t get target methods for {benchmark_name}', num_indentations=self.printer_indent+1)
                    continue

                Logger.success(f'({i+1}/{len(list_of_benchmarks)}) Got target methods for {benchmark_name}. Duration: {results["duration"]}', num_indentations=self.printer_indent+1)

                target_methods.append({
                    'benchmark': benchmark_name,
                    'methods': results['methods'],
                    'duration': results['duration']
                })

            self.__save_benchmark_history(target_methods=target_methods,
                                          benchmark_hash=hash_to_check)
        else:
            Logger.success(f'Got the target methods from the history', num_indentations=self.printer_indent+1)
            target_methods = benchmark_history

        # Check if the benchmarks are targeting the changed methods
        Logger.info('Checking if benchmark is targeting changed methods...', num_indentations=self.printer_indent)
        chosen_benchmarks:dict[str, dict[str, dict[str, Any]]] = {}
        for tm in target_methods:
            tm_benchmark = tm['benchmark']
            tm_methods = tm['methods']
            tm_duration = tm['duration']

            is_targeting, targets = self.__is_benchmark_targeting_changed_methods(changed_methods=changed_methods,
                                                                                  target_methods=tm_methods)
            
            # If the benchmark is targeting the changed methods, add it to the chosen benchmarks for running
            if is_targeting:
                chosen_benchmarks[tm_benchmark] = {
                    'targets': targets,
                    'duration': tm_duration
                }

        # If no benchmarks are targeting the changed methods, return (i.e., skip the commit)
        if not chosen_benchmarks:
            Logger.warning(f'No benchmarks are targeting the changed methods', num_indentations=self.printer_indent+1)
            return False, None

        # We want to minimize the number of benchmarks for running
        chosen_benchmarks = self.__minimize_and_distribute_methods(benchmarks=chosen_benchmarks)

        for commit_hash_, chosen_benchmarks_ in chosen_benchmarks.items():
            # Empty the execution directory first
            config_directory = os.path.join('results', self.project_name, 'commits', commit.hexsha, 'execution', commit_hash_)
            FileUtils.create_directory(config_directory, remove_contents=True)

            for bench_name, bench_info in chosen_benchmarks_.items():
                methods = bench_info['targets']
                Logger.success(f'Benchmark {bench_name} is targeting {len(methods)} methods', num_indentations=self.printer_indent+1)

                # Create the YAML file
                YamlCreator().create_yaml(
                    log_file=os.path.join(config_directory, 'ust', f'{bench_name}.log'),
                    target_package=target_package,
                    instrument=methods,
                    ignore=[],
                    instrument_main_method=False,
                    add_timestamp_to_file_names=True,
                    use_hash=True,
                    max_number_of_instrumentations=100000,
                    yaml_file=os.path.join(config_directory, f'{bench_name}.yaml')
                )

            # Run the benchmarks
            Logger.info(f'Checking out to {"current" if commit_hash_ == current_commit_hash else "previous"} commit...', num_indentations=self.printer_indent)
            # Checkout the commit. If already checked out, no need to checkout again

            if commit_hash_ != current_commit_hash:
                self.__clean_checkout(commit_hash_)

                # If the Java version should be updated, update the pom.xml file
                if java_version['should_update_pom']:
                    self.__update_java_version_everywhere(self.java_version)

                if not has_same_benchmarks and commit_to_use_for_benchmark != current_commit_hash:
                    Logger.info(f'Replacing the benchmarks with the other commit...', num_indentations=self.printer_indent)
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
                
            Logger.info('Running benchmarks...', num_indentations=self.printer_indent+1)
            self.__run_benchmark(benchmark_jar_path=benchmark_jar_path,
                                                                             config_directory=config_directory,
                                                                             java_version=self.java_version)
            Logger.success(f'Benchmarks are executed successfully', num_indentations=self.printer_indent+2)

        # Analyze the performance data
        Logger.info('Analyzing the performance data...', num_indentations=self.printer_indent)
        performance_results = {}
        for commit_hash_, chosen_benchmarks_ in chosen_benchmarks.items():
            is_current = commit_hash_ == current_commit_hash
            if not is_current:
                continue

            current_config_directory = os.path.join('results', self.project_name, 'commits', commit.hexsha, 'execution', commit_hash_)
            previous_config_directory = os.path.join('results', self.project_name, 'commits', commit.hexsha, 'execution', previous_commit_hash)

            for bench_name in list(chosen_benchmarks_.keys()):
                current_log_file = os.path.join(current_config_directory, 'ust', f'{bench_name}.log')
                previous_log_file = os.path.join(previous_config_directory, 'ust', f'{bench_name}.log')

                current_analysis = PerformanceAnalysis(current_log_file)
                current_analysis.analyze()
                previous_analysis = PerformanceAnalysis(previous_log_file)
                previous_analysis.analyze()
            
                performance_results[bench_name] = previous_analysis.calculate_significance(current_analysis)

        if not performance_results:
            Logger.error(f'Error while analyzing the performance data', num_indentations=self.printer_indent+1)
            return False, None

        return True, performance_results

    def __build_project(self, commit_hash: str, # The commit hash of the project
                        java_version:str = '11', # The Java version to be used for building the project
                        build_anyway = False, # If True, the build will be done regardless of the history
                        retry_with_other_java_versions: bool = True # If True, the build will be retried with other Java versions
                        ) -> bool:        
        # Check if in the history, the build is successful
        history_path = os.path.join('results', self.project_name, 'build_history.json')
        build_history = FileUtils.read_json_file(history_path)

        if commit_hash in build_history and not build_anyway:
            return build_history[commit_hash]
        
        # Modify the project (if there is any special modification)
        modification_service = ProjectModificationService(project_name=self.project_name,
                                                          project_path=self.project_path)
        modification_service.fix_issues()
        
        Logger.info(f'Building the project locally with Java {self.java_version}', num_indentations=self.printer_indent+2)
        mvn_service = MvnService()
        mvn_service.clean_mvn_cache(cwd=self.project_path, directory=os.path.join(self.project_path, self.project_benchmark_directory, 'target'))
        status, jv = mvn_service.install(cwd=self.project_path,
                                         java_version=java_version,
                                         verbose=False,
                                         retry_with_other_java_versions=retry_with_other_java_versions)

        # Save the result
        build_history[commit_hash] = status
        FileUtils.write_json_file(history_path, build_history)

        # Update the Java version is the build is successful
        if status:
            if jv != self.java_version:
                Logger.info(f'Java version is updated to {jv}', num_indentations=self.printer_indent+3)
                self.java_version = jv

        return status

    def __build_benchmarks(self, benchmark_directory: str, # The directory where the benchmarks are located
                           benchmark_commit_hash: str, # The commit SHA of the benchmark. In this pipeline, we use the previous release commit sha
                           build_anyway:bool = False, # If True, the build will be done regardless of the history
                           java_version: str = '11', # The Java version to be used for building the benchmarks
                           custom_command: Optional[dict] = None, # The custom command to build the benchmarks
                           retry_with_other_java_versions: bool = True # If True, the build will be retried with other Java versions
                           ) -> bool: 
        # Check if in the history, the build is successful
        history_path = os.path.join('results', self.project_name, 'benchmark_build_history.json')
        build_history = FileUtils.read_json_file(history_path)

        # Check if the build has already been done
        if benchmark_commit_hash in build_history and not build_anyway:
            return build_history[benchmark_commit_hash]
        
        # Modify the project (if there is any special modification)
        modification_service = ProjectModificationService(project_name=self.project_name,
                                                          project_path=self.project_path,
                                                          project_benchmark_path=benchmark_directory)
        modification_service.fix_issues()
                
        # Basically, the baseline command has been indicated in MvnService class. If there is a custom command, it will be used.
        command = None
        cwd = os.path.join(self.project_path, benchmark_directory)
        if custom_command:
            command = custom_command['command'].split()
            cwd = os.path.join(self.project_path, custom_command['cwd'])

        # Build the benchmarks (i.e., package)
        Logger.info(f'Building the benchmarks locally with Java {java_version}', num_indentations=self.printer_indent+2)
        mvn_service = MvnService()
        status, jv = mvn_service.package(cwd=cwd,
                                         custom_command=command,
                                         args=self.project_benchmark_args,
                                         java_version=java_version,
                                         verbose=False,
                                         retry_with_other_java_versions=retry_with_other_java_versions)

        # Save the result
        build_history[benchmark_commit_hash] = True
        FileUtils.write_json_file(history_path, build_history)

        # Update the Java version is the build is successful
        if status:
            if jv != self.java_version:
                self.java_version = jv

        return status
    
    def __build_benchmarks_with_module(self, benchmark_commit_hash: str, # The commit hash of the benchmark
                                       module: str, # The module to be built
                                       java_version:str = '11', # The Java version to be used for building the benchmarks
                                       build_anyway = False, # If True, the build will be done regardless of the history
                                       retry_with_other_java_versions: bool = True # If True, the build will be retried with other Java versions
                                       ) -> bool:         
        # Check if in the history, the build is successful
        history_path = os.path.join('results', self.project_name, 'benchmark_build_history.json')
        build_history = FileUtils.read_json_file(history_path)

        # Check if the build has already been done
        if benchmark_commit_hash in build_history and not build_anyway:
            return build_history[benchmark_commit_hash]
        
        # Modify the project (if there is any special modification)
        modification_service = ProjectModificationService(project_name=self.project_name,
                                                          project_path=self.project_path,
                                                          project_benchmark_path=os.path.join(self.project_path, module))
        modification_service.fix_issues()
        
        Logger.info(f'Building the benchmarks with custom module locally with Java {java_version}', num_indentations=self.printer_indent+2)
        mvn_service = MvnService()
        mvn_service.clean_mvn_cache(cwd=self.project_path, directory=os.path.join(self.project_path, module, 'target'))
        status, jv = mvn_service.package_module(cwd=self.project_path,
                                                args=self.project_benchmark_args,
                                                module=module,
                                                java_version=java_version,
                                                verbose=False,
                                                retry_with_other_java_versions=retry_with_other_java_versions)

        # Save the result
        build_history[benchmark_commit_hash] = status
        FileUtils.write_json_file(history_path, build_history)

        # Update the Java version is the build is successful
        if status:
            if jv != self.java_version:
                Logger.info(f'Java version is updated to {jv}', num_indentations=self.printer_indent+3)
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
                        if any(substring in file.lower() for substring in ('shade', 'original', 'source', 'sources', 'javadoc', 'tests', 'test')):
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
                MvnService.remove_security_from_jar(candidate_jar)
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
            MvnService.remove_security_from_jar(benchmark_jar_path)
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
                             benchmark_name: str) -> Union[NoneType, dict[str, Any]]:
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
        MvnService.remove_security_from_jar(benchmark_jar_path)
        command = [
            'java',
            f'-javaagent:{self.jib_path}=config={config_path}',
            '-jar',
            benchmark_jar_path,
            '-f', '1',
            '-wi', '0',
            '-i', '1',
            '-r', '1s',
            benchmark_name
        ]
        
        start_time = time.time()
        try:
            start_time = time.time()
            process = subprocess.run(command, capture_output=True, shell=False, env=env, timeout=60)

            if process.returncode != 0:
                return None
        except subprocess.TimeoutExpired:
            pass
        duration = time.time() - start_time

        target_methods = set()

        converted_trace_data = TraceParser.get_trace_data_well_formatted(log_path)
        for line in converted_trace_data:
            target_methods.add(
                ' '.join(line.strip().split(' ')[2:]).split('(')[0].strip())

        return {
            'methods': list(target_methods),
            'duration': duration
        }

    def __is_benchmark_targeting_changed_methods(self, changed_methods: dict[str, list[str]], # The list of changed methods in the commit
                                                 target_methods: list[str] # The list of methods that the benchmark executes
                                                 ) -> Tuple[bool, dict[str, list[str]]]:
        
        def normalize_method_name(method: str) -> str:
            # Remove parameters but keep generic type information
            method = method.split('(')[0]
            
            # Handle array notation
            method = method.replace("[]", "")
            
            # Split into parts (return type, class name, method name)
            parts = method.split()
            if len(parts) > 1:
                method_name = '.'.join(parts[-1:])  # Include class name and method name
            else:
                method_name = parts[0]
            
            # Replace $ with . for inner classes
            method_name = method_name.replace('$', '.')
            
            # Remove synthetic method suffixes but keep generic type info
            method_name = re.sub(r'(\.\$\w+)(?=<|$)', '', method_name)
            
            # Handle constructor and static initializer methods
            method_name = method_name.replace(".<init>", ".constructor")
            method_name = method_name.replace(".<clinit>", ".static_initializer")
            
            # Remove generic type information for comparison
            method_name = re.sub(r'<[^>]+>', '', method_name)
            
            return method_name.lower()  # Convert to lowercase for case-insensitive comparison
        
        # Normalize target methods
        tf = {normalize_method_name(f) for f in target_methods}
        
        # We'll keep a set of method names without package info for fallback matching
        tf_reduced = {m.split('.')[-1] for m in tf}

        chosen_methods = {commit_hash: [] for commit_hash in changed_methods}
        
        for commit_hash, methods in changed_methods.items():
            for method in methods:
                normalized = normalize_method_name(method)
                
                if '.' in normalized:
                    if normalized in tf:
                        chosen_methods[commit_hash].append(method)
                else:
                    if normalized in tf_reduced:
                        chosen_methods[commit_hash].append(method)


        return any(methods for methods in chosen_methods.values()), chosen_methods

    def __minimize_and_distribute_methods(self, benchmarks: dict[str, dict[str, dict[str, Any]]]) -> dict[str, dict[str, dict[str, list[str]]]]:
        # Define a threshold for what counts as "significantly higher" in duration
        SIGNIFICANTLY_HIGHER_FACTOR = 2.0

        # Create a set of all methods to be covered for each commit
        all_methods = {}
        for benchmark_info in benchmarks.values():
            for commit_id, methods in benchmark_info['targets'].items():
                if commit_id not in all_methods:
                    all_methods[commit_id] = set()
                all_methods[commit_id].update(methods)

        # Create a list of benchmarks sorted by number of unique methods they cover and then by duration
        sorted_benchmarks = sorted(
            (
                benchmark, 
                benchmark_info['targets'], 
                benchmark_info['duration']
            )
            for benchmark, benchmark_info in benchmarks.items()
        )

        selected_benchmarks = {}
        covered_methods = {commit_id: set() for commit_id in all_methods}

        # Select benchmarks iteratively
        while any(covered_methods[commit_id] != all_methods[commit_id] for commit_id in all_methods):
            # Sort benchmarks by maximum new methods covered first, then by duration
            sorted_benchmarks = sorted(
                sorted_benchmarks,
                key=lambda x: (
                    -sum(len(set(methods) - covered_methods[commit_id]) for commit_id, methods in x[1].items()),
                    x[2]
                )
            )

            # Identify the best benchmark based on methods covered
            best_benchmark = sorted_benchmarks[0]
            best_duration = best_benchmark[2]

            # Check if other benchmarks provide similar coverage but with significantly lower duration
            alternative_benchmarks = [
                benchmark for benchmark in sorted_benchmarks[1:]
                if sum(len(set(methods) - covered_methods[commit_id]) for commit_id, methods in benchmark[1].items()) == 
                sum(len(set(methods) - covered_methods[commit_id]) for commit_id, methods in best_benchmark[1].items())
            ]
            
            if alternative_benchmarks:
                min_alternative_duration = min(benchmark[2] for benchmark in alternative_benchmarks) # type: ignore

                # If the best benchmark is significantly slower, consider alternatives
                if best_duration > min_alternative_duration * SIGNIFICANTLY_HIGHER_FACTOR:
                    best_benchmark = min(alternative_benchmarks, key=lambda x: x[2])
            
            # Now add the best benchmark to the selected benchmarks
            added_to_selected = False
            for commit_id, methods in best_benchmark[1].items():
                new_methods = set(methods) - covered_methods[commit_id]

                if new_methods:
                    if commit_id not in selected_benchmarks:
                        selected_benchmarks[commit_id] = {
                            best_benchmark[0]: {
                                "targets": [],
                                "duration": best_benchmark[2]
                            }
                        }
                    elif best_benchmark[0] not in selected_benchmarks[commit_id]:
                        selected_benchmarks[commit_id][best_benchmark[0]] = {
                            "targets": [],
                            "duration": best_benchmark[2]
                        }
                    
                    selected_benchmarks[commit_id][best_benchmark[0]]["targets"].extend(new_methods)
                    covered_methods[commit_id].update(new_methods)
                    added_to_selected = True

            if added_to_selected:
                # Remove the selected benchmark from the list
                sorted_benchmarks = [b for b in sorted_benchmarks if b[0] != best_benchmark[0]]

        return selected_benchmarks

    def __run_benchmark(self, benchmark_jar_path: str,
                                                 config_directory: str,
                                                 java_version: str) -> Union[NoneType, dict]:
        # Open all of the config files
        configs = [file for file in os.listdir(config_directory) if file.endswith('.yaml')]

        for config in configs:
            benchmark_name = config.replace('.yaml', '')
            config_path = os.path.join(config_directory, config)

            # Remove the previous log file (if exists)
            log_path = os.path.join(config_directory, 'ust', f'{benchmark_name}.log')
            if os.path.exists(log_path):
                os.remove(log_path)

            # Remove the previous JSON file (if exists)
            jmh_json_path = os.path.join(config_directory, 'jmh-results', f'{benchmark_name}.json')
            FileUtils.create_directory(os.path.dirname(jmh_json_path), remove_contents=True)

            # Check if we need to use LTTng
            if self.use_lttng:
                lttng_service = LTTngService(project_name=self.project_name,
                                             output_path=config_directory)
                lttng_service.start()

            # Run the benchmark
            mvn_service = MvnService()
            env = mvn_service.update_java_home(java_version)
            MvnService.remove_security_from_jar(benchmark_jar_path)
            process = subprocess.run([
                'java',
                f'-javaagent:{self.jib_path}=config={config_path}',
                '-jar',
                benchmark_jar_path,
                '-f', str(self.num_forks),
                '-wi', str(self.num_warmups),
                '-i', str(self.num_iterations),
                '-r', str(self.measurement_time),
                '-rf', 'json',
                '-rff', jmh_json_path,
                benchmark_name
            ], capture_output=True, shell=False, env=env)

            # Stop the LTTng tracing (if enabled)
            if self.use_lttng:
                lttng_service.stop()

            # Check if the process is successful
            if process.returncode != 0:
                Logger.error(f'Error while running the benchmark {benchmark_name}', num_indentations=self.printer_indent+1)
                return None
    
    def __update_java_version_everywhere(self, java_version: str) -> None:
        for root, _, files in os.walk(self.project_path):
            for file in files:
                if file == 'pom.xml':
                    pom_path = os.path.join(root, file)
                    
                    pom_service = PomService(pom_source=pom_path)
                    current_version = pom_service.get_java_version()

                    # If it is none, continue
                    if not current_version:
                        continue

                    pom_service.set_java_version(java_version)