import os
import json

from benchmark_executor import BenchmarkExecutor

BASE_PROJECT_PATH = 'C:\\Users\\eavkhas\\Personal\\Projects\\perf2vec-target-projects\\'

PROJECTS = [
    {
        'git': {
            'owner': 'HdrHistogram',
            'repo': 'HdrHistogram',
        },
        'name': 'HdrHistogram',
        'branch': 'master',
        'path': os.path.join(BASE_PROJECT_PATH, 'HdrHistogram'),
        'target_package': 'org.HdrHistogram',
    }
]

REQUIRED_DEPENDENCIES = [
    {
        "group_id": "javax.xml.bind",
        "artifact_id": "jaxb-api",
        "version": "2.3.0"
    }
]

if __name__ == '__main__':
    for project in PROJECTS:
        project_name = project['name']
        project_path = project['path']
        branch = project['branch']
        target_package = project['target_package']
        git_info = project['git']

        with open('candidate_commits.json', 'r') as f:
            candidate_commits = json.load(f)[project_name]

        # Sort candidate commits by number of changed lines
        for commit_ in candidate_commits:
            count = 0
            for file, data in commit_['method_changes'].items():
                count += len(data['lines'])
            commit_['line_count'] = count

        candidate_commits = sorted(candidate_commits, key=lambda x: x['line_count'], reverse=True)

        executor = BenchmarkExecutor(project_name, project_path)
        for candiate_commit in candidate_commits[:1]:
            print(f'Running benchmark for {candidate_commits.index(candiate_commit) + 1} out of {len(candidate_commits)}')

            commit_hash = candiate_commit['commit']
            previous_commit_hash = candiate_commit['previous_commit']
            jmh_dependency = candiate_commit['jmh_dependency']
            changed_methods = [str(m) for cm in candiate_commit['method_changes'].values() for m in cm['methods']]

            executed, performance_data = executor.execute(jmh_dependency=jmh_dependency,
                                                          current_commit_hash=commit_hash,
                                                          previous_commit_hash=previous_commit_hash,
                                                          changed_methods=changed_methods,
                                                          target_package=target_package,
                                                          git_info=git_info,
                                                          required_dependencies=REQUIRED_DEPENDENCIES)

            if executed:
                if not os.path.exists('performance_data.json'):
                    with open('performance_data.json', 'w') as f:
                        json.dump({}, f)

                # Save the performance data
                with open(f'performance_data.json', 'r') as f:
                    data = json.load(f)

                    if project_name not in data:
                        data[project_name] = {}

                    data[project_name][commit_hash] = performance_data

                with open(f'performance_data.json', 'w') as f:
                    json.dump(data, f, indent=4)

            print('-' * 50)
