import os
import hashlib
import json
from typing import Union

class FileUtils:
    @staticmethod
    def get_file_hash(file_path: str) -> str:
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    
    @staticmethod
    def get_folder_hash(folder_path: str) -> str:
        md5_list = []
    
        for root, dirs, files in os.walk(folder_path):
            for filename in sorted(files):
                file_path = os.path.join(root, filename)
                file_md5 = FileUtils.get_file_hash(file_path)
                relative_path = os.path.relpath(file_path, folder_path)
                md5_list.append((relative_path, file_md5))
        
        md5_list.sort()
        
        combined_md5_string = ''.join(f'{path}:{md5}' for path, md5 in md5_list)
        final_md5 = hashlib.md5(combined_md5_string.encode('utf-8')).hexdigest()
        
        return final_md5
    
    @staticmethod
    def is_path_exists(path: str) -> bool:
        return os.path.exists(path)
    
    @staticmethod
    def remove_path(path: str):
        if os.path.isdir(path):
            os.rmdir(path)
        else:
            os.remove(path)

    @staticmethod
    def create_directory(directory_path: str):
        if not FileUtils.is_path_exists(directory_path):
            os.makedirs(directory_path, exist_ok=True)
    
    @staticmethod
    def read_json_file(file_path: str, create_if_not_exists: bool = True) -> dict:
        if not FileUtils.is_path_exists(file_path):
            if create_if_not_exists:
                with open(file_path, 'w') as f:
                    json.dump({}, f)
            else:
                return {}

        with open(file_path, 'r') as f:
            file = json.load(f)

        return file
    
    @staticmethod
    def write_json_file(file_path: str, data: Union[dict, list]):
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=4)