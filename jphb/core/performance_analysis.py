import re
import os
import json
from collections import deque, defaultdict
from scipy import stats
import numpy as np

# Regular expressions for parsing trace lines
general_pattern = re.compile(r'\[(\d+)\] (S|E) (.+)')
enter_pattern = re.compile(r'\[(\d+)\] S (.+)')
exit_pattern = re.compile(r'\[(\d+)\] E (.+)')

class PerformanceAnalysis:
    def __init__(self, trace_data_path: str) -> None:
        self.trace_data_path = trace_data_path
        self.trace_file_directory = os.path.dirname(trace_data_path)
        self.trace_file_name = trace_data_path.replace(f'{self.trace_file_directory}/', '').replace('.log', '')
        self.z_threshold = 3.0  # Z-score threshold for outlier removal

    def analyze(self) -> dict:
        total_times = defaultdict(list)
        self_times = defaultdict(list)
        call_counts = defaultdict(int)

        call_stack = deque()

        for line in self._batch_process_traces():
            self._process_line(line, call_stack, total_times, self_times, call_counts)

        output = {}
        for function in total_times:
            cleaned_total_times = self._remove_outliers(total_times[function])
            cleaned_self_times = self._remove_outliers(self_times[function])
            
            if cleaned_total_times and cleaned_self_times:  # Check if lists are not empty after outlier removal
                output[function] = {
                    'total_execution_time': int(np.sum(cleaned_total_times)),
                    'self_execution_time': int(np.sum(cleaned_self_times)),
                    'average_self_time': float(np.mean(cleaned_self_times)),
                    'cumulative_execution_time': int(np.sum(cleaned_total_times)),
                    'min_execution_time': int(np.min(cleaned_total_times)),
                    'max_execution_time': int(np.max(cleaned_total_times)),
                    'call_count': len(cleaned_total_times)  # This is now the count after outlier removal
                }
            else:
                # Handle the case where all data points were considered outliers
                output[function] = {
                    'total_execution_time': 0,
                    'self_execution_time': 0,
                    'average_self_time': 0,
                    'cumulative_execution_time': 0,
                    'min_execution_time': 0,
                    'max_execution_time': 0,
                    'call_count': 0
                }

        return output

    def _remove_outliers(self, data):
        if len(data) < 2:  # Need at least 2 data points to calculate z-score
            return data
        z_scores = np.abs(stats.zscore(data))
        return [d for d, z in zip(data, z_scores) if z < self.z_threshold]

    def _process_line(self, line, call_stack, total_times, self_times, call_counts):
        if (match := re.match(enter_pattern, line)):
            timestamp, function = match.groups()
            call_stack.append((function, int(timestamp), 0))  # function, start time, child time
            call_counts[function] += 1
        elif (match := re.match(exit_pattern, line)):
            timestamp, function = match.groups()
            exit_time = int(timestamp)
            if call_stack and call_stack[-1][0] == function:
                _, start_time, child_time = call_stack.pop()
                total_time = exit_time - start_time
                self_time = total_time - child_time

                total_times[function].append(total_time)
                self_times[function].append(self_time)

                if call_stack:
                    parent_function, parent_start, parent_child_time = call_stack.pop()
                    call_stack.append((parent_function, parent_start, parent_child_time + total_time))

    def _batch_process_traces(self):
        for file in sorted(os.listdir(self.trace_file_directory)):
            if self.trace_file_name in file:
                timestamp = file.replace(f'{self.trace_file_name}_', '').replace('.log', '').replace('.json', '')
                
                if file.endswith('.log'):
                    log_file = f'{self.trace_file_directory}/{file}'
                    json_file = f'{self.trace_file_directory}/{self.trace_file_name}_{timestamp}.json'
                    
                    if os.path.exists(json_file):
                        yield from self._process_trace_file(log_file, json_file)

    def _process_trace_file(self, log_file, json_file):
        with open(json_file, 'r') as f:
            metadata = json.load(f)
        
        log_time_difference = metadata['log_time_difference']
        method_signature_hash = {v: k for k, v in metadata['method_signature_hash'].items()}

        with open(log_file, 'r') as f:
            for line in f:
                match = general_pattern.match(line)
                if match:
                    time, start_or_end, method = match.groups()
                    time = int(time) + log_time_difference
                    method = method_signature_hash.get(method, method)
                    yield f'[{time}] {start_or_end} {method}'

    @staticmethod
    def get_trace_data_well_formatted(trace_data_path: str) -> list[str]:
        """
        Here, we want to parse the trace data with their metadata to analyze the performance of the project.

        The reasons for using metadata are:
            - The log time difference is used to adjust the time of the trace data.
                -- Since the original times in the log files are reduced in character lenght for storage usage.
            - The method signature hash is used to map the method signatures to their original form.
                -- Again, we wanted to reduce the character length for storage usage.

        Steps:
            1. Read each trace data and its metadata (they are separated by timestamp).
            2. Combine the trace data and metadata.
            3. Aggregate the trace data in a single list.
        """
        
        traces = []

        trace_data = {}
        trace_file_directory = os.path.dirname(trace_data_path)
        trace_file_name = trace_data_path.replace(f'{trace_file_directory}/', '').replace('.log', '')
        
        # Iterate over all files in the directory
        for file in os.listdir(trace_file_directory):
            if trace_file_name in file:
                # Check if file is a log file or a json file
                timestamp = file.replace(f'{trace_file_name}_', '').replace('.log', '').replace('.json', '')

                if file.endswith('.log'): # The trace data
                    with open(f'{trace_file_directory}/{file}', 'r') as f:
                        trace_data[timestamp] = trace_data.get(timestamp, {})
                        trace_data[timestamp]['trace'] = f.readlines()
                elif file.endswith('.json'): # The metadata (of the trace data)
                    with open(f'{trace_file_directory}/{file}', 'r') as f:
                        trace_data[timestamp] = trace_data.get(timestamp, {})
                        trace_data[timestamp]['metadata'] = json.load(f)

        for timestamp, data in trace_data.items():
            # There are some cases that the trace data is not available (e.g., empty executions)
            if 'trace' not in data or 'metadata' not in data or not data['trace']:
                continue

            trace = data['trace']
            metadata = data['metadata']
            log_time_difference = metadata['log_time_difference']
            method_signature_hash = {v: k for k, v in metadata['method_signature_hash'].items()}

            trace_data = []
            for line in trace:
                match = general_pattern.match(line)
                if match:
                    time, start_or_end, method = match.groups()
                    time = int(time) + log_time_difference # Adjust the time
                    method = method_signature_hash.get(method, method) # Convert back to original method signature
                    line = f'[{time}] {start_or_end} {method}' # Update the line
                    trace_data.append(line)

            # Add the trace data to the list
            traces.extend(trace_data)

        return traces