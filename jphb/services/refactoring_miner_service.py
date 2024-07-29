import subprocess
import os
import json
import tempfile
import sys

from jphb.services.mvn_service import MvnService

class RefactoringMinerService:

    def __init__(self, project_path: str) -> None:
        self.project_path = project_path

    def mine(self, commit_hash: str) -> list[dict]:
        output_file = tempfile.NamedTemporaryFile(delete=True).name

        mvn_service = MvnService()
        env = mvn_service.update_java_home('17')
        subprocess.run(['./RefactoringMiner',
                        '-c',
                        self.project_path,
                        commit_hash,
                        '-json', output_file],
                        cwd=os.path.join(sys.path[0], 'jphb', 'resources', 'refactoring-miner', 'bin'),
                        capture_output=True,
                        env=env)
        
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
            
    def __read(self, file_path: str) -> dict:
        with open(file_path, 'r') as f:
            return json.load(f)