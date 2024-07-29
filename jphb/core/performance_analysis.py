import re
from collections import defaultdict, deque
import os

# Regular expressions for parsing trace lines
enter_pattern = re.compile(r'\[(\d+)\] ENTER (.+)')
exit_pattern = re.compile(r'\[(\d+)\] EXIT (.+)')


class PerformanceAnalysis:
    def __init__(self, trace_data_path):
        with open(trace_data_path, 'r') as trace_file:
            trace_data = trace_file.readlines()
        self.trace_data = trace_data

    def analyze(self):
        # Dictionaries to store times
        call_stack = deque()
        total_execution_times = defaultdict(int)
        self_execution_times = defaultdict(int)
        call_counts = defaultdict(int)
        min_self_times = defaultdict(lambda: float('inf'))
        max_self_times = defaultdict(lambda: float('-inf'))

        # Parse the trace data
        for line in self.trace_data:
            if 'ENTER' in line:
                match = enter_pattern.match(line)
                if match:
                    timestamp, function = match.groups()
                    call_stack.append((function, int(timestamp)))
                    call_counts[function] += 1
            elif 'EXIT' in line:
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