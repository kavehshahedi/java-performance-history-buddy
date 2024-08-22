from typing import Optional
from git import Repo, Commit, Tree
import os

from jphb.utils.file_utils import FileUtils
from jphb.utils.printer import Printer

from jphb.services.pom_service import PomService


class BenchmarkPresenceMiner:

    def __init__(self, project_name: str,
                 project_path: str,
                 project_branch: str,
                 custom_benchmark: Optional[dict] = None,
                 **kwargs) -> None:
        self.project_name = project_name
        self.project_path = project_path
        self.project_branch = project_branch
        self.custom_benchmark = custom_benchmark

        self.printer_indent = kwargs.get('printer_indent', 0)
        self.check_root_pom = kwargs.get('check_root_pom', False)

    def __list_blobs(self, tree: Tree) -> list:
        blobs = []

        def traverse_tree(tree, path=''):
            for item in tree:
                if item.type == 'blob':
                    blobs.append(item)
                elif item.type == 'tree':
                    traverse_tree(item, os.path.join(path, item.name))

        traverse_tree(tree)
        return blobs

    def get_benchmarks_info(self, repo: Repo, commit: Commit, checkout: bool = True) -> tuple[bool, str, str]:
        there_is_dependency = False
        benchmark_directory = ''
        benchmark_name = ''

        if not self.custom_benchmark:
            # Get all the pom.xml files in the project (including the ones in the subdirectories)
            blobs = self.__list_blobs(commit.tree)
            for blob in blobs:
                if 'pom.xml' in blob.path:
                    # Read the content of the pom.xml file
                    pom_content = blob.data_stream.read().decode('utf-8')

                    # Check whether the pom.xml file contains a dependency to JMH
                    if 'jmh-core' in pom_content:
                        # Check if it isn't the main pom.xml file that is in the root directory of the project
                        # We should check the blob path to make sure that the pom.xml file is not in the root directory
                        if blob.path == 'pom.xml' and not self.check_root_pom:
                            continue

                        there_is_dependency = True
                        benchmark_directory = os.path.dirname(blob.path)

                        # Extract the benchmark name from the pom.xml file
                        pom_service = PomService(pom_content)
                        benchmark_name = pom_service.get_jar_name()

                        break
        else:
            if checkout:
                repo.git.checkout(commit.hexsha)
            benchmark_directory = self.custom_benchmark['directory']
            pom_path = os.path.join(self.project_path, benchmark_directory, 'pom.xml')
            if not FileUtils.is_path_exists(pom_path):
                return there_is_dependency, benchmark_directory, benchmark_name
            
            pom_service = PomService(pom_path)
            benchmark_name = pom_service.get_jar_name()
            there_is_dependency = True

        return there_is_dependency, benchmark_directory, benchmark_name

    def mine(self) -> int:
        repo = Repo(self.project_path)

        counter = 0
        total_commits = sum(1 for _ in repo.iter_commits(self.project_branch))
        for commit_index, commit in enumerate(repo.iter_commits(self.project_branch), start=1):
            commit_folder = os.path.join('results', self.project_name, 'commits', commit.hexsha)
            benchmark_file_path = os.path.join(commit_folder, 'jmh_dependency.json')
            # Check if the commit has already been mined
            if FileUtils.is_path_exists(benchmark_file_path):
                Printer.success(f'({commit_index}/{total_commits}) Commit {commit.hexsha} has already been checked', num_indentations=self.printer_indent)
                counter += 1
                continue

            there_is_dependency, benchmark_directory, benchmark_name = self.get_benchmarks_info(repo, commit)

            if there_is_dependency:
                Printer.success(f'({commit_index}/{total_commits}) Commit {commit.hexsha} contains a dependency to JMH', num_indentations=self.printer_indent)

                # Create an info file to indicate that the commit contains a dependency to JMH
                FileUtils.write_json_file(benchmark_file_path, 
                                          {'benchmark_directory': benchmark_directory, 'benchmark_name': benchmark_name})

                counter += 1
            else:
                Printer.warning(f'({commit_index}/{total_commits}) Commit {commit.hexsha} does not contain a dependency to JMH', num_indentations=self.printer_indent)

        Printer.separator(num_indentations=self.printer_indent)
        Printer.info(f'Project {self.project_name} has {counter} commits out of {total_commits} that contain a dependency to JMH', num_indentations=self.printer_indent, bold=True)

        return counter