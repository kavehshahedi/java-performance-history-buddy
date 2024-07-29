import javalang
import javalang.ast
import javalang.tree
import hashlib

from jphb.services.srcml_service import SrcMLService


class JavaService:

    """
    This module provides a service to work with Java code and extract information from it.

    The methods in this class are:
        - get_different_methods: This method gets two Java code snippets and returns the methods that are different between them.
        - convert_method_signature: Given a full method signature, this method converts it to a short method signature.
        - get_method_hashes: Here, we get the method hashes for the given Java code
    """

    def __init__(self) -> None:
        pass

    def __get_ast(self, code: str) -> javalang.tree.CompilationUnit:
        """
        We use the javalang library to parse the Java code and get the AST.
        """

        return javalang.parse.parse(code)
    
    def get_different_methods(self, first_code: str, second_code: str) -> list[str]:
        """
        This method gets two Java code snippets and returns the methods that are different between them.
        """

        first_code_hashes = self.get_method_hashes(first_code) # i.e., the new commit's code
        second_code_hashes = self.get_method_hashes(second_code) # i.e., the old commit's code

        different_methods = []
        for method_name, _ in first_code_hashes.items():
            if method_name not in second_code_hashes:
                # This means that the method is newly introduced in the new commit (either renamed, moved, or added)
                different_methods.append({'first': method_name, 'second': None})
            elif first_code_hashes[method_name] != second_code_hashes[method_name]:
                # This means that the method has been changed
                different_methods.append({'first': method_name, 'second': method_name})

        return different_methods
    
    def convert_method_signature(self, code: str) -> str:
        """
        Given a full method signature, this method converts it to a short method signature.

        For example:
            - Input: 'public void com.example.A.method(int, int)'
            - Output: 'None-None-method-[int, int]'
        """

        full_method_name = code.split('(')[0].split(' ')[-1]
        short_method_name = full_method_name.split('.')[-1]
        code = code.replace(full_method_name, short_method_name)
        wrapped_code = f'public class A {{ {code} {{}} }}'
        tree = self.__get_ast(wrapped_code)
        
        method_signature = ''
        for _, node in tree:
            if isinstance(node, javalang.tree.MethodDeclaration):
                method_signature = f'{node.type_parameters}-{node.return_type}-{node.name}-{node.parameters}' # type: ignore
                break
            
        return method_signature
    
    def get_method_hashes(self, code: str) -> dict:
        """
        Here, we get the method hashes for the given Java code.
        The method hashes are calculated based on the method's signature and body.

        For example:
            - Input: 'public void method(int a, int b) { return a + b; }'
            - Output: {'None-void-method-[int, int]': 'd41d8cd98f00b204e9800998ecf8427e'}
        """

        # Remove the comments
        srcml_service = SrcMLService()
        code = srcml_service.remove_comments(code)
        
        tree = self.__get_ast(code)
        method_hashes = {}
        
        for _, node in tree:
            if isinstance(node, javalang.tree.MethodDeclaration):
                method_name = f'{node.type_parameters}-{node.return_type}-{node.name}-{node.parameters}' # type: ignore
                method_body = ''.join(map(str, node.body)) if node.body else '' # type: ignore
                method_signature = f'{method_name}{method_body}'
                method_hash = hashlib.md5(method_signature.encode()).hexdigest()
                method_hashes[method_name] = method_hash
        
        return method_hashes