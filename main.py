import os
import json
import random

from pipeline import Pipeline

BASE_PROJECT_PATH = '/home/kavehshahedi/Documents/Projects/perf2vec/target-projects'

with open('projects.json', 'r') as f:
    PROJECTS = json.load(f)

if __name__ == '__main__':
    random.seed(42)
    os.sched_setaffinity(0, list(range(0, 16)))

    for project in PROJECTS:
        if project['name'] != 'prometheus':
            continue

        pipeline = Pipeline(project=project, base_project_path=BASE_PROJECT_PATH)
        pipeline.run()