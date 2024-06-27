import json
from git import Repo
import os
import re
import xml.etree.ElementTree as ET

BASE_PROJECT_PATH = 'C:\\Users\\eavkhas\\Personal\\Projects\\perf2vec-target-projects\\'

PROJECTS = [
    {
        'name': 'HdrHistogram',
        'branch': 'master',
        'path': os.path.join(BASE_PROJECT_PATH, 'HdrHistogram')
    }
]


def list_blobs(tree):
    blobs = []

    def traverse_tree(tree, path=''):
        for item in tree:
            if item.type == 'blob':
                blobs.append(item)
            elif item.type == 'tree':
                traverse_tree(item, os.path.join(path, item.name))

    traverse_tree(tree)
    return blobs


if __name__ == '__main__':
    for project in PROJECTS:
        project_path = project['path']
        project_name = project['name']
        project_branch = project['branch']

        repo = Repo(project_path)
        commits = list(repo.iter_commits(project_branch))

        counter = 0
        for commit in commits[:1000]:
            commit_folder = os.path.join('results', project_name, commit.hexsha)

            there_is_dependency = False
            benchmark_directory = ""
            benchmark_name = ""

            # Get all the pom.xml files in the project (including the ones in the subdirectories)
            blobs = list_blobs(commit.tree)
            for blob in blobs:
                if 'pom.xml' in blob.path:
                    # Read the content of the pom.xml file
                    pom_content = blob.data_stream.read().decode('utf-8')

                    # Check whether the pom.xml file contains a dependency to JMH
                    if 'jmh-core' in pom_content:
                        there_is_dependency = True
                        benchmark_directory = os.path.dirname(blob.path)

                        # Remove the namespace from the pom.xml file
                        pom_content = re.sub(r'\sxmlns="[^"]+"', '', pom_content, count=1)

                        root = ET.fromstring(pom_content)
                        final_name = root.find('.//finalName')
                        if final_name is not None:
                            benchmark_name = str(final_name.text).strip()

                        counter += 1
                        break

            if there_is_dependency:
                # Create an empty file to indicate that the commit contains a dependency to JMH
                with open(os.path.join(commit_folder, 'jmh_dependency.txt'), 'w') as f:
                    f.write(json.dumps({'benchmark_directory': benchmark_directory, 'benchmark_name': benchmark_name}))

        print(f'Project {project_name} has {counter} commits out of {len(commits)} that contain a dependency to JMH')
