import subprocess
import os
from typing import Optional

JAVA_HOME_PATHS = {
    '1.8': '/usr/lib/jvm/java-8-openjdk-amd64',
    '11': '/usr/lib/jvm/java-11-openjdk-amd64',
    '17': '/usr/lib/jvm/java-17-openjdk-amd64',
    '21': '/usr/lib/jvm/java-21-openjdk-amd64'
}

MAX_NUM_RETRIES = 2

class MvnService:
    def __init__(self) -> None:
        pass

    def install(self, cwd: str,
                custom_command: Optional[list] = None,
                java_version: str = '11',
                verbose: bool = False,
                is_shell: bool = False,
                retry_with_other_java_versions: bool = False,
                timeout: int = 600) -> tuple[bool, str]:
        command = [
            'mvn',
            'clean',
            'install'
        ]

        if custom_command is not None:
            command = custom_command

        return self.__run_mvn_command(cwd, command, java_version, verbose, is_shell, retry_with_other_java_versions, timeout)

    def package(self, cwd: str,
                custom_command: Optional[list] = None,
                java_version: str = '11',
                verbose: bool = False,
                is_shell: bool = False,
                retry_with_other_java_versions: bool = False,
                timeout: int = 600) -> tuple[bool, str]:
        command = [
            'mvn',
            'clean',
            'package'
        ]

        if custom_command is not None:
            command = custom_command

        return self.__run_mvn_command(cwd, command, java_version, verbose, is_shell, retry_with_other_java_versions, timeout)
    
    def package_module(self, cwd: str,
                module: str,
                java_version: str = '11',
                verbose: bool = False,
                is_shell: bool = False,
                retry_with_other_java_versions: bool = False,
                timeout: int = 600) -> tuple[bool, str]:
        command = [
            'mvn',
            '-pl',
            module,
            '-am',
            'clean',
            'package'
        ]

        return self.__run_mvn_command(cwd, command, java_version, verbose, is_shell, retry_with_other_java_versions, timeout)

    def __run_mvn_command(self, cwd: str,
                          command: list,
                          java_version: str,
                          verbose: bool,
                          is_shell: bool,
                          retry_with_other_java_versions: bool,
                          timeout: int) -> tuple[bool, str]:
        
        COMMAND_ARGS = [
            '-DskipTests',
            '-Dmaven.javadoc.skip=true',
            '-Dcheckstyle.skip=true',
            '-Denforcer.skip=true',
            '-Dfindbugs.skip=true',
            '-Dlicense.skip=true'
        ]

        command.extend(COMMAND_ARGS)

        retries = 0
        while True:
            env = MvnService.update_java_home(java_version)

            process = subprocess.run(command, cwd=cwd, capture_output=not verbose, shell=is_shell, timeout=timeout, env=env)

            if process.returncode == 0:
                return True, java_version

            if not retry_with_other_java_versions or retries >= MAX_NUM_RETRIES:
                return False, java_version

            # Find the next higher Java version
            java_versions = sorted(JAVA_HOME_PATHS.keys())
            next_version = next((jv for jv in java_versions if jv > java_version), None)

            if next_version is None:
                return False, java_version

            java_version = next_version

            retries += 1
    
    @staticmethod
    def update_java_home(java_version: str) -> dict:
        env = os.environ.copy()
        if java_version in JAVA_HOME_PATHS:
            java_home = JAVA_HOME_PATHS[java_version]
            env['JAVA_HOME'] = java_home
            env['PATH'] = f"{java_home}/bin:" + env['PATH']

        return env