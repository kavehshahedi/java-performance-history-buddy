from difflib import SequenceMatcher
import re
import os
import json
from collections import deque, defaultdict
from scipy import stats
import numpy as np
from typing import Any, Dict, cast

class PerformanceAnalysis:
    """Analyze performance changes between two versions of a program
    
    Basically, we want to compare the execution times of functions between two versions (before and after).
    We will use the Mann-Whitney U test to determine if the changes are statistically significant.
    We will also use Cliff's Delta effect size to determine the magnitude of the changes.
    Accordingly, we will indicate if the changes are improvements, regressions, or unchanged (i.e., insignificant).

    Attributes:
    - trace_data_path: Path to the trace data file
    - trace_file_directory: Directory containing the trace data file
    - trace_file_name: Name of the trace data file
    - execution_times: A dictionary to store execution times for each function
    """
    def __init__(self, trace_data_path: str) -> None:
        """Initialize the PerformanceDiffSignificance object

        :param trace_data_path: Path to the trace data file
        :type trace_data_path: str
        """
        self.trace_data_path = trace_data_path
        self.trace_file_directory = os.path.dirname(trace_data_path)
        self.trace_file_name = trace_data_path.replace(f'{self.trace_file_directory}/', '').replace('.log', '')
        self.execution_times = defaultdict(list)  # Store execution times for each function

    def _process_line(self, line: str, call_stack: deque) -> None:
        """Process a single trace line and update execution times
        
        :param line: A single line from the trace file
        :type line: str
        :param call_stack: A stack to keep track of function calls
        :type call_stack: deque
        """
        enter_pattern = re.compile(r'\[(\d+)\] S (.+)')
        exit_pattern = re.compile(r'\[(\d+)\] E (.+)')

        if (match := re.match(enter_pattern, line)):
            timestamp, function = match.groups()
            call_stack.append((function, int(timestamp)))
        elif (match := re.match(exit_pattern, line)):
            timestamp, function = match.groups()
            exit_time = int(timestamp)
            if call_stack and call_stack[-1][0] == function:
                _, start_time = call_stack.pop()
                duration = exit_time - start_time
                self.execution_times[function].append(duration)

    def _batch_process_traces(self):
        """Process all trace files and yield each line"""
        general_pattern = re.compile(r'\[(\d+)\] (S|E) (.+)')
        for file in sorted(os.listdir(self.trace_file_directory)):
            if self.trace_file_name in file:
                timestamp = file.replace(f'{self.trace_file_name}_', '').replace('.log', '').replace('.json', '')
                
                if file.endswith('.log'):
                    log_file = f'{self.trace_file_directory}/{file}'
                    json_file = f'{self.trace_file_directory}/{self.trace_file_name}_{timestamp}.json'
                    
                    if os.path.exists(json_file):
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

    def _remove_outliers(self, data: np.ndarray, iqr_multiplier: float = 1.5) -> np.ndarray:
        """Remove outliers from data using IQR method

        :param data: An array of data points
        :type data: np.ndarray
        :param iqr_multiplier: A multiplier to adjust the IQR range, defaults to 1.5
        :type iqr_multiplier: float, optional
        :return: An array of data points with outliers removed
        :rtype: np.ndarray
        """
        if len(data) < 2:  # Need at least 2 data points to calculate IQR
            return data
        
        q1, q3 = np.percentile(data, [25, 75])
        iqr = q3 - q1
        lower_bound = q1 - (iqr_multiplier * iqr)
        upper_bound = q3 + (iqr_multiplier * iqr)
        return data[(data >= lower_bound) & (data <= upper_bound)]

    def analyze(self) -> None:
        """Process all trace files and collect execution times"""
        call_stack = deque()
        for line in self._batch_process_traces():
            self._process_line(line, call_stack)

    def calculate_cliffs_delta(self, x: np.ndarray, y: np.ndarray) -> float:
        """
        Calculate Cliff's Delta effect size using a more efficient approach.
        Returns a value between -1 and 1, where:
        - Close to +1: y is consistently greater than x
        - Close to -1: y is consistently less than x
        - Close to 0: no consistent difference

        :param x: An array of data points for the first sample
        :type x: np.ndarray
        :param y: An array of data points for the second sample
        :type y: np.ndarray
        :return: Cliff's Delta effect size
        :rtype: float
        """
        nx, ny = len(x), len(y)
        rank = stats.rankdata(np.concatenate((x, y)))
        rank_x = rank[:nx]
        rank_y = rank[nx:]
        
        u_x = np.sum(rank_x) - nx * (nx + 1) / 2
        u_y = np.sum(rank_y) - ny * (ny + 1) / 2
        
        return cast(float, (u_x - u_y) / (nx * ny))

    def interpret_cliffs_delta(self, d: float) -> str:
        """
        Interpret Cliff's Delta effect size based on common thresholds:
        negligible: |d| < 0.147
        small: |d| < 0.33
        medium: |d| < 0.474
        large: |d| >= 0.474

        :param d: Cliff's Delta effect size
        :type d: float
        :return: Interpretation of the effect size
        :rtype: str
        """
        abs_d = abs(d)
        if abs_d < 0.147:
            return "negligible"
        elif abs_d < 0.33:
            return "small"
        elif abs_d < 0.474:
            return "medium"
        else:
            return "large"

    def calculate_significance(self, other_analysis: 'PerformanceAnalysis') -> Dict[str, Dict[str, Any]]:
        """
        Calculate statistical significance of changes between two versions using
        Mann-Whitney U test (p-value) and Cliff's Delta (effect size)

        :param other_analysis: Another instance of PerformanceDiffSignificance for the other version
        :type other_analysis: PerformanceDiffSignificance
        :return: A dictionary of method changes with statistical significance
        :rtype: Dict[str, Any]
        """    
        methods_ = list(self.execution_times.keys())
        other_methods_ = list(other_analysis.execution_times.keys())
        matches: list[tuple[str, str]] = []

        # First, match methods with exact names
        for method in methods_[:]:
            if method in other_methods_:
                matches.append((method, method))
                methods_.remove(method)
                other_methods_.remove(method)

        # Then, find the most similar method for the remaining ones
        for method in methods_:
            if other_methods_:
                # Find the most similar method name in other_methods_
                most_similar_method = max(other_methods_, key=lambda x: SequenceMatcher(None, method, x).ratio())
                matches.append((method, most_similar_method))
                other_methods_.remove(most_similar_method)

        results = {}
        for method_, other_method in matches:
            before_times = np.array(self.execution_times[method_])
            after_times = np.array(other_analysis.execution_times[other_method])
            
            # Remove outliers using a more conservative method
            before_times = self._remove_outliers(before_times)
            after_times = self._remove_outliers(after_times)
            
            if len(before_times) < 2 or len(after_times) < 2:
                return {}
                
            # Calculate basic statistics
            before_median = np.median(before_times)
            after_median = np.median(after_times)
            
            if before_median == 0:
                return {}
                
            # Calculate relative change
            median_change = (after_median - before_median) / before_median
            
            # Perform Mann-Whitney U test
            _, p_value = stats.mannwhitneyu(
                before_times,
                after_times,
                alternative='two-sided'
            )
            
            # Calculate Cliff's Delta effect size
            effect_size = self.calculate_cliffs_delta(before_times, after_times)
            effect_size_interpretation = self.interpret_cliffs_delta(effect_size)
            
            # Determine change type based on both p-value and effect size
            is_statistically_significant = p_value < 0.05
            has_meaningful_effect = abs(effect_size) >= 0.147  # at least small effect
            
            if is_statistically_significant and has_meaningful_effect:
                if median_change > 0:
                    change_type = "regression"
                else:
                    change_type = "improvement"
            else:
                change_type = "unchanged"
                
            results[method_] = {
                "method_name": method_,
                "previous_method_name": other_method,
                "change_type": change_type,
                "median_change_percentage": median_change * 100,
                "p_value": p_value,
                "effect_size": effect_size,
                "effect_size_interpretation": effect_size_interpretation,
                "statistically_significant": int(is_statistically_significant),
                "sample_size": {
                    "before": len(before_times),
                    "after": len(after_times)
                }
            }

        return results