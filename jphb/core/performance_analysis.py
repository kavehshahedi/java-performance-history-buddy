import re
from collections import defaultdict, deque
import os
import json

# Regular expressions for parsing trace lines
general_pattern = re.compile(r'\[(\d+)\] (S|E) (.+)')
enter_pattern = re.compile(r'\[(\d+)\] S (.+)')
exit_pattern = re.compile(r'\[(\d+)\] E (.+)')


class PerformanceAnalysis:
    def __init__(self, trace_data_path: str) -> None:
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

        self.traces = []

        self.trace_data = {}
        trace_file_directory = os.path.dirname(trace_data_path)
        # Iterate over all files in the directory
        for file in os.listdir(trace_file_directory):
            trace_file_name = trace_data_path.replace(f'{trace_file_directory}/', '').replace('.log', '')
            if trace_file_name in file:
                # Check if file is a log file or a json file
                timestamp = file.replace(f'{trace_file_name}_', '').replace('.log', '').replace('.json', '')

                if file.endswith('.log'): # The trace data
                    with open(f'{trace_file_directory}/{file}', 'r') as f:
                        self.trace_data[timestamp] = self.trace_data.get(timestamp, {})
                        self.trace_data[timestamp]['trace'] = f.readlines()
                elif file.endswith('.json'): # The metadata (of the trace data)
                    with open(f'{trace_file_directory}/{file}', 'r') as f:
                        self.trace_data[timestamp] = self.trace_data.get(timestamp, {})
                        self.trace_data[timestamp]['metadata'] = json.load(f)

        for timestamp, data in self.trace_data.items():
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
            self.traces.extend(trace_data)

    def analyze(self) -> dict:
        # Dictionaries to store times
        call_stack = deque()
        total_execution_times = defaultdict(int)
        self_execution_times = defaultdict(int)
        call_counts = defaultdict(int)
        min_self_times = defaultdict(lambda: float('inf'))
        max_self_times = defaultdict(lambda: float('-inf'))

        # Parse the trace data
        for line in self.traces:
            if re.match(enter_pattern, line):
                match = enter_pattern.match(line)
                if match:
                    timestamp, function = match.groups()
                    call_stack.append((function, int(timestamp)))
                    call_counts[function] += 1
            elif re.match(exit_pattern, line):
                match = exit_pattern.match(line)
                if match:
                    timestamp, function = match.groups()
                    exit_time = int(timestamp)
                    if call_stack and call_stack[-1][0] == function:
                        enter_function, enter_time = call_stack.pop()
                        duration = exit_time - enter_time

                        # Update total execution times
                        total_execution_times[function] += duration

                        # Update min and max self times
                        min_self_times[function] = min(min_self_times[function], duration)
                        max_self_times[function] = max(max_self_times[function], duration)

                        # Adjust the parent's self time
                        if call_stack:
                            parent_function, _ = call_stack[-1]
                            self_execution_times[parent_function] -= duration

                        # Add the duration to self time of this function
                        self_execution_times[function] += duration

        # Calculate average self time
        average_self_times = {function: self_execution_times[function] / call_counts[function]
                              for function in self_execution_times}

        output = {}
        for function in total_execution_times:
            output[function] = {
                'total_execution_time': total_execution_times[function],
                'self_execution_time': self_execution_times[function],
                'average_self_time': average_self_times[function],
                'cumulative_execution_time': total_execution_times[function],
                'min_execution_time': min_self_times[function],
                'max_execution_time': max_self_times[function],
                'call_count': call_counts[function]
            }

        return output

    def convert_time_units(self, ns):
        if ns < 1_000:
            return f'{ns} ns'
        elif ns < 1_000_000:
            return f'{ns / 1_000:.3f} µs'
        elif ns < 1_000_000_000:
            return f'{ns / 1_000_000:.3f} ms'
        elif ns < 60_000_000_000:
            return f'{ns / 1_000_000_000:.3f} s'
        else:
            return f'{ns / 60_000_000_000:.3f} m'