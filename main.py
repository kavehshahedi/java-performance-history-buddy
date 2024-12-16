import random
import argparse
import os

from jphb.pipeline import Pipeline

BASE_PROJECT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'projects')

if __name__ == '__main__':
    random.seed(42)
    
    parser = argparse.ArgumentParser(description='Java Performance Evolution Buddy (JPerfEvo)',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    # Required arguments
    parser.add_argument('--name', type=str, help='Name of the project to analyze', required=True)
    parser.add_argument('--git', type=str, help='Git URL of the project to analyze', required=True)
    parser.add_argument('--package', type=str, help='Package name of the project to analyze', required=True)
    parser.add_argument('--benchmark-module', type=str, help='Benchmark module of the project to analyze')
    parser.add_argument('--custom-commits', type=str, help='Path to a file containing custom commits to analyze, one per line', default=None)

    # Optional arguments - Benchmarking Configuration
    parser.add_argument('--forks', type=int, help='Number of forks for the benchmarking process', default=3)
    parser.add_argument('--warmups', type=int, help='Number of warmups for the benchmarking process', default=0)
    parser.add_argument('--iterations', type=int, help='Number of iterations for the benchmarking process', default=5)
    parser.add_argument('--measurement-time', type=str, help='Measurement time for the benchmarking process (seconds)', default='10s')
    parser.add_argument('--max-instrumentations', type=int, help='Maximum number of instrumentations to apply for each method', default=100000)

    # Optional arguments - Tool Configuration
    parser.add_argument('--kernel', action='store_true', help='Enable kernel tracing (via LTTng)', default=False)
    parser.add_argument('--llm', action='store_true', help='Enable using LLM to aid method changes (via OpenAI services)', default=False)
    parser.add_argument('--email', action='store_true', help='Enable email notifications (via Google\'s mail services)', default=False)
    parser.add_argument('--use-db', action='store_true', help='Enable database (MongoDB)', default=False)
    parser.add_argument('--cloud-db', action='store_true', help='Enable cloud database (MongoDB Atlas) (only if --use-db is enabled)', default=False)

    args = parser.parse_args()

    pipeline = Pipeline(project_name=args.name,
                        project_git=args.git,
                        project_package=args.package,
                        project_benchmark_module=args.benchmark_module,
                        base_project_path=BASE_PROJECT_PATH,
                        custom_commits_path=args.custom_commits,
                        num_forks=args.forks,
                        num_warmups=args.warmups,
                        num_iterations=args.iterations,
                        measurement_time=args.measurement_time,
                        max_instrumentations=args.max_instrumentations,
                        use_lttng=args.kernel,
                        use_llm=args.llm,
                        use_email_notification=args.email,
                        use_db=args.use_db,
                        use_cloud_db=args.cloud_db)
    pipeline.run()
