import os
import tempfile
from typing import Optional
from git import Repo, Commit, NULL_TREE

from jphb.core.benchmark_presence_miner import BenchmarkPresenceMiner

from jphb.services.refactoring_miner_service import RefactoringMinerService
from jphb.services.java_service import JavaService
from jphb.services.srcml_service import SrcMLService
from jphb.services.llm_service import LLMService

from jphb.utils.file_utils import FileUtils
from jphb.utils.Logger import Logger


class ProjectChangeMiner:

    def __init__(self, project_name: str,
                 project_path: str,
                 project_branch: str,
                 custom_benchmark: Optional[dict] = None,
                 use_llm: bool = False,
                 **kwargs) -> None:
        self.project_name = project_name
        self.project_path = project_path
        self.project_branch = project_branch
        self.custom_benchmark = custom_benchmark

        self.use_llm = use_llm
        if use_llm:
            self.llm_service = LLMService()

        self.printer_indent = kwargs.get('printer_indent', 0)

    def __write_error(self, path: str, source: str, commit: str, previous_commit: str, extra_info: list) -> None:
        with open(os.path.join(path, 'error.txt'), 'w') as f:
            f.write(f'Source: {source}\n')
            f.write(f'Commit: {commit}\n')
            f.write(f'Previous Commit: {previous_commit}\n')
            
            for info in extra_info:
                f.write(f'{info}\n')

    def __is_file_new_in_commit(self, commit: Commit, parent: Commit, file_path: str) -> bool:
        # Get the diff between the current commit and its parent (or NULL_TREE for the initial commit)
        diffs = parent.diff(commit)
        
        # Check if the file was added in this commit
        for diff in diffs:
            if diff.a_path == file_path and diff.change_type == 'A':
                return True
        return False
    
    def __get_deleted_and_moved_files(self, commit: Commit, parent: Commit) -> tuple[list[str], list[tuple[str, str]]]:
        # Get the diff between the current commit and its parent (or NULL_TREE for the initial commit)
        diffs = parent.diff(commit)

        deleted_files = []
        moved_files = []

        # Check for deleted and moved files
        for diff in diffs:
            # Detect deleted files
            if diff.change_type == 'D':
                deleted_files.append(diff.a_path)
            # Detect renamed/moved files
            elif diff.change_type == 'R':
                moved_files.append((diff.a_path, diff.b_path))

        return deleted_files, moved_files

    def mine(self, force: bool = False, custom_commits: Optional[list[str]] = None, max_commits: Optional[int] = None) -> int:
        repo = Repo(self.project_path)

        # Iterate over all commits
        num_successful_commits = 0
        total_commits = sum(1 for _ in repo.iter_commits(self.project_branch))
        for commit_index, commit in enumerate(repo.iter_commits(self.project_branch), start=1):
            # Keep track of the number of changed methods
            num_changed_methods = 0

            # Check if we reached the maximum number of commits
            if max_commits and commit_index > max_commits:
                break

            # Check if there are custom commits to process
            if custom_commits and commit.hexsha not in custom_commits:
                continue

            # Skip the commits if they are already processed and saved in the output folder
            commit_folder = os.path.join('results', self.project_name, 'commits', commit.hexsha)
            if os.path.exists(commit_folder) and not force:
                Logger.success(f'({commit_index}/{total_commits}) Commit {commit.hexsha} already processed', num_indentations=self.printer_indent)
                continue

            # Create a folder for the commit if it does not exist
            os.makedirs(commit_folder, exist_ok=True)

            # Skip the merge commits
            if len(commit.parents) > 1:
                Logger.warning(f'({commit_index}/{total_commits}) Skipping merge commit {commit.hexsha}', num_indentations=self.printer_indent)
                continue

            # Check the file changes in the commit
            # If there is no file change in the commit on .java files, skip the commit
            if not commit.stats.files or not any(str(file).endswith('.java') for file in commit.stats.files):
                Logger.warning(f'({commit_index}/{total_commits}) No .java file changes in commit {commit.hexsha}', num_indentations=self.printer_indent)
                continue

            try:
                # Checkout the commit
                repo.git.checkout(commit.hexsha, force=True)
            except:
                self.__write_error(commit_folder, 'git checkout', commit.hexsha, 'None', [])
                Logger.error(f'({commit_index}/{total_commits}) Error in commit {commit.hexsha}', num_indentations=self.printer_indent)
                continue

            # Get the previous commit
            previous_commit = commit.parents[0] if commit.parents else None
            if not previous_commit:
                Logger.error(f'({commit_index}/{total_commits}) No previous commit for commit {commit.hexsha}', num_indentations=self.printer_indent)
                continue

            # Get the changed .java files in the new commit
            changed_files = [file for file in commit.stats.files if str(file).endswith('.java')]

            # Remove the changed files that are within the benchmark directory
            bench_presence_miner = BenchmarkPresenceMiner(self.project_name,
                                                          self.project_path,
                                                          self.project_branch,
                                                          custom_benchmark=self.custom_benchmark)
            there_is_dependency, benchmark_directory, _ = bench_presence_miner.get_benchmarks_info(repo=repo,
                                                                                                    commit=commit,
                                                                                                    checkout=False)
            if there_is_dependency:
                changed_files = [file for file in changed_files if not str(file).startswith(benchmark_directory)]
            else:
                # Since there is no dependency to JMH, we skip the commit
                Logger.warning(f'({commit_index}/{total_commits}) Commit {commit.hexsha} does not contain a dependency to JMH', num_indentations=self.printer_indent)
                continue

            # Remove the test java files
            changed_files = [file for file in changed_files if not any(substring in str(file).lower() for substring in ('/test',))]

            # Now we get the refactoring changes
            refactoring_miner = RefactoringMinerService(project_path=self.project_path)
            all_refactorings = refactoring_miner.mine(commit_hash=commit.hexsha)

            # Remove the deleted or moved files (since we check the new code for diff)
            deleted_files, moved_files = self.__get_deleted_and_moved_files(commit=commit, parent=previous_commit)
            deleted_mapped_files = {}
            for f_name in list(commit.stats.files.keys()):
                if not str(f_name).endswith('.java'):
                    continue

                if str(f_name) in deleted_files or any(str(f_name) in moved_file for moved_file in moved_files):
                    # Check its refactorings
                    f_refactorings = refactoring_miner.get_refactorings_for_file(all_refactorings, str(f_name))
                    is_replaced, new_file = refactoring_miner.is_file_replaced(f_refactorings, str(f_name))
                    if is_replaced and f_name in changed_files:
                        # Map the deleted file to the new file
                        deleted_mapped_files[new_file] = f_name

                    changed_files = [file for file in changed_files if file != f_name]

            # Check which files have been newly added in the new commit that were not in the previous commit entirely (i.e., not refactored)
            new_file_indexes = []
            for file_index, file_ in enumerate(changed_files):
                if self.__is_file_new_in_commit(commit=commit, parent=previous_commit, file_path=str(file_)):
                    new_file_indexes.append(file_index)
            changed_files = [file for i, file in enumerate(changed_files) if i not in new_file_indexes]

            method_changes = {}
            # Iterate over all changed .java files
            for file in changed_files:
                method_changes[file] = {
                    commit.hexsha: set(),
                    previous_commit.hexsha: set()
                }

                try:
                    new_file = str(repo.git.show(f'{commit.hexsha}:{file}')).encode('utf-8', errors='ignore').decode('utf-8')

                    if file in deleted_mapped_files:
                        old_file_name = deleted_mapped_files[file]
                    else:
                        old_file_name = file
                    old_file = str(repo.git.show(f'{previous_commit.hexsha}:{old_file_name}')).encode('utf-8', errors='ignore').decode('utf-8')
                except:
                    self.__write_error(commit_folder, 'git show', commit.hexsha, 'None', [])
                    Logger.error(f'Error in commit {commit.hexsha}', num_indentations=self.printer_indent)
                    continue

                # Remove the comments from the files (since we are comparing the methods)
                srcml_service = SrcMLService()
                new_file = srcml_service.remove_comments(new_file)
                old_file = srcml_service.remove_comments(old_file)

                # Save both files in temporary files
                new_file_path = tempfile.NamedTemporaryFile(delete=True, mode='w', suffix='.java')
                old_file_path = tempfile.NamedTemporaryFile(delete=True, mode='w', suffix='.java')
                
                new_file_path.write(new_file)
                new_file_path.seek(0)

                old_file_path.write(old_file)
                old_file_path.seek(0)

                java_service = JavaService()
                different_methods = java_service.get_different_methods(new_file_path.name, old_file_path.name)
                if different_methods is None:
                    self.__write_error(commit_folder, 'get_different_methods', commit.hexsha, previous_commit.hexsha, [])
                    Logger.error(f'Error in commit {commit.hexsha}', num_indentations=self.printer_indent)
                    continue

                # Close and delete the temporary files
                new_file_path.close()
                old_file_path.close()
                
                # NOTE: Temporary
                # Remove the methods that 'second' is null (i.e., the methods that are newly introduced in the new commit)
                different_methods = [diff for diff in different_methods if diff['second']]
                if len(different_methods) == 0:
                    continue

                srcml_service = SrcMLService()

                # If we are using LLM, we need to check if the code change is significant
                if self.use_llm:
                    new_file_methods = srcml_service.get_methods(new_file, with_body=True)
                    old_file_methods = srcml_service.get_methods(old_file, with_body=True)
                    
                    # Iterate over the different methods and check if the code change is significant
                    # If not, we remove the method from the list
                    indexes_to_remove = []
                    for i, diff in enumerate(different_methods):
                        new_method = None
                        old_method = None

                        # We need to find the method in the new and old files
                        for method_ in new_file_methods:
                            method_name = java_service.convert_method_signature(method_.split('{')[0])
                            if method_name == diff['first']:
                                new_method = method_
                                break

                        for method_ in old_file_methods:
                            method_name = java_service.convert_method_signature(method_.split('{')[0])
                            if method_name == diff['second']:
                                old_method = method_
                                break

                        # Check if the method is not found
                        if new_method is None or old_method is None:
                            continue
                        
                        # Check if the code change is significant
                        is_significant = self.llm_service.is_code_change_significant(new_method, old_method, wrap_codes=False)
                        if not is_significant:
                            indexes_to_remove.append(i)

                    # Remove the methods that are not significant
                    different_methods = [diff for i, diff in enumerate(different_methods) if i not in indexes_to_remove]

                num_changed_methods += len(different_methods)

                for file_, commit_, diff_key in [(file, commit, 'first'), (old_file_name, previous_commit, 'second')]:
                    file_methods = srcml_service.get_methods(repo.git.show(f'{commit_.hexsha}:{file_}'),
                                                             remove_comments=False)

                    for method_ in file_methods:
                        converted_method_name = java_service.convert_method_signature(method_)
                        if converted_method_name is None:
                            continue

                        for diff_method in different_methods:
                            if diff_key == 'first' and diff_method['first'] == converted_method_name: # type: ignore
                                method_changes[file][commit.hexsha].add(method_)
                            elif diff_key == 'second' and diff_method['second'] == converted_method_name: # type: ignore
                                method_changes[file][previous_commit.hexsha].add(method_)

            # Remove the empty files
            method_changes = {file: data for file, data in method_changes.items() if data[commit.hexsha] or data[previous_commit.hexsha]}

            # Convert the sets to lists
            method_changes = {file: {commit.hexsha: list(data[commit.hexsha]), previous_commit.hexsha: list(data[previous_commit.hexsha])} for file, data in method_changes.items()}

            # Change the structure of the method changes
            new_method_changes = {}
            for file, data in method_changes.items():
                for commit_hash, methods in data.items():
                    new_method_changes[commit_hash] = new_method_changes.get(commit_hash, {})
                    new_method_changes[commit_hash][file] = methods
            method_changes = new_method_changes

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

                num_successful_commits += 1

            Logger.success(f'({commit_index}/{total_commits}) Commit {commit.hexsha} processed successfully with {num_changed_methods} methods', num_indentations=self.printer_indent)

        return num_successful_commits