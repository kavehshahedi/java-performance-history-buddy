import os
import json
import time
import math
import random

from benchmark_executor import BenchmarkExecutor

BASE_PROJECT_PATH = '/home/kavehshahedi/Documents/Projects/perf2vec/target-projects'

with open('projects.json', 'r') as f:
    PROJECTS = json.load(f)

REQUIRED_DEPENDENCIES = [
    # {
    #     "group_id": "javax.xml.bind",
    #     "artifact_id": "jaxb-api",
    #     "version": "2.3.0"
    # },
    {
        "group_id": "javax.annotation",
        "artifact_id": "javax.annotation-api",
        "version": "1.3.2"
    }
]

def calculate_sample_size(confidence_level, margin_of_error, population_size):
    Z = 1.96  # Z-score for 95% confidence
    p = 0.5   # Proportion (maximum variability)
    E = margin_of_error

    n_0 = (Z**2 * p * (1 - p)) / E**2
    n = n_0 / (1 + ((n_0 - 1) / population_size))
    
    return math.ceil(n)

if __name__ == '__main__':
    os.sched_setaffinity(0, list(range(0, 16)))

    for project in PROJECTS:
        if project['name'] != 'rdf4j':
            continue

        project_name = project['name']
        project_path = os.path.join(BASE_PROJECT_PATH, project_name)
        branch = project['branch']
        target_package = project['target_package']
        git_info = project['git']
        if "custom_commands" in project:
            custom_commands = project['custom_commands']
        else:
            custom_commands = None  

        with open('candidate_commits.json', 'r') as f:
            candidate_commits = json.load(f)[project_name]

        # Sort candidate commits by number of changed lines
        for commit_ in candidate_commits:
            count = 0
            for file, data in commit_['method_changes'].items():
                count += len(data['lines'])
            commit_['line_count'] = count

        candidate_commits = sorted(candidate_commits, key=lambda x: x['line_count'], reverse=True)

        # candidate_commits = [c for c in candidate_commits if c['commit'] == '9240a21b461c1241e07e0ec1d5e4c50f5353db31']

        # Calculate sample size
        N = len(candidate_commits)
        confidence_level = 0.95
        margin_of_error = 0.05
        sample_size = calculate_sample_size(confidence_level, margin_of_error, N)

        # Systematic sampling
        k = N // sample_size
        start = random.randint(0, k-1)

        sampled_commits = []
        sampled_count = 0
        i = 0

        while sampled_count < sample_size and i < N:
            index = (start + i * k) % N
            candidate_commit = candidate_commits[index]

            commit_hash = candidate_commit['commit']
            previous_commit_hash = candidate_commit['previous_commit']
            jmh_dependency = candidate_commit['jmh_dependency']
            changed_methods = [str(m) for cm in candidate_commit['method_changes'].values() for m in cm['methods']]

            start_time = time.time()

            executor = BenchmarkExecutor(project_name, project_path)
            executed, performance_data = executor.execute(jmh_dependency=jmh_dependency,
                                                        current_commit_hash=commit_hash,
                                                        previous_commit_hash=previous_commit_hash,
                                                        changed_methods=changed_methods,
                                                        target_package=target_package,
                                                        git_info=git_info,
                                                        required_dependencies=REQUIRED_DEPENDENCIES,
                                                        custom_commands=custom_commands)

            if executed:
                sampled_commits.append(candidate_commit)
                sampled_count += 1

                if not os.path.exists('performance_data.json'):
                    with open('performance_data.json', 'w') as f:
                        json.dump({}, f)

                # Save the performance data
                with open('performance_data.json', 'r') as f:
                    data = json.load(f)

                    if project_name not in data:
                        data[project_name] = {}

                    data[project_name][commit_hash] = performance_data

                with open('performance_data.json', 'w') as f:
                    json.dump(data, f, indent=4)

            print(f'Execution time: {time.time() - start_time}')
            print('-' * 50)
            
            i += 1

        if sampled_count < sample_size:
            print(f"Only {sampled_count} suitable commits found out of requested {sample_size}")
