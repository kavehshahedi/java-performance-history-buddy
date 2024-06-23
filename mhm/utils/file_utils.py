import os
import hashlib

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