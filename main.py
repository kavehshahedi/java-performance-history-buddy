import os
import json

from benchmark_executor import BenchmarkExecutor

BASE_PROJECT_PATH = 'C:\\Users\\eavkhas\\Personal\\Projects\\perf2vec-target-projects\\'

PROJECTS = [
    {
        'name': 'HdrHistogram',
        'branch': 'master',
        'path': os.path.join(BASE_PROJECT_PATH, 'HdrHistogram')
    }
]

if __name__ == '__main__':
    for project in PROJECTS:
        project_name = project['name']
        project_path = project['path']
        branch = project['branch']

        with open('candidate_commits.json', 'r') as f:
            candidate_commits = json.load(f)

        commits = [item['commit'] for item in candidate_commits[project_name]]

        executor = BenchmarkExecutor(project_name, project_path)
        # executor.execute(benchmark_directory, ["2b676dc50591dfc0ee2bba37e0740ce943ad2d5e"])
