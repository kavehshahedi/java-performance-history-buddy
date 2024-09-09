import os
import time

from jphb.services.sampling_service import Sampling
from jphb.utils.file_utils import FileUtils
from jphb.core.project_change_miner import ProjectChangeMiner
from jphb.core.benchmark_presence_miner import BenchmarkPresenceMiner
from jphb.core.commit_candidator import CommitCandidator
from jphb.core.benchmark_executor import BenchmarkExecutor

from jphb.services.git_service import GitService
from jphb.services.db_service import DBService
from jphb.services.email_service import EmailService

from jphb.utils.Logger import Logger
from jphb.utils.file_utils import FileUtils

class Pipeline:

    def __init__(self, project: dict,
                 base_project_path: str,
                 use_lttng: bool = False,
                 use_llm: bool = False,
                 use_email_notification: bool = False,
                 use_cloud_db: bool = False) -> None:
        self.project_name = project['name']
        self.project_path = os.path.join(base_project_path, self.project_name)
        self.target_package = project['target_package']
        self.git_info = {
            'owner': project['git']['owner'],
            'repo': project['git']['repo'],
            'branch': project['git']['branch']
        }
        self.custom_benchmark = project.get('custom_benchmark', None)

        self.use_lttng = use_lttng
        self.use_llm = use_llm

        self.email_service = EmailService(project_name=self.project_name) if use_email_notification else None

        self.db_service = DBService(use_cloud_db=use_cloud_db)

    def run(self) -> None:
        # First we check if the candidate commits have already been selected
        candidate_commits_file_path = os.path.join('results', self.project_name, 'candidate_commits.json')
        if not FileUtils.is_path_exists(candidate_commits_file_path):
            # Step 1: Clone the project repository if it doesn't exist
            if not FileUtils.is_path_exists(self.project_path):
                Logger.info(f'Cloning {self.project_name}...', bold=True)
                git_service = GitService(owner=self.git_info['owner'], repo_name=self.git_info['repo'])
                cloned, num_commits, head_commit_hash = git_service.clone_repo(repo_path=self.project_path, branch=self.git_info['branch'])
                if not cloned:
                    Logger.error(f'Failed to clone {self.project_name}. Skipping...', bold=True, num_indentations=1)
                    return
                
                Logger.success(f'{self.project_name} cloned successfully.', bold=True, num_indentations=1)
                
                # Update the project information in the database
                self.db_service.update_project(project_name=self.project_name,
                                                head_commit=head_commit_hash,
                                                num_total_commits=num_commits)

            # Step 2: Mine project changes
            Logger.info('Mining project changes...', bold=True)
            pcm = ProjectChangeMiner(project_name=self.project_name, 
                                    project_path=self.project_path, 
                                    project_branch=self.git_info['branch'],
                                    custom_benchmark=self.custom_benchmark,
                                    use_llm=self.use_llm,
                                    printer_indent=1)
            num_mined_commits = pcm.mine(
                force=False
            )
            # exit()

            # Step 3: Mine benchmark presence
            Logger.separator()
            Logger.info('Mining benchmark presence...', bold=True)
            bpm = BenchmarkPresenceMiner(project_name=self.project_name,
                                        project_path=self.project_path,
                                        project_branch=self.git_info['branch'],
                                        custom_benchmark=self.custom_benchmark,
                                        check_root_pom=True,
                                        printer_indent=1)
            num_commits_with_benchmark = bpm.mine()

            # Step 4: Candidate commits
            Logger.separator()
            Logger.info('Selecting candidate commits...', bold=True)
            cc = CommitCandidator(project_name=self.project_name,
                                project_path=self.project_path,
                                project_git_info=self.git_info,
                                custom_benchmark=self.custom_benchmark,
                                printer_indent=1)
            candidate_commits = cc.select()

            # Save the candidate commits to the database
            self.db_service.save_candidate_commits(project_name=self.project_name,
                                                   candidate_commits=candidate_commits)

            # Update the project information in the database
            self.db_service.update_project(project_name=self.project_name,
                                           num_candidate_commits=len(candidate_commits),
                                           num_commits_with_benchmark=num_commits_with_benchmark,
                                           num_commits_with_changes=num_mined_commits)
        else:
            candidate_commits = FileUtils.read_json_file(candidate_commits_file_path)

        Logger.separator()
        Logger.info(f'Found {len(candidate_commits)} candidate commits for {self.project_name}.', bold=True)

        # Step 5: For each candidate commit, execute the benchmark and get performance data
        Logger.separator()
        Logger.info('Executing benchmarks...', bold=True)

        sampling = Sampling(candidate_commits)
        N, sample_size, k, start = sampling.sample()

        i = 0
        sampled_count = 0
        while sampled_count < sample_size and i < N:
            # Capture the start time
            start_time = time.time()

            # Get the candidate commit based on the systematic sampling
            index = (start + i * k) % N
            candidate_commit = candidate_commits[index]

            # Check if the commit has already been executed
            db_performance_data = self.db_service.get_performance_data(project_name=self.project_name,
                                                                       commit_hash=candidate_commit['commit'])
            if db_performance_data:
                Logger.info(f'Commit {i + 1}/{N} already processed. Skipping...', bold=True, num_indentations=1)
                Logger.separator(num_indentations=1)
                i += 1
                
                if db_performance_data['status']:
                    sampled_count += 1

                continue

            # This is for backward compatibility
            if self.custom_benchmark and 'module' in self.custom_benchmark:
                if 'benchmark_module' not in candidate_commit['jmh_dependency'] or candidate_commit['jmh_dependency']['benchmark_module'] is None:
                    candidate_commit['jmh_dependency']['benchmark_module'] = self.custom_benchmark['module']

            # Execute the benchmark
            executor = BenchmarkExecutor(project_name=self.project_name,
                                         project_path=self.project_path,
                                         printer_indent=1,
                                         use_lttng=self.use_lttng)
            executed, performance_data = executor.execute(jmh_dependency=candidate_commit['jmh_dependency'],
                                                        current_commit_hash=candidate_commit['commit'],
                                                        previous_commit_hash=candidate_commit['previous_commit'],
                                                        changed_methods={commit_hash: [m for method_ in files.values() for m in method_] for commit_hash, files in candidate_commit['method_changes'].items()},
                                                        target_package=self.target_package,
                                                        java_version=candidate_commit['java_version'])

            # If the benchmark was executed successfully, save the performance data
            if executed:
                sampled_count += 1

                # Load the performance data file
                performance_data_file_path = os.path.join('results', self.project_name, 'performance_data.json')
                performance_data_file = FileUtils.read_json_file(performance_data_file_path)

                # Update the performance data
                performance_data_file[candidate_commit['commit']] = performance_data

                # Save the performance data file
                FileUtils.write_json_file(performance_data_file_path, performance_data_file)

            # Save the performance data to the database
            self.db_service.save_performance_data(project_name=self.project_name,
                                                commit_hash=candidate_commit['commit'],
                                                status=executed,
                                                performance_data=performance_data if performance_data else {})

            Logger.info(f'Commit {i + 1}/{N} processed. {sampled_count} out of {sample_size} required samples are available.', bold=True, num_indentations=1)
            Logger.info(f'Execution time: {time.time() - start_time}', bold=True, num_indentations=1)
            Logger.separator(num_indentations=1)
            
            i += 1

        if sampled_count < sample_size:
            Logger.warning(f'Only {sampled_count} suitable commits found out of requested {sample_size}')

        # Update the project information in the database
        self.db_service.update_project(project_name=self.project_name,
                                       sample_size=sample_size,
                                       sampled_count=sampled_count)

        # Send an email notification (if enabled)
        if self.email_service:
            self.email_service.send_email(to_email=os.getenv('SMTP_TO_EMAIL', 'INVALID_EMAIL'),
                                    subject=f'JPHB Pipeline - {self.project_name} (Completed)',
                                    message=f"""The JPHB pipeline for {self.project_name} has been completed successfully.
                                    \nSample Size: {sample_size}
                                    \nSampled Count: {sampled_count})""")
