import os
import re
import subprocess
from typing import Dict

from jphb.utils.file_utils import FileUtils
from jphb.utils.Logger import Logger
from jphb.services.mvn_service import MvnService


class JvmService:
    """
    Service for collecting and analyzing JVM compilation and inlining data.
    """

    def __init__(self, project_name: str, printer_indent: int = 0) -> None:
        """
        Initialize the JvmService
        """
        self.project_name = project_name
        self.printer_indent = printer_indent

    def execute_jvm_profiling(self, commit_hash: str,
                              current_commit_hash: str,
                              benchmark_jar_path: str,
                              benchmarks: list,
                              java_version: str) -> None:
        """
        Collect JVM compilation and inlining data for the given benchmarks for the a specific commit.

        :param commit_hash: The commit hash to analyze
        :type commit_hash: str
        :param current_commit_hash: The current commit hash
        :type current_commit_hash: str
        :param benchmark_jar_path: The path to the benchmark jar file
        :type benchmark_jar_path: str
        :param benchmarks: The list of benchmarks to analyze
        :type benchmarks: list
        :param java_version: The version of Java to use
        :type java_version: str
        """
        # Create output directory
        output_dir = os.path.join('results', self.project_name, 'commits', commit_hash, 'jvm_data', current_commit_hash)
        FileUtils.create_directory(output_dir, remove_contents=True)

        # For each benchmark
        for benchmark_name in benchmarks:
            jvm_output_file = os.path.join(output_dir, f'{benchmark_name}_jvm.log')

            # Run the benchmark with JVM flags for printing compilation and inlining
            Logger.info(f'Collecting JVM data for benchmark {benchmark_name}...', num_indentations=self.printer_indent)

            mvn_service = MvnService()
            env = mvn_service.update_java_home(java_version)
            MvnService.remove_security_from_jar(benchmark_jar_path)

            with open(jvm_output_file, 'w') as f:
                try:
                    # Run with minimal iterations and forks to just get JVM data
                    process = subprocess.run([
                        'java',
                        '-XX:+PrintCompilation',
                        '-XX:+UnlockDiagnosticVMOptions',
                        '-XX:+PrintInlining',
                        '-jar',
                        benchmark_jar_path,
                        '-f', '1',
                        '-wi', '0',
                        '-i', '1',
                        '-r', '10ms',
                        benchmark_name
                    ], capture_output=True, shell=False, env=env, timeout=120)

                    # Save both stdout and stderr as they contain JVM compilation info
                    f.write("STDOUT:\n")
                    f.write(process.stdout.decode('utf-8', errors='replace'))
                    f.write("\nSTDERR:\n")
                    f.write(process.stderr.decode('utf-8', errors='replace'))

                    if process.returncode != 0:
                        Logger.warning(f'JVM data collection for {benchmark_name} returned non-zero exit code', num_indentations=self.printer_indent+1)
                    else:
                        Logger.success(f'JVM data collected for {benchmark_name}', num_indentations=self.printer_indent+1)
                except subprocess.TimeoutExpired:
                    f.write("ERROR: Process timed out after 120 seconds\n")
                    Logger.warning(f'JVM data collection for {benchmark_name} timed out', num_indentations=self.printer_indent+1)
                except Exception as e:
                    f.write(f"ERROR: {str(e)}\n")
                    Logger.error(f'Error collecting JVM data for {benchmark_name}: {str(e)}', num_indentations=self.printer_indent+1)

    def analyze_jvm_compilation_data(self, commit_hash: str, previous_commit_hash: str) -> Dict:
        """
        Analyze the collected JVM compilation and inlining data to identify differences
        between the current and previous commit.

        :param commit_hash: The commit hash to analyze
        :type commit_hash: str
        :param previous_commit_hash: The previous commit hash
        :type previous_commit_hash: str
        :return: The analysis results
        :rtype: Dict
        """
        Logger.info('Analyzing JVM compilation data...', num_indentations=self.printer_indent)

        analysis_dir = os.path.join('results', self.project_name, 'commits', commit_hash, 'jvm-analysis')
        FileUtils.create_directory(analysis_dir, remove_contents=True)

        current_jvm_data_dir = os.path.join('results', self.project_name, 'commits', commit_hash, 'jvm_data', commit_hash)
        previous_jvm_data_dir = os.path.join('results', self.project_name, 'commits', commit_hash, 'jvm_data', previous_commit_hash)

        if not os.path.exists(current_jvm_data_dir) or not os.path.exists(previous_jvm_data_dir):
            Logger.error('JVM data directories not found', num_indentations=self.printer_indent+1)
            return {}

        # Get all benchmark files from both directories
        current_files = {f.replace('_jvm.log', ''): os.path.join(current_jvm_data_dir, f)
                         for f in os.listdir(current_jvm_data_dir) if f.endswith('_jvm.log')}
        previous_files = {f.replace('_jvm.log', ''): os.path.join(previous_jvm_data_dir, f)
                          for f in os.listdir(previous_jvm_data_dir) if f.endswith('_jvm.log')}

        common_benchmarks = set(current_files.keys()) & set(previous_files.keys())

        results = {}
        for benchmark in common_benchmarks:
            Logger.info(f'Analyzing JVM data for benchmark {benchmark}...', num_indentations=self.printer_indent+1)

            current_file = current_files[benchmark]
            previous_file = previous_files[benchmark]

            # Extract compilation and inlining info
            current_compilation = self._extract_compilation_info(current_file)
            previous_compilation = self._extract_compilation_info(previous_file)

            diff = self._compare_compilation_info(previous_compilation, current_compilation)

            results[benchmark] = diff

            analysis_file = os.path.join(analysis_dir, f'{benchmark}_jvm_analysis.txt')
            with open(analysis_file, 'w') as f:
                f.write(f"JVM Compilation Analysis for {benchmark}\n")
                f.write("="*50 + "\n\n")

                f.write("COMPILATION DIFFERENCES:\n")
                f.write("-"*50 + "\n")
                for method, stats in diff.get('compilation_changes', {}).items():
                    f.write(f"Method: {method}\n")
                    f.write(f"  Previous: {stats.get('previous', 'Not compiled')}\n")
                    f.write(f"  Current: {stats.get('current', 'Not compiled')}\n")
                    f.write("\n")

                f.write("\nINLINING DIFFERENCES:\n")
                f.write("-"*50 + "\n")
                for method, inlined_methods in diff.get('inlining_changes', {}).items():
                    f.write(f"Method: {method}\n")
                    f.write("  Newly inlined:\n")
                    for m in inlined_methods.get('added', []):
                        f.write(f"    + {m}\n")
                    f.write("  No longer inlined:\n")
                    for m in inlined_methods.get('removed', []):
                        f.write(f"    - {m}\n")
                    f.write("\n")

        # Create a summary file
        summary_file = os.path.join(analysis_dir, 'jvm_analysis_summary.txt')
        with open(summary_file, 'w') as f:
            f.write("JVM Compilation Analysis Summary\n")
            f.write("="*50 + "\n\n")

            for benchmark, diff in results.items():
                f.write(f"Benchmark: {benchmark}\n")
                f.write("-"*50 + "\n")

                # Compilation changes summary
                compilation_changes = diff.get('compilation_changes', {})
                f.write(f"Compilation changes: {len(compilation_changes)} methods\n")

                # Inlining changes summary
                inlining_changes = diff.get('inlining_changes', {})
                total_added = sum(len(m.get('added', [])) for m in inlining_changes.values())
                total_removed = sum(len(m.get('removed', [])) for m in inlining_changes.values())
                f.write(f"Inlining changes: {len(inlining_changes)} methods, {total_added} newly inlined, {total_removed} no longer inlined\n")
                f.write("\n")

        Logger.success('JVM compilation analysis completed', num_indentations=self.printer_indent)
        return results

    def _extract_compilation_info(self, file_path: str) -> Dict:
        """
        Extract compilation and inlining information from JVM log file.

        :param file_path: The path to the JVM log file
        :type file_path: str
        :return: The compilation information
        :rtype: Dict
        """
        compilation_info = {
            'compiled_methods': {},  # Method name -> compilation level
            'inlined_methods': {}  # Caller -> list of inlined methods
        }

        with open(file_path, 'r', errors='replace') as f:
            content = f.read()

        # Extract compilation information
        compilation_pattern = r'(\d+)\s+(\d+)\s+(\w+)\s+(\S+)::(\S+)'
        for match in re.finditer(compilation_pattern, content):
            level = match.group(2)
            class_name = match.group(4)
            method_name = match.group(5)
            full_method = f"{class_name}.{method_name}"
            compilation_info['compiled_methods'][full_method] = level

        # Extract inlining information
        current_method = None
        inlining_pattern = r'^\s+@ (\d+)\s+(\S+)::(\S+)'
        inline_decision_pattern = r'^\s+\+\s+(\S+)::(\S+)'

        for line in content.splitlines():
            # Detect method being compiled
            match = re.search(inlining_pattern, line)
            if match:
                class_name = match.group(2)
                method_name = match.group(3)
                current_method = f"{class_name}.{method_name}"
                if current_method not in compilation_info['inlined_methods']:
                    compilation_info['inlined_methods'][current_method] = []

            # Detect inlined method
            if current_method:
                match = re.search(inline_decision_pattern, line)
                if match:
                    class_name = match.group(1)
                    method_name = match.group(2)
                    inlined_method = f"{class_name}.{method_name}"
                    compilation_info['inlined_methods'][current_method].append(inlined_method)

        return compilation_info

    def _compare_compilation_info(self, previous: Dict, current: Dict) -> Dict:
        """
        Compare compilation information between previous and current commit.

        :param previous: The compilation information for the previous commit
        :type previous: Dict
        :param current: The compilation information for the current commit
        :type current: Dict
        :return: The comparison results
        :rtype: Dict
        """
        result = {
            'compilation_changes': {},
            'inlining_changes': {}
        }

        # Compare compiled methods
        all_methods = set(previous['compiled_methods'].keys()) | set(current['compiled_methods'].keys())
        for method in all_methods:
            prev_level = previous['compiled_methods'].get(method)
            curr_level = current['compiled_methods'].get(method)

            if prev_level != curr_level:
                result['compilation_changes'][method] = {
                    'previous': prev_level,
                    'current': curr_level
                }

        # Compare inlined methods
        all_callers = set(previous['inlined_methods'].keys()) | set(current['inlined_methods'].keys())
        for caller in all_callers:
            prev_inlined = set(previous['inlined_methods'].get(caller, []))
            curr_inlined = set(current['inlined_methods'].get(caller, []))

            if prev_inlined != curr_inlined:
                result['inlining_changes'][caller] = {
                    'added': list(curr_inlined - prev_inlined),
                    'removed': list(prev_inlined - curr_inlined)
                }

        return result
