import os
import time

from git import Repo

from mhm.utils.file_utils import FileUtils
from mhm.utils.printer import Printer

from mhm.services.git_service import GitService
from mhm.services.pom_service import PomService


class CommitCandidator:

    def __init__(self, project_name: str, project_path: str, project_git_info: dict, **kwargs) -> None:
        self.project_name = project_name
        self.project_path = project_path
        self.project_git_info = project_git_info
        self.candidate_commits = []

        self.printer_indent = kwargs.get('printer_indent', 0)

    def select(self, save_to_file: bool = True) -> list:
        project_directory = os.path.join('results', self.project_name)

        # Iterate over the subdirectories of the project directory
        for commit_folder in os.listdir(project_directory):
            commit_path = os.path.join(project_directory, commit_folder)

            # Check whether the commit folder contains a jmh_dependency.txt file (indicating that the commit contains a dependency to JMH)
            if not FileUtils.is_path_exists(os.path.join(commit_path, 'jmh_dependency.json')):
                continue

            # Check if the commit folder contains a method_changes.json file (indicating that the commit contains method changes)
            if not FileUtils.is_path_exists(os.path.join(commit_path, 'method_changes.json')):
                continue

            # Read the content of the jmh_dependency.json file
            jmh_dependency = FileUtils.read_json_file(os.path.join(commit_path, 'jmh_dependency.json'))

            # Read the content of the method_changes.json file
            method_changes = FileUtils.read_json_file(os.path.join(commit_path, 'method_changes.json'))

            # Read the content of the commit_details.json file
            commit_details = FileUtils.read_json_file(os.path.join(commit_path, 'commit_details.json'))

            # Extract the commit hash, author, and message
            commit_hash = commit_details['commit']
            previous_commit = commit_details['previous_commit']
            commit_message = commit_details['message']

            # Check if the project is buildable in GitHub Actions (indicating that the commit is buildable)
            git_service = GitService(owner=self.project_git_info['owner'], repo_name=self.project_git_info['repo'])
            buildable = git_service.is_github_builable(commit_hash)
            time.sleep(0.1) # Sleep for 100ms to avoid rate limiting
            if not buildable:
                continue

            # Find the Java version used in the commit
            repo = Repo(self.project_path)
            repo.git.checkout(commit_hash, force=True)
            pom_service = PomService(pom_source=os.path.join(self.project_path, 'pom.xml'))
            java_version = pom_service.get_java_version()
            if java_version is None:
                continue

            # If the Java version is below 8, let's upgrade it to 8 for now
            should_update_pom = False
            if float(java_version) < 1.8:
                java_version = "1.8"
                should_update_pom = True

            # Find the previous and next release commits
            prev_release_commit_hash, next_release_commit_hash = git_service.find_surrounding_releases(repo=repo, commit_hash=commit_hash)

            # Add the commit to the list of candidate commits
            self.candidate_commits.append({
                'commit': commit_hash,
                'previous_commit': previous_commit,
                'releases': {
                    'previous': prev_release_commit_hash,
                    'next': next_release_commit_hash
                },
                'commit_message': commit_message,
                'jmh_dependency': {
                    'benchmark_directory': jmh_dependency.get('benchmark_directory', ''),
                    'benchmark_name': jmh_dependency.get('benchmark_name', '')
                },
                'method_changes': method_changes,
                'java_version': {
                    'version': java_version,
                    'should_update_pom': should_update_pom
                }
            })

        # Sort the candidate commits by the number of lines changed
        for commit_ in self.candidate_commits:
            count = 0
            for _, data in commit_['method_changes'].items():
                count += len(data['lines'])
            commit_['num_changed_lines'] = count
        self.candidate_commits = sorted(self.candidate_commits, key=lambda x: x['num_changed_lines'], reverse=True)

        Printer.success(f'Project {self.project_name} has {len(self.candidate_commits)} candidate commits', num_indentations=self.printer_indent)

        # Save the candidate commits to a JSON file
        if save_to_file:
            FileUtils.write_json_file(os.path.join('results', self.project_name, 'candidate_commits.json'), self.candidate_commits)

        return self.candidate_commits
