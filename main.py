import json
import random
import argparse
import os

from jphb.pipeline import Pipeline

BASE_PROJECT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'projects')

with open('projects.json', 'r') as f:
    PROJECTS = json.load(f)

if __name__ == '__main__':
    random.seed(42)
    
    parser = argparse.ArgumentParser(description='Java Performance History Buddy')
    parser.add_argument('project_name', type=str, help='Name of the project to analyze')
    parser.add_argument('--kernel', action='store_true', help='Enable kernel tracing', default=False)
    parser.add_argument('--llm', action='store_true', help='Enable using LLM to aid method changes', default=False)
    parser.add_argument('--email', action='store_true', help='Enable email notifications', default=False)
    parser.add_argument('--cloud-db', action='store_true', help='Enable cloud database', default=False)
    args = parser.parse_args()

    project = None
    for project_ in PROJECTS:
        if project_['name'] == args.project_name:
            project = project_
            break

    if project is None:
        raise ValueError(f'Project with name {args.project_name} not found')

    pipeline = Pipeline(project=project,
                        base_project_path=BASE_PROJECT_PATH,
                        use_lttng=args.kernel,
                        use_llm=args.llm,
                        use_email_notification=args.email,
                        use_cloud_db=args.cloud_db)
    pipeline.run()
