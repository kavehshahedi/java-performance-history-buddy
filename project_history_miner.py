import json
import subprocess
import re
import os
from xml.etree import ElementTree as ET
from pathlib import Path
from multiprocessing import Pool, cpu_count

from git import Repo

BASE_PROJECT_PATH = '/home/kavehshahedi/Documents/Projects/perf2vec/target-projects'
POS_NS = {'pos': 'http://www.srcML.org/srcML/position'}

projects = [
    {
        'name': 'HdrHistogram',
        'branch': 'master',
        'path': os.path.join(BASE_PROJECT_PATH, 'HdrHistogram')
    },
    {
        'name': 'JCTools',
        'branch': 'master',
        'path': os.path.join(BASE_PROJECT_PATH, 'JCTools')
    },
    {
        'name': 'debezium',
        'branch': 'main',
        'path': os.path.join(BASE_PROJECT_PATH, 'debezium')
    },
    {
        'name': 'SimpleFlatMapper',
        'branch': 'master',
        'path': os.path.join(BASE_PROJECT_PATH, 'SimpleFlatMapper')
    },
    {
        'name': 'apm-agent-java',
        'branch': 'main',
        'path': os.path.join(BASE_PROJECT_PATH, 'apm-agent-java')
    },
    {
        'name': 'jetty',
        'branch': 'jetty-12.0.x',
        'path': os.path.join(BASE_PROJECT_PATH, 'jetty')
    },
    {
        'name': 'netty',
        'branch': '4.1',
        'path': os.path.join(BASE_PROJECT_PATH, 'netty')
    },
    {
        'name': 'rdf4j',
        'branch': 'main',
        'path': os.path.join(BASE_PROJECT_PATH, 'rdf4j')
    },
    {
        'name': 'vertx',
        'branch': 'master',
        'path': os.path.join(BASE_PROJECT_PATH, 'vertx')
    },
    {
        'name': 'zipkin',
        'branch': 'master',
        'path': os.path.join(BASE_PROJECT_PATH, 'zipkin')
    },
    {
        'name': 'prometheus',
        'branch': 'main',
        'path': os.path.join(BASE_PROJECT_PATH, 'prometheus')
    },
    {
        'name': 'Chronicle-Core',
        'branch': 'ea',
        'path': os.path.join(BASE_PROJECT_PATH, 'Chronicle-Core')
    },
    {
        'name': 'log4j2',
        'branch': '2.x',
        'path': os.path.join(BASE_PROJECT_PATH, 'log4j2')
    },
    {
        'name': 'hadoop',
        'branch': 'trunk',
        'path': os.path.join(BASE_PROJECT_PATH, 'hadoop')
    },
    {
        'name': 'camel',
        'branch': 'main',
        'path': os.path.join(BASE_PROJECT_PATH, 'camel')
    },
    {
        'name': 'kafka',
        'branch': 'trunk',
        'path': os.path.join(BASE_PROJECT_PATH, 'kafka')
    },
    {
        'name': 'cassandra',
        'branch': 'trunk',
        'path': os.path.join(BASE_PROJECT_PATH, 'cassandra')
    },
    {
        'name': 'spark',
        'branch': 'master',
        'path': os.path.join(BASE_PROJECT_PATH, 'spark')
    }
]

def get_method_class(function, root):
    if root is None or function is None:
        return ''
    
    for class_ in root.findall('.//class'):
        class_start = int(class_.attrib[f'{{{POS_NS["pos"]}}}start'].split(':')[0])
        class_end = int(class_.attrib[f'{{{POS_NS["pos"]}}}end'].split(':')[0])

        function_start = int(function.attrib[f'{{{POS_NS["pos"]}}}start'].split(':')[0])

        if class_start < function_start < class_end:
            package_name = ''.join(root.find('.//package').itertext()).replace('package', '').replace(';','').strip() if root.find('.//package') is not None else ''
            class_name = ''.join(class_.find('name').itertext()).strip() if class_.find('name') is not None else ''

            return f'{package_name}.{class_name}' if package_name else class_name
        
    return ''

def get_function_name(function):
    if function is None:
        return ''
    
    function_name = ''.join(function.find('name').itertext()).strip() if function.find('name') is not None else ''
    function_return_type = ''.join(function.find('type').itertext()).strip() if function.find('type') is not None else ''
    function_parameters = ''.join(function.find('parameter_list').itertext()).replace('\n', '').strip() if function.find('parameter_list') is not None else ''

    return re.sub(' +', ' ', f'{function_return_type} {function_name}{function_parameters}').strip()

def write_error(path, source, commit, previous_commit, extra_info):
    with open(os.path.join(path, 'error.txt'), 'w') as f:
        f.write(f'Source: {source}\n')
        f.write(f'Commit: {commit}\n')
        f.write(f'Previous Commit: {previous_commit}\n')
        
        for info in extra_info:
            f.write(f'{info}\n')

