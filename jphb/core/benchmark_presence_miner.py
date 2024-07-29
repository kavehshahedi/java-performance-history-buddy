from git import Repo, Commit, Tree
import os
import re
import xml.etree.ElementTree as ET

from jphb.utils.file_utils import FileUtils
from jphb.utils.printer import Printer

from jphb.services.pom_service import PomService


class BenchmarkPresenceMiner:

    def __init__(self, project_name: str, project_path: str, project_branch: str, **kwargs) -> None:
        self.project_name = project_name
        self.project_path = project_path
        self.project_branch = project_branch

        self.printer_indent = kwargs.get('printer_indent', 0)

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

    def get_benchmarks_info(self, commit: Commit) -> tuple[bool, str, str]:
        there_is_dependency = False
        benchmark_directory = ''
        benchmark_name = ''

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
                    if blob.path == 'pom.xml':
                        continue

                    there_is_dependency = True
                    benchmark_directory = os.path.dirname(blob.path)

                    # Extract the benchmark name from the pom.xml file
                    pom_service = PomService(pom_content)
                    benchmark_name = pom_service.get_jar_name()

                    break

        return there_is_dependency, benchmark_directory, benchmark_name

    def mine(self) -> None:
        repo = Repo(self.project_path)
        commits = list(repo.iter_commits(self.project_branch))

        counter = 0
        for commit in commits[:]:
            commit_folder = os.path.join('results', self.project_name, 'commits', commit.hexsha)

            there_is_dependency, benchmark_directory, benchmark_name = self.get_benchmarks_info(commit)

            if there_is_dependency:
                # Create an info file to indicate that the commit contains a dependency to JMH
                FileUtils.write_json_file(os.path.join(commit_folder, 'jmh_dependency.json'), 
                                          {'benchmark_directory': benchmark_directory, 'benchmark_name': benchmark_name})

                counter += 1

        Printer.success(f'Project {self.project_name} has {counter} commits out of {len(commits)} that contain a dependency to JMH', num_indentations=self.printer_indent)