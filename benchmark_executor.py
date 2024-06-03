from git import Repo
import os
import sys
import subprocess
import time

BASE_PROJECT_PATH = 'C:\\Users\\eavkhas\\Personal\\Projects\\perf2vec-target-projects\\'

PROJECTS = [
    {
        'name': 'HdrHistogram',
        'branch': 'master',
        'path': os.path.join(BASE_PROJECT_PATH, 'HdrHistogram'),
        'benchmark_directory': 'HdrHistogram-benchmarks'
    }
]

def is_project_buildable(project_path: str) -> bool:
    process = subprocess.run([
        'mvn',
        'clean',
        'install',
        '-DskipTests',
        '-Dmaven.javadoc.skip=true',
        '-Dcheckstyle.skip=true',
        '-Denforcer.skip=true'
    ], cwd=project_path, capture_output=True, shell=True)

    if process.returncode != 0:
        return False

    return True

def build_benchmarks(project_path: str, benchmark_directory: str) -> bool:
    process = subprocess.run([
        'mvn',
        'clean',
        'package'
    ], cwd=os.path.join(project_path, benchmark_directory), capture_output=True, shell=True)

    if process.returncode != 0:
        return False
    
    return True

def update_compile_version(pom_path:str, java_version: int) -> bool:
    try:
        with open(pom_path, 'r') as f:
            pom_content = f.read()

        # Replace any version with 17
        import re
        pom_content = re.sub(r'<source>.*</source>', f'<source>{java_version}</source>', pom_content)
        pom_content = re.sub(r'<target>.*</target>', f'<target>{java_version}</target>', pom_content)

        with open(pom_path, 'pom.xml', 'w') as f:
            f.write(pom_content)
    except Exception:
        return False

    return True

if __name__ == '__main__':
    for project in PROJECTS:
        project_path = project['path']
        project_name = project['name']
        project_branch = project['branch']
        project_benchmark_directory = project['benchmark_directory']

        repo = Repo(project_path)
        commits = list(repo.iter_commits(project_branch))

        for commit in commits:
            start_time = time.time()
            # Checkout the commit
            repo.git.checkout(commit)

            # Modify the pom.xml file to check Java compiling version
            ucv_main = update_compile_version(os.path.join(project_path, 'pom.xml'), 17)
            ucv_benchmark = update_compile_version(os.path.join(project_path, project_benchmark_directory, 'pom.xml'), 17)
            if not ucv_main or not ucv_benchmark:
                print(f'{commit.hexsha} can\'t update Java version')
                continue

            # Check whether the project is buildable
            is_buildable = is_project_buildable(project_path)
            if not is_buildable:
                print(f'{commit.hexsha} is not buildable')
                continue

            benchmark = build_benchmarks(project_path, project_benchmark_directory)
            if not benchmark:
                print(f'{commit.hexsha} can\'t build benchmarks')
                continue

            print(f'{commit.hexsha} successfully built benchmarks in {time.time() - start_time} seconds')