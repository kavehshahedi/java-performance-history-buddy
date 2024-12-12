import re
import os
import json

# Regular expressions for parsing trace lines
general_pattern = re.compile(r'\[(\d+)\] (S|E) (.+)')

class TraceParser:
    """
    This class is responsible for parsing the trace data and metadata to analyze the performance of the project.
    """

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