def process_project(project):
    project_name = project['name']
    project_branch = project['branch']
    project_path = project['path']

    repo = Repo(project_path)
    commits = list(repo.iter_commits(project_branch))

    # Iterate over all commits
    for commit in commits:
        # Skip the commits if they are already processed and saved in the output folder
        commit_folder = os.path.join('results', project_name, commit.hexsha)
        if os.path.exists(commit_folder):
            print(f'Commit {commit.hexsha} already processed')
            continue

        # Create a folder for the commit if it does not exist
        os.makedirs(commit_folder, exist_ok=True)

        # Skip the merge commits
        if len(commit.parents) > 1:
            print(f'Skipping merge commit {commit.hexsha}')
            continue

        # Check the file changes in the commit
        # If there is no file change in the commit on .java files, skip the commit
        if not commit.stats.files or not any(str(file).endswith('.java') for file in commit.stats.files):
            print(f'No .java file changes in commit {commit.hexsha}')
            continue

        try:
            # Checkout the commit
            repo.git.checkout(commit.hexsha)
        except:
            write_error(commit_folder, 'git checkout', commit.hexsha, None, [])
            print(f'Error in commit {commit.hexsha}')
            continue

        # Get the previous commit
        previous_commit = commit.parents[0] if commit.parents else None

        # Get the changed .java files in the new commit
        changed_files = [file for file in commit.stats.files if str(file).endswith('.java')]

        method_changes = {}
        # Iterate over all changed .java files
        for file in changed_files:
            # Check the changed methods in the file
            # If there is no method change in the file, skip the file
            try:
                if previous_commit:
                    previous_commit_hex = previous_commit.hexsha
                    diff = repo.git.diff(f'{previous_commit_hex}..{commit.hexsha}', file, unified=0)
                else:
                    previous_commit_hex = "None"
                    diff = repo.git.diff(commit.hexsha, file, unified=0)

                if not diff:
                    continue
            except:
                write_error(commit_folder, 'git diff', commit.hexsha, previous_commit_hex, [f'File: {file}'])
                print(f'Error in commit {commit.hexsha} for file {file}')
                continue

            method_changes[file] = {
                'methods': set(),
                'lines': set()
            }

            line_numbers = []
            current_line = 0
            for line in diff.splitlines():
                if line.startswith('@@'):
                    # Extract the start line number for the changed lines
                    parts = line.split(' ')
                    # parts[2] has the new file information starting with '+'
                    start_line = int(parts[2].split(',')[0][1:])
                    current_line = start_line
                elif line.startswith('+') and not line.startswith('+++'):
                    line_numbers.append(current_line)
                    current_line += 1
                elif line.startswith('-') and not line.startswith('---'):
                    continue
                else:
                    current_line += 1

            # We only consider the changes in the right side (new code)
            code = repo.git.show(f'{commit.hexsha}:{file}')
            
            temp_file_path = Path(f'temp{project_name}.java')
            try:
                with open(temp_file_path, 'w') as f:
                    f.write(code)
            except:
                write_error(commit_folder, 'write temp file', commit.hexsha, previous_commit_hex, [f'File: {file}'])
                print(f'Error in commit {commit.hexsha} for file {file}')
                continue

            process = subprocess.run(['srcml', temp_file_path, '--position'], capture_output=True) 
            xml = process.stdout.decode('utf-8')
            xml = re.sub('xmlns="[^"]+"', '', xml, count=1)

            root = ET.fromstring(xml)
            if root is None:
                write_error(commit_folder, 'srcml', commit.hexsha, previous_commit_hex, [f'File: {file}'])
                print(f'Error in commit {commit.hexsha} for file {file}')
                continue

            for function in root.findall('.//function'):
                # Get the function pos:start and pos:end attributes
                pos_start = function.attrib[f'{{{POS_NS["pos"]}}}start'].split(':')[0]
                pos_end = function.attrib[f'{{{POS_NS["pos"]}}}end'].split(':')[0]

                for line_number in line_numbers:
                    if int(pos_start) < line_number < int(pos_end):
                        method_name = get_function_name(function)
                        class_name = get_method_class(function, root)

                        try:
                            m_name_only = method_name.split('(')[0]
                            m_name_only = m_name_only.split(' ')[-1]
                            m_name_only = m_name_only + '(' + method_name.split('(')[1]

                            m_signature = method_name.split('(')[0]
                            m_signature = ' '.join(m_signature.split(' ')[0:-1])

                            method_changes[file]['methods'].add(f'{m_signature} {class_name}.{m_name_only}')
                            method_changes[file]['lines'].add(line_number)
                        except:
                            write_error(commit_folder, 'method_changes', commit.hexsha, previous_commit_hex, [f'File: {file}', f'Function: {method_name}'])
                            print(f'Error in commit {commit.hexsha} for file {file} and function {method_name}')
                            continue

            # Remove the temporary file
            os.remove(temp_file_path)

        # Remove the empty files
        method_changes = {file: data for file, data in method_changes.items() if len(data['methods']) > 0}

        # Convert the sets to lists
        method_changes = {file: {'methods': list(data['methods']), 'lines': list(data['lines'])} for file, data in method_changes.items()}

        if method_changes:
            # Save the method changes in a json file
            with open(os.path.join(commit_folder, 'method_changes.json'), 'w') as f:
                json.dump(method_changes, f, indent=4)

            # Save the commit details in a text file
            with open(os.path.join(commit_folder, 'commit_details.txt'), 'w') as f:
                f.write(f'Commit: {commit.hexsha}\n')
                f.write(f'Previous Commit: {previous_commit_hex if previous_commit else None}\n')
                f.write(f'Author: {commit.author.name} <{commit.author.email}>\n')
                f.write(f'Date: {commit.authored_datetime}\n')
                f.write(f'Message: {commit.message}\n')

            print(f'Commit {commit.hexsha} processed successfully')

if __name__ == '__main__':
    # Separate the projects to process them in parallel
    with Pool(cpu_count()) as p:
        p.map(process_project, projects)