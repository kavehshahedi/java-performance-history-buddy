import subprocess
import os
import json
import tempfile
import sys
from collections import defaultdict
import re

from jphb.services.srcml_service import SrcMLService
from jphb.services.mvn_service import MvnService

class RefactoringMinerService:

    def __init__(self, project_path: str) -> None:
        self.project_path = project_path

    def mine(self, commit_hash: str) -> list[dict]:
        output_file = tempfile.NamedTemporaryFile(delete=True).name

        try:
            mvn_service = MvnService()
            env = mvn_service.update_java_home('17')
            subprocess.run(['./RefactoringMiner',
                            '-c',
                            self.project_path,
                            commit_hash,
                            '-json', output_file],
                            cwd=os.path.join(sys.path[0], 'jphb', 'resources', 'refactoring-miner', 'bin'),
                            capture_output=True,
                            env=env,
                            timeout=60)
        except subprocess.TimeoutExpired:
            return []

        result = self.__read(output_file)
        for commit in result['commits']:
            if commit['sha1'] == commit_hash:
                return commit['refactorings']

        return []

    def get_refactorings_for_file(self, refactorings: list[dict], file_path: str) -> list[dict]:
        file_refactorings = []
        for refactoring in refactorings:
            if refactoring['leftSideLocations']:
                for location in refactoring['leftSideLocations']:
                    if location['filePath'] == file_path:
                        file_refactorings.append(refactoring)

            if refactoring['rightSideLocations']:
                for location in refactoring['rightSideLocations']:
                    if location['filePath'] == file_path:
                        file_refactorings.append(refactoring)

        return file_refactorings

    def get_refactorings_for_line(self, refactorings: list[dict], line_number: int) -> list[dict]:
        line_refactorings = []
        for refactoring in refactorings:
            if refactoring['rightSideLocations']:
                for location in refactoring['rightSideLocations']:
                    if location['startLine'] <= line_number <= location['endLine']:
                        line_refactorings.append(refactoring)

        return line_refactorings

    def is_file_replaced(self, file_refactorings: list[dict], file_path: str) -> tuple[bool, str]:
        for refactoring in file_refactorings:
            r_type = refactoring['type']
            if r_type in ['Move Class', 'Rename Class', 'Move And Rename Class']:
                return True, refactoring['rightSideLocations'][0]['filePath']

        return False, ''

    def remove_insignificant_refactorings(self, refactorings: list[dict]) -> list[dict]:
        return [refactoring for refactoring in refactorings if refactoring['type'] not in ['Rename Method',
                                                                                           'Rename Class',
                                                                                           'Rename Variable',
                                                                                           'Rename Parameter',
                                                                                           'Rename Attribute',
                                                                                           'Rename Package']]

    def __extract_method_changes(self, refactorings: list[dict]) -> dict:
        method_changes = {}
        for refactoring in refactorings:
            if refactoring['type'] in ['Rename Method',
                                       'Inline Method',
                                       'Move Method',
                                       'Move And Rename Method']:
                method_changes[refactoring['methodBefore']] = refactoring['methodAfter']

        return method_changes

    def get_candidate_refactorings(self, refactorings: list[dict]) -> list[dict]:
        acceptable_refactoring_types = ["Extract Method", "Extract Class", "Inline Method", "Move Method"]
        candidate_refactorings = []
        for refactoring in refactorings:
            refactoring_type = refactoring.get("type")
            if refactoring_type and (refactoring_type in acceptable_refactoring_types):
                candidate_refactorings.append(refactoring)

        return candidate_refactorings  

    def restructure_refactorings(self, repo, refactorings, current_commit, previous_commit):
        srcml = SrcMLService()
        restructured = defaultdict(lambda: defaultdict(list))
        metadata = defaultdict(list)

        for refactoring in refactorings:
            refactoring_type = refactoring.get("type")
            method_changes = {
                "before": {"method_sig": [], "file": ""},
                "after": {"method_sig": [], "file": ""}
            }

            # Process right side locations
            for location in refactoring.get("rightSideLocations", []):
                if location["codeElementType"] == "METHOD_DECLARATION":
                    file_path = location.get("filePath")
                    if "/test" in file_path:  # ignore all test files
                        continue
                    start_line = location.get("startLine")
                    end_line = location.get("endLine")
                    if file_path and start_line:
                        code_element = srcml.get_code_element_method_name(repo, start_line, current_commit, file_path)
                        # print(current_commit, file_path, start_line, end_line)
                        if code_element:
                            restructured[current_commit][file_path].append(code_element)
                            method_changes["after"]["method_sig"].append(code_element)
                            method_changes["after"]["file"] = file_path

            # Process left side locations
            for location in refactoring.get('leftSideLocations', []):
                if location["codeElementType"] == "METHOD_DECLARATION":
                    file_path = location.get('filePath')
                    if "/test" in file_path: # ignore all test files
                        continue
                    start_line = location.get('startLine')
                    if file_path and start_line:
                        code_element = srcml.get_code_element_method_name(repo, start_line, previous_commit, file_path)
                        if code_element:
                            restructured[previous_commit][file_path].append(code_element)
                            method_changes["before"]["method_sig"].append(code_element)
                            method_changes["before"]["file"] = file_path

            # Add to metadata
            metadata["refactorings"].append({
                "method_changes": method_changes,
                "refactoring_type": refactoring_type
            })

        # Convert defaultdict to regular dict for the final output
        restructured_dict = {k: dict(v) for k, v in restructured.items()}

        return restructured_dict, metadata

    def __structure_code_element(self, code_element: str) -> str:
        element_return_type = code_element.split(":")[-1].strip()
        code_element = code_element.split(":")[0].strip()
        method_name = code_element.split(" ")[-1].strip()
        code_element = code_element.replace(method_name, "")
        code_element = code_element + element_return_type + " " + method_name
        return code_element

    def transform_string(self, file_path, original_string):
        # Extract the package name from the file path
        package_name = (
            os.path.dirname(file_path)
            .replace("/", ".")
            .replace("\\", ".")
            .replace("src.main.java.", "")
        )

        # Extract the class name from the file path
        class_name = os.path.basename(file_path).split(".")[0]

        # Use regex to parse the original string
        pattern = r"(package\s+)?([\w<>[\]]+\s+)?([\w]+)\s*\((.*?)\)(\s*:\s*([\w<>[\]]+))?"
        match = re.match(pattern, original_string)

        if not match:
            return "Invalid input string format"

        is_package = bool(match.group(1))
        return_type = match.group(2) or match.group(6) or ""
        method_name = match.group(3)
        parameters = match.group(4)

        # Remove any leading/trailing whitespace
        return_type = return_type.strip()
        method_name = method_name.strip()
        parameters = parameters.strip()

        # Construct the new string
        if is_package:
            transformed_string = f"{return_type} {package_name}.{class_name}.{method_name}({parameters})"
        else:
            transformed_string = (
                f"{return_type} {package_name}.{class_name}.{method_name}({parameters})"
            )

        # Remove any double spaces that might have been introduced
        transformed_string = re.sub(r"\s+", " ", transformed_string).strip()

        return transformed_string

    def __read(self, file_path: str) -> dict:
        with open(file_path, 'r') as f:
            return json.load(f) 
