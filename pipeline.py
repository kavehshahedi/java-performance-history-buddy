import os
import time

from mhm.services.sampling_service import Sampling
from mhm.utils.file_utils import FileUtils
from project_change_miner import ProjectChangeMiner
from benchmark_presence_miner import BenchmarkPresenceMiner
from commit_candidator import CommitCandidator
from benchmark_executor import BenchmarkExecutor

from mhm.utils.printer import Printer

class Pipeline:
    def __init__(self, project: dict, base_project_path: str) -> None:
        self.project_name = project['name']
        self.project_path = os.path.join(base_project_path, self.project_name)
        self.target_package = project['target_package']
        self.git_info = {
            'owner': project['git']['owner'],
            'repo': project['git']['repo'],
            'branch': project['git']['branch']
        }
        self.custom_commands = project.get('custom_commands', None)

    def run(self) -> None:
        # Step 1: Mine project changes
        Printer.info('Mining project changes...', bold=True)
        pcm = ProjectChangeMiner(project_name=self.project_name, 
                                 project_path=self.project_path, 
                                 project_branch=self.git_info['branch'],
                                 printer_indent=1)
        pcm.mine()

        # Step 2: Mine benchmark presence
        Printer.separator()
        Printer.info('Mining benchmark presence...', bold=True)
        bpm = BenchmarkPresenceMiner(project_name=self.project_name,
                                     project_path=self.project_path,
                                     project_branch=self.git_info['branch'],
                                     printer_indent=1)
        bpm.mine()

        # Step 3: Candidate commits
        Printer.separator()
        Printer.info('Selecting candidate commits...', bold=True)
        cc = CommitCandidator(project_name=self.project_name,
                              project_path=self.project_path,
                              project_git_info=self.git_info,
                              printer_indent=1)
        candidate_commits = cc.select()

        Printer.separator()
        Printer.info(f'Found {len(candidate_commits)} candidate commits for {self.project_name}.', bold=True)

        # Step 4: For each candidate commit, execute the benchmark and get performance data
        Printer.separator()
        Printer.info('Executing benchmarks...', bold=True)

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

            # Execute the benchmark
            executor = BenchmarkExecutor(project_name=self.project_name,
                                         project_path=self.project_path,
                                         printer_indent=1)
            executed, performance_data = executor.execute(jmh_dependency=candidate_commit['jmh_dependency'],
                                                        current_commit_hash=candidate_commit['commit'],
                                                        previous_commit_hash=candidate_commit['previous_commit'],
                                                        changed_methods=[str(m) for cm in candidate_commit['method_changes'].values() for m in cm['methods']],
                                                        target_package=self.target_package,
                                                        git_info=self.git_info,
                                                        custom_commands=self.custom_commands,
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

            Printer.info(f'Execution time: {time.time() - start_time}', bold=True, num_indentations=1)
            Printer.separator(num_indentations=1)
            
            i += 1

        if sampled_count < sample_size:
            Printer.warning(f"Only {sampled_count} suitable commits found out of requested {sample_size}")