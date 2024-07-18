import subprocess
import os
from typing import Optional

JAVA_HOME_PATHS = {
    '1.8': '/usr/lib/jvm/java-8-openjdk-amd64',
    '11': '/usr/lib/jvm/java-11-openjdk-amd64',
    '17': '/usr/lib/jvm/java-17-openjdk-amd64'
}

class MvnService:
    def __init__(self) -> None:
        pass

    def install(self, cwd: str, custom_command: Optional[list] = None, java_version: str = '11', verbose: bool = False, is_shell: bool = False, timeout: int = 600) -> bool:
        command = [
            'mvn',
            'clean',
            'install',
            '-DskipTests',
            '-Dmaven.javadoc.skip=true',
            '-Dcheckstyle.skip=true',
            '-Denforcer.skip=true',
            '-Dfindbugs.skip=true',
            '-Dlicense.skip=true'
        ]

        if custom_command is not None:
            command = custom_command

        return self.__run_mvn_command(cwd, command, java_version, verbose, is_shell, timeout)

    def package(self, cwd: str, custom_command: Optional[list] = None, java_version: str = '11', verbose: bool = False, is_shell: bool = False, timeout: int = 600) -> bool:
        command = [
            'mvn',
            'clean',
            'package',
            '-DskipTests',
            '-Dmaven.javadoc.skip=true',
            '-Dcheckstyle.skip=true',
            '-Denforcer.skip=true',
            '-Dfindbugs.skip=true',
            '-Dlicense.skip=true'
        ]

        if custom_command is not None:
            command = custom_command

        return self.__run_mvn_command(cwd, command, java_version, verbose, is_shell, timeout)
    
    def __run_mvn_command(self, cwd: str, command: list, java_version: str, verbose: bool, is_shell: bool, timeout: int) -> bool:
        env = self.__update_java_home(java_version)

        process = subprocess.run(command, cwd=cwd, capture_output=not verbose, shell=is_shell, timeout=timeout, env=env)
        return process.returncode == 0
    
    def __update_java_home(self, java_version: str) -> dict:
        env = os.environ.copy()
        if java_version in JAVA_HOME_PATHS:
            java_home = JAVA_HOME_PATHS[java_version]
            env['JAVA_HOME'] = java_home
            env['PATH'] = f"{java_home}/bin:" + env['PATH']

        return env