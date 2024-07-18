import git
import requests
import dotenv
import os

dotenv.load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "INVALID_GIT_TOKEN")

class GitService:

    def __init__(self, owner: str, repo_name: str) -> None:
        self.owner = owner
        self.repo_name = repo_name

    def is_github_builable(self, commit_hash: str) -> bool:
        headers = {
            'Authorization': f'token {GITHUB_TOKEN}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        url = f'https://api.github.com/repos/{self.owner}/{self.repo_name}/commits/{commit_hash}/status'
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            status_data = response.json()
            statuses = status_data.get('statuses', [])
            
            if statuses:
                for status in statuses:
                    context = status['context']
                    state = status['state']
                    
                    if context == 'build':
                        if state != 'success':
                            # If the build status is not successful, we return False
                            return False
            else:
                # No statuses found. Hence, we assume it's successful
                return True
        else:
            # Since we can't get the status, we assume it's successful
            return True
        
        return True

    def __get_release_commits(self, repo: git.Repo) -> list:
        # Get all tags and their corresponding commits
        tags = repo.tags
        release_commits = []
        for tag in tags:
            commit = tag.commit
            release_commits.append((commit.committed_date, commit.hexsha, tag.name))

        # Sort release commits by date
        release_commits.sort()
        return release_commits

    def find_surrounding_releases(self, repo: git.Repo, commit_hash: str) -> tuple:
        release_commits = self.__get_release_commits(repo)

        target_commit = repo.commit(commit_hash)
        target_date = target_commit.committed_date

        prev_release_commit_hash = None
        next_release_commit_hash = None

        for (commit_date, commit_hash, _) in release_commits:
            if commit_date > target_date:
                next_release_commit_hash = commit_hash
                break
            prev_release_commit_hash = commit_hash

        return prev_release_commit_hash, next_release_commit_hash