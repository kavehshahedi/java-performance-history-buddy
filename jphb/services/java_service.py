import javalang
import javalang.ast
import javalang.tree
import hashlib


class JavaService:
    def __init__(self):
        pass

    def get_ast(self, code: str) -> javalang.tree.CompilationUnit:
        return javalang.parse.parse(code)
    
    def are_similar_codes(self, first_code: str, second_code: str) -> bool:
        first_code_hashes = self.__get_method_hashes(first_code)
        second_code_hashes = self.__get_method_hashes(second_code)

        return first_code_hashes == second_code_hashes
    
    def __normalize_method_body(self, method_body):
        # Replace variable names with placeholders
        tokens = list(javalang.tokenizer.tokenize(method_body))
        normalized_tokens = []
        for token in tokens:
            if isinstance(token, javalang.tokenizer.Identifier):
                normalized_tokens.append('var')
            else:
                normalized_tokens.append(token.value)
        return ''.join(normalized_tokens)

    def __get_method_hashes(self, code: str) -> dict:
        tree = self.get_ast(code)
        method_hashes = {}
        
        for _, node in tree:
            if isinstance(node, javalang.tree.MethodDeclaration):
                method_name = node.name # type: ignore
                method_body = ''.join(map(str, node.body)) # type: ignore
                normalized_body = self.__normalize_method_body(method_body)
                method_signature = f'{method_name}{normalized_body}'
                method_hash = hashlib.md5(method_signature.encode()).hexdigest()
                method_hashes[method_name] = method_hash
        
        return method_hashes