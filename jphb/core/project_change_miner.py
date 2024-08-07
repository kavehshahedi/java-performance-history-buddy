import os
from typing import Optional
from git import Repo

from jphb.core.benchmark_presence_miner import BenchmarkPresenceMiner

from jphb.services.refactoring_miner_service import RefactoringMinerService
from jphb.services.java_service import JavaService
from jphb.services.srcml_service import SrcMLService
from jphb.services.llm_service import LLMService

from jphb.utils.file_utils import FileUtils
from jphb.utils.printer import Printer


class ProjectChangeMiner:

    def __init__(self, project_name: str, project_path: str, project_branch: str, use_llm: bool = False, **kwargs) -> None:
        self.project_name = project_name
        self.project_path = project_path
        self.project_branch = project_branch
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

    def mine(self, force: bool = False, custom_commits: Optional[list[str]] = None) -> int:
        repo = Repo(self.project_path)

        # Iterate over all commits
        num_successful_commits = 0
        for commit in repo.iter_commits(self.project_branch):
            # Keep track of the number of changed methods
            num_changed_methods = 0

            # Check if there are custom commits to process
            if custom_commits and commit.hexsha not in custom_commits:
                continue

            # Skip the commits if they are already processed and saved in the output folder
            commit_folder = os.path.join('results', self.project_name, 'commits', commit.hexsha)
            if os.path.exists(commit_folder) and not force:
                Printer.success(f'Commit {commit.hexsha} already processed', num_indentations=self.printer_indent)
                continue

            # Create a folder for the commit if it does not exist
            os.makedirs(commit_folder, exist_ok=True)

            # Skip the merge commits
            if len(commit.parents) > 1:
                Printer.warning(f'Skipping merge commit {commit.hexsha}', num_indentations=self.printer_indent)
                continue

            # Check the file changes in the commit
            # If there is no file change in the commit on .java files, skip the commit
            if not commit.stats.files or not any(str(file).endswith('.java') for file in commit.stats.files):
                Printer.warning(f'No .java file changes in commit {commit.hexsha}', num_indentations=self.printer_indent)
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
            if not previous_commit:
                Printer.error(f'No previous commit for commit {commit.hexsha}', num_indentations=self.printer_indent)
                continue

            # Get the changed .java files in the new commit
            changed_files = [file for file in commit.stats.files if str(file).endswith('.java')]

            # Remove the changed files that are within the benchmark directory
            bench_presence_miner = BenchmarkPresenceMiner(self.project_name, self.project_path, self.project_branch)
            there_is_dependency, benchmark_directory, _ = bench_presence_miner.get_benchmarks_info(commit)
            if there_is_dependency:
                changed_files = [file for file in changed_files if not str(file).startswith(benchmark_directory)]

            # Remove the test java files
            changed_files = [file for file in changed_files if not any(substring in str(file).lower() for substring in ('/test',))]

            # Now we get the refactoring changes
            refactoring_miner = RefactoringMinerService(project_path=self.project_path)
            all_refactorings = refactoring_miner.mine(commit_hash=commit.hexsha)

            # Remove the deleted or moved files (since we check the new code for diff)
            deleted_mapped_files = {}
            for f_name, f_data in commit.stats.files.items():
                if not str(f_name).endswith('.java'):
                    continue

                if f_data['insertions'] == 0 and f_data['deletions'] == f_data['lines']:
                    # Check its refactorings
                    f_refactorings = refactoring_miner.get_refactorings_for_file(all_refactorings, str(f_name))
                    is_replaced, new_file = refactoring_miner.is_file_replaced(f_refactorings, str(f_name))
                    if is_replaced and f_name in changed_files:
                        # Map the deleted file to the new file
                        deleted_mapped_files[new_file] = f_name

                    changed_files = [file for file in changed_files if file != f_name]

            # Check which files have been newly added in the new commit that were not in the previous commit entirely (i.e., not refactored)
            for f_name, f_data in commit.stats.files.items():
                if not str(f_name).endswith('.java'):
                    continue

                if f_data['insertions'] == f_data['lines']:
                    if f_name not in deleted_mapped_files and f_name in changed_files:
                        changed_files = [file for file in changed_files if file != f_name]

            method_changes = {}
            # Iterate over all changed .java files
            for file in changed_files:
                method_changes[file] = {
                    commit.hexsha: set(),
                    previous_commit.hexsha: set()
                }

                new_file = repo.git.show(f'{commit.hexsha}:{file}')

                if file in deleted_mapped_files:
                    old_file_name = deleted_mapped_files[file]
                else:
                    old_file_name = file
                old_file = repo.git.show(f'{previous_commit.hexsha}:{old_file_name}')

                # Remove the comments from the files (since we are comparing the methods)
                srcml_service = SrcMLService()
                new_file = srcml_service.remove_comments(new_file)
                old_file = srcml_service.remove_comments(old_file)

                java_service = JavaService()
                different_methods = java_service.get_different_methods(new_file, old_file)
                if different_methods is None:
                    self.__write_error(commit_folder, 'get_different_methods', commit.hexsha, previous_commit.hexsha, [])
                    Printer.error(f'Error in commit {commit.hexsha}', num_indentations=self.printer_indent)
                    continue
                
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
                                                             remove_comments=True)

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

            Printer.success(f'Commit {commit.hexsha} processed successfully with {num_changed_methods} methods', num_indentations=self.printer_indent)

        return num_successful_commits