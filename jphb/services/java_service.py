from typing import Union
import subprocess
import os
import sys
import json

from jphb.services.similarity_service import SimilarityService

from concurrent.futures import ThreadPoolExecutor

class JavaService:

    """
    This module provides a service to work with Java code and extract information from it.

    The methods in this class are:
        - get_different_methods: This method gets two Java code snippets and returns the methods that are different between them.
        - convert_method_signature: Given a full method signature, this method converts it to a short method signature.
        - get_method_hashes: Here, we get the method hashes for the given Java code
    """

    def __init__(self) -> None:
        self.jpb_path = os.path.join(sys.path[0], 'jphb', 'resources', 'jpb.jar')
        self.executor = ThreadPoolExecutor(max_workers=8)
    
    def get_different_methods(self, first_code_path: str, second_code_path: str) -> Union[list[dict], None]:
        """
        This method gets two Java code snippets and returns the methods that are different between them.
        """

        first_output = self.__execute_get_method_hashes(first_code_path)
        second_output = self.__execute_get_method_hashes(second_code_path)

        if not first_output or not second_output:
            return None
        
        first_methods = json.loads(first_output)
        second_methods = json.loads(second_output)

        different_methods = []
        for method_ in first_methods:
            method_signature = method_['signature']
            method_hash = method_['hash']
            method_tokens = method_['tokens']

            # Check if method_name exists in second_methods
            second_method = next((method for method in second_methods if method['signature'] == method_signature), None)
            if not second_method:
                for smethod in second_methods:
                    smethod_tokens = smethod['tokens']
                    
                    similarity_service = SimilarityService(method_tokens, smethod_tokens)
                    if similarity_service.are_similar():
                        second_method = smethod
                        break

            # If again, we couldn't find the second method by comparing the tokens, we add it as null to the different_methods
            if not second_method:
                different_methods.append({
                    'first': method_signature,
                    'second': None,
                })
                continue
            
            # Check if method_hash is different
            if second_method['hash'] != method_hash:
                different_methods.append({
                    'first': method_signature,
                    'second': second_method['signature'],
                })

        return different_methods
    
    def convert_method_signature(self, method_signature: str) -> Union[str, None]:
        """
        Given a full method signature, this method converts it to a short method signature.

        For example:
            - Input: 'public void com.example.A.method(int a, int b)'
            - Output: 'None-None-method-[int a, int b]'
        """
        
        return self.executor.submit(self.__execute_convert_method_signature, method_signature).result()
    
    def __execute_get_method_hashes(self, code_path: str):
        output = subprocess.check_output(['java', '-jar', self.jpb_path, '-get-methods-hash', code_path])
        return output.decode('utf-8').strip() or None
    
    def __execute_convert_method_signature(self, method_signature: str):
        output = subprocess.check_output(['java', '-jar', self.jpb_path, '-convert-method-signature', method_signature])
        return output.decode('utf-8').strip() or None
    
    