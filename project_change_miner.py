import subprocess
import re
import os
from typing import Union
from xml.etree import ElementTree as ET
from pathlib import Path
from git import Repo

from benchmark_presence_miner import BenchmarkPresenceMiner

from mhm.utils.file_utils import FileUtils
from mhm.utils.printer import Printer

POS_NS = {'pos': 'http://www.srcML.org/srcML/position'}

class ProjectChangeMiner:

    def __init__(self, project_name: str, project_path: str, project_branch: str, **kwargs) -> None:
        self.project_name = project_name
        self.project_path = project_path
        self.project_branch = project_branch

        self.printer_indent = kwargs.get('printer_indent', 0)

    def __get_method_class(self, function: Union[ET.Element, None], root: Union[ET.Element, None]) -> str:
        if root is None or function is None:
            return ''
        
        for class_ in root.findall('.//class'):
            class_start = int(class_.attrib[f'{{{POS_NS["pos"]}}}start'].split(':')[0])
            class_end = int(class_.attrib[f'{{{POS_NS["pos"]}}}end'].split(':')[0])

            function_start = int(function.attrib[f'{{{POS_NS["pos"]}}}start'].split(':')[0])

            if class_start < function_start < class_end:
                package_element = root.find('.//package')
                class_name_element = class_.find('name')

                package_name = ''
                class_name = ''

                if package_element is not None:
                    package_name = ''.join(package_element.itertext()).replace('package', '').replace(';','').strip()
                if class_name_element is not None:
                    class_name = ''.join(class_name_element.itertext()).strip()

                return f'{package_name}.{class_name}' if package_name else class_name
            
        return ''

    def __get_function_name(self, function: Union[ET.Element, None]) -> str:
        if function is None:
            return ''
        
        function_name_element = function.find('name')
        function_name = ''
        if function_name_element is not None:
            function_name = ''.join(function_name_element.itertext()).strip()

        function_return_type_element = function.find('type')
        function_return_type = ''
        if function_return_type_element is not None:
            function_return_type = ''.join(function_return_type_element.itertext()).strip()

        function_parameters_element = function.find('parameter_list')
        function_parameters = ''
        if function_parameters_element is not None:
            function_parameters = ''.join(function_parameters_element.itertext()).replace('\n', '').strip()
        
        return re.sub(' +', ' ', f'{function_return_type} {function_name}{function_parameters}').strip()

    def __write_error(self, path: str, source: str, commit: str, previous_commit: str, extra_info: list) -> None:
        with open(os.path.join(path, 'error.txt'), 'w') as f:
            f.write(f'Source: {source}\n')
            f.write(f'Commit: {commit}\n')
            f.write(f'Previous Commit: {previous_commit}\n')
            
            for info in extra_info:
                f.write(f'{info}\n')

    def mine(self) -> None:
        repo = Repo(self.project_path)

        # Iterate over all commits
        for commit in repo.iter_commits(self.project_branch):
            # Skip the commits if they are already processed and saved in the output folder
            commit_folder = os.path.join('results', self.project_name, commit.hexsha)
            if os.path.exists(commit_folder):
                Printer.info(f'Commit {commit.hexsha} already processed', num_indentations=self.printer_indent)
                continue

            # Create a folder for the commit if it does not exist
            os.makedirs(commit_folder, exist_ok=True)

            # Skip the merge commits
            if len(commit.parents) > 1:
                Printer.info(f'Skipping merge commit {commit.hexsha}', num_indentations=self.printer_indent)
                continue

            # Check the file changes in the commit
            # If there is no file change in the commit on .java files, skip the commit
            if not commit.stats.files or not any(str(file).endswith('.java') for file in commit.stats.files):
                Printer.info(f'No .java file changes in commit {commit.hexsha}', num_indentations=self.printer_indent)
                continue

            try:
                # Checkout the commit
                repo.git.checkout(commit.hexsha, force=True)
            except:
                self.__write_error(commit_folder, 'git checkout', commit.hexsha, 'None', [])
                Printer.error(f'Error in commit {commit.hexsha}', num_indentations=self.printer_indent)
                continue

            # Get the previous commit
            previous_commit = commit.parents[0] if commit.parents else None

            # Get the changed .java files in the new commit
            changed_files = [file for file in commit.stats.files if str(file).endswith('.java')]

            # Remove the changed files that are within the benchmark directory
            bench_presence_miner = BenchmarkPresenceMiner(self.project_name, self.project_path, self.project_branch)
            there_is_dependency, benchmark_directory, _ = bench_presence_miner.get_benchmarks_info(commit)
            if there_is_dependency:
                changed_files = [file for file in changed_files if not str(file).startswith(benchmark_directory)]

            # Remove the test java files
            changed_files = [file for file in changed_files if not any(substring in str(file).lower() for substring in ('/test',))]

            method_changes = {}
            # Iterate over all changed .java files
            for file in changed_files:
                # Check the changed methods in the file
                # If there is no method change in the file, skip the file
                try:
                    if previous_commit:
                        previous_commit_hex = previous_commit.hexsha
                        diff = repo.git.diff(f'{previous_commit_hex}..{commit.hexsha}', file, unified=0)
                    else:
                        previous_commit_hex = "None"
                        diff = repo.git.diff(commit.hexsha, file, unified=0)

                    if not diff:
                        continue
                except:
                    self.__write_error(commit_folder, 'git diff', commit.hexsha, previous_commit_hex, [f'File: {file}'])
                    Printer.error(f'Error in commit {commit.hexsha} for file {file}', num_indentations=self.printer_indent)
                    continue

                method_changes[file] = {
                    'methods': set(),
                    'lines': set()
                }

                line_numbers = []
                current_line = 0
                for line in diff.splitlines():
                    if line.startswith('@@'):
                        # Extract the start line number for the changed lines
                        parts = line.split(' ')
                        # parts[2] has the new file information starting with '+'
                        start_line = int(parts[2].split(',')[0][1:])
                        current_line = start_line
                    elif line.startswith('+') and not line.startswith('+++'):
                        line_numbers.append(current_line)
                        current_line += 1
                    elif line.startswith('-') and not line.startswith('---'):
                        continue
                    else:
                        current_line += 1

                # We only consider the changes in the right side (new code)
                code = repo.git.show(f'{commit.hexsha}:{file}')
                
                temp_file_path = Path(f'temp{self.project_name}.java')
                try:
                    with open(temp_file_path, 'w') as f:
                        f.write(code)
                except:
                    self.__write_error(commit_folder, 'write temp file', commit.hexsha, previous_commit_hex, [f'File: {file}'])
                    Printer.error(f'Error in commit {commit.hexsha} for file {file}', num_indentations=self.printer_indent)
                    continue

                process = subprocess.run(['srcml', temp_file_path, '--position'], capture_output=True) 
                xml = process.stdout.decode('utf-8')
                xml = re.sub('xmlns="[^"]+"', '', xml, count=1)

                root = ET.fromstring(xml)
                if root is None:
                    self.__write_error(commit_folder, 'srcml', commit.hexsha, previous_commit_hex, [f'File: {file}'])
                    Printer.error(f'Error in commit {commit.hexsha} for file {file}', num_indentations=self.printer_indent)
                    continue

                for function in root.findall('.//function'):
                    # Get the function pos:start and pos:end attributes
                    pos_start = function.attrib[f'{{{POS_NS["pos"]}}}start'].split(':')[0]
                    pos_end = function.attrib[f'{{{POS_NS["pos"]}}}end'].split(':')[0]

                    for line_number in line_numbers:
                        if int(pos_start) < line_number < int(pos_end):
                            method_name = self.__get_function_name(function)
                            class_name = self.__get_method_class(function, root)

                            try:
                                m_name_only = method_name.split('(')[0]
                                m_name_only = m_name_only.split(' ')[-1]
                                m_name_only = m_name_only + '(' + method_name.split('(')[1]

                                m_signature = method_name.split('(')[0]
                                m_signature = ' '.join(m_signature.split(' ')[0:-1])

                                method_changes[file]['methods'].add(f'{m_signature} {class_name}.{m_name_only}')
                                method_changes[file]['lines'].add(line_number)
                            except:
                                self.__write_error(commit_folder, 'method_changes', commit.hexsha, previous_commit_hex, [f'File: {file}', f'Function: {method_name}'])
                                Printer.error(f'Error in commit {commit.hexsha} for file {file} and function {method_name}', num_indentations=self.printer_indent)
                                continue

                # Remove the temporary file
                os.remove(temp_file_path)

            # Remove the empty files
            method_changes = {file: data for file, data in method_changes.items() if len(data['methods']) > 0}

            # Convert the sets to lists
            method_changes = {file: {'methods': list(data['methods']), 'lines': list(data['lines'])} for file, data in method_changes.items()}

            if method_changes:
                # Save the method changes in a json file
                FileUtils.write_json_file(os.path.join(commit_folder, 'method_changes.json'), method_changes)

                # Save the commit details in a text file
                commit_info = {
                    'commit': commit.hexsha,
                    'previous_commit': previous_commit.hexsha if previous_commit else None,
                    'author': f'{commit.author.name} <{commit.author.email}>',
                    'date': commit.authored_datetime.strftime('%Y-%m-%d %H:%M:%S'),
                    'message': commit.message
                }
                FileUtils.write_json_file(os.path.join(commit_folder, 'commit_details.json'), commit_info)

                Printer.success(f'Commit {commit.hexsha} processed successfully', num_indentations=self.printer_indent)