import os
import json

BASE_PROJECT_PATH = '/home/kavehshahedi/Documents/Projects/perf2vec/target-projects'

with open('projects.json', 'r') as f:
    PROJECTS = json.load(f)

if __name__ == '__main__':
    candiate_commits = {}

    for project in PROJECTS:
        project_path = os.path.join(BASE_PROJECT_PATH, project['path'])
        project_name = project['name']
        project_branch = project['branch']

        if project_name != 'rdf4j':
            continue

        project_directory = os.path.join('results', project_name)

        candiate_commits[project_name] = []

        # Iterate over the subdirectories of the project directory
        for commit_folder in os.listdir(project_directory):
            commit_path = os.path.join(project_directory, commit_folder)

            # Check whether the commit folder contains a jmh_dependency.txt file (indicating that the commit contains a dependency to JMH)
            if not os.path.exists(os.path.join(commit_path, 'jmh_dependency.txt')):
                continue

            # Check if the commit folder contains a method_changes.json file (indicating that the commit contains method changes)
            if not os.path.exists(os.path.join(commit_path, 'method_changes.json')):
                continue

            # Read the content of the jmh_dependency.txt file
            with open(os.path.join(commit_path, 'jmh_dependency.txt'), 'r') as f:
                jmh_dependency = json.load(f)

            # Read the content of the method_changes.json file
            with open(os.path.join(commit_path, 'method_changes.json'), 'r') as f:
                method_changes = json.load(f)

            # Read the content of the commit_details.txt file
            with open(os.path.join(commit_path, 'commit_details.txt'), 'r') as f:
                commit_details = f.read().strip().split('\n')

            # Extract the commit hash, author, and message
            commit_hash = commit_details[0].split(': ')[1]
            previous_commit = commit_details[1].split(': ')[1]
            commit_message = commit_details[4].split(': ')[1]

            # Add the commit to the list of candidate commits
            candiate_commits[project_name].append({
                'commit': commit_hash,
                'previous_commit': previous_commit,
                'commit_message': commit_message,
                'jmh_dependency': {
                    'benchmark_directory': jmh_dependency.get('benchmark_directory', ''),
                    'benchmark_name': jmh_dependency.get('benchmark_name', '')
                },
                'method_changes': method_changes
            })

        print(f'Project {project_name} has {len(candiate_commits[project_name])} candidate commits')

    # Save the candidate commits to a JSON file
    with open('candidate_commits.json', 'w') as f:
        json.dump(candiate_commits, f, indent=4)
