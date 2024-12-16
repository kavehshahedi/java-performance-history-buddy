from typing import Optional
from pymongo import MongoClient
import os
import dotenv

dotenv.load_dotenv()


class DBService:

    """
    This module is responsible for handling the database operations.
    We use MongoDB as our database in order to store the candidate commits and performance data.
    """

    def __init__(self, use_db: int = False,
                    db_name: str = os.getenv('DB_NAME', 'jphb'),
                    db_url: str = os.getenv('DB_URL', 'localhost:27017'),
                    use_cloud_db: bool = False) -> None:
        self.use_db = use_db
        if not use_db:
            return
        
        if use_cloud_db:
            db_url = os.getenv('CLOUD_DB_URL', db_url)
 
        self.client = MongoClient(db_url)
        self.db = self.client[db_name]

    def get_candidate_commits(self, project_name: str) -> dict:
        if not self.use_db:
            return {}
        
        candidate_commits = self.db['candidate_commits'].find_one({'project_name': project_name})
        return candidate_commits if candidate_commits else {}
    
    def save_candidate_commits(self, project_name: str, candidate_commits: list) -> None:
        if not self.use_db:
            return
        
        self.db['candidate_commits'].update_one({'project_name': project_name}, 
                                                {'$set': {'candidate_commits': candidate_commits}},
                                                upsert=True)
        
    def save_performance_data(self, project_name: str, commit_hash: str, status: bool, performance_data: dict) -> None:
        if not self.use_db:
            return
        
        self.db['performance_data'].update_one({'project_name': project_name, 'commit_hash': commit_hash},
                                                {'$set': {'status': status, 'performance_data': performance_data}},
                                                upsert=True)
        
    def get_performance_data(self, project_name: str, commit_hash: str) -> dict:
        if not self.use_db:
            return {}
        
        performance_data = self.db['performance_data'].find_one({'project_name': project_name, 'commit_hash': commit_hash})
        return performance_data if performance_data else {}
    
    def get_all_performance_data(self, project_name: str) -> list:
        if not self.use_db:
            return []
        
        return list(self.db['performance_data'].find({'project_name': project_name}))
    
    def update_project(self, project_name: str,
                       head_commit: Optional[str] = None,
                       num_total_commits: Optional[int] = None,
                       num_candidate_commits: Optional[int] = None,
                       num_commits_with_benchmark: Optional[int] = None,
                       num_commits_with_changes: Optional[int] = None,
                       sample_size: Optional[int] = None,
                       sampled_count: Optional[int] = None) -> None:
        if not self.use_db:
            return
        
        # Update the project information with non-None values
        update_info = {}
        if head_commit:
            update_info['head_commit'] = head_commit
        if num_total_commits:
            update_info['num_total_commits'] = num_total_commits
        if num_candidate_commits:
            update_info['num_candidate_commits'] = num_candidate_commits
        if num_commits_with_benchmark:
            update_info['num_commits_with_benchmark'] = num_commits_with_benchmark
        if num_commits_with_changes:
            update_info['num_commits_with_changes'] = num_commits_with_changes
        if sample_size:
            update_info['sample_size'] = sample_size
        if sampled_count:
            update_info['sampled_count'] = sampled_count

        self.db['projects'].update_one({'project_name': project_name}, {'$set': update_info}, upsert=True)
