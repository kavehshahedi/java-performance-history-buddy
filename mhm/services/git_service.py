import git
import requests
import dotenv
import os
import bisect

dotenv.load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "INVALID_GIT_TOKEN")

class GitService:

    def __init__(self, owner: str, repo_name: str) -> None:
        self.owner = owner
        self.repo_name = repo_name

        self.build_history = {}

    def is_github_builable(self, commit_hash: str) -> bool:
        # First, we check if we have already checked the build status of this commit
        if commit_hash in self.build_history:
            return self.build_history[commit_hash]

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
                    
                    if 'build' in context.lower():
                        if state != 'success':
                            # If the build status is not successful, we return False
                            self.build_history[commit_hash] = False
                            return False
            else:
                # No statuses found. Hence, we assume it's successful
                self.build_history[commit_hash] = True
                return True
        else:
            # Since we can't get the status, we assume it's successful
            self.build_history[commit_hash] = True
            return True
        
        self.build_history[commit_hash] = True
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
        commit_dates = [date for date, _, _ in release_commits]

        target_commit = repo.commit(commit_hash)
        target_date = target_commit.committed_date

        # Find insertion point using binary search
        idx = bisect.bisect_left(commit_dates, target_date)

        # Initialize surrounding commits
        prev_release_commit_hash = None
        next_release_commit_hash = None

        # Find the next buildable release commit
        for i in range(idx, len(release_commits)):
            _, next_hash, _ = release_commits[i]
            if self.is_github_builable(next_hash):
                next_release_commit_hash = next_hash
                break

        # Find the previous buildable release commit
        for i in range(idx - 1, -1, -1):
            _, prev_hash, _ = release_commits[i]
            if self.is_github_builable(prev_hash):
                prev_release_commit_hash = prev_hash
                break

        return prev_release_commit_hash, next_release_commit_hash