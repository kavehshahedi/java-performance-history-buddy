import subprocess
import os
from typing import Optional

JAVA_HOME_PATHS = {
    '1.8': '/usr/lib/jvm/java-8-openjdk-amd64',
    '11': '/usr/lib/jvm/java-11-openjdk-amd64',
    '17': '/usr/lib/jvm/java-17-openjdk-amd64',
    '21': '/usr/lib/jvm/java-21-openjdk-amd64'
}
from jphb.utils.file_utils import FileUtils

# JAVA_HOME_PATHS = {
#     "1.8": "/Library/Java/JavaVirtualMachines/adoptopenjdk-8.jdk/Contents/Home",
#     "11": "/opt/homebrew/Cellar/openjdk@11/11.0.24/libexec/openjdk.jdk/Contents/Home",
#     "17": "/opt/homebrew/Cellar/openjdk@17/17.0.12/libexec/openjdk.jdk/Contents/Home",
#     "21": "/Library/Java/JavaVirtualMachines/jdk-21.jdk/Contents/Home",
# }

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

        return self.__run_mvn_command(cwd, command, java_version, verbose, is_shell, retry_with_other_java_versions, timeout, False)

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

        return self.__run_mvn_command(cwd, command, java_version, verbose, is_shell, retry_with_other_java_versions, timeout, True)

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

        return self.__run_mvn_command(cwd, command, java_version, verbose, is_shell, retry_with_other_java_versions, timeout, False)

    def __run_mvn_command(self, cwd: str,
                          command: list,
                          java_version: str,
                          verbose: bool,
                          is_shell: bool,
                          retry_with_other_java_versions: bool,
                          timeout: int,
                          parent_mvn_wrapper: bool) -> tuple[bool, str]:

        COMMAND_ARGS = [
            '-q',
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
            print("Building using: ", java_version, env["JAVA_HOME"])

            # Try with regular maven command
            process = subprocess.run(command, cwd=cwd, capture_output=not verbose, shell=is_shell, timeout=timeout, env=env)

            if process.returncode == 0:
                return True, java_version

            # If regular maven fails, try with mvnw
            mvnw_path = os.path.join(cwd, '../mvnw') if parent_mvn_wrapper else os.path.join(cwd, 'mvnw')
            if os.path.isfile(mvnw_path):
                # If regular maven fails, try with mvnw
                mvnw_command = ['../mvnw'] if parent_mvn_wrapper else ['./mvnw']
                mvnw_command += command[1:]  # Add the rest of the command arguments

                try:
                    process = subprocess.run(mvnw_command, cwd=cwd, capture_output=not verbose, shell=is_shell, timeout=timeout, env=env)
                    if process.returncode == 0:
                        return True, java_version
                except:
                    pass

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
    def clean_mvn_cache(cwd:str, directory: str) -> None:
        subprocess.run(['mvn', 'dependency:purge-local-repository', '-DreResolve=false'], cwd=cwd, capture_output=True)
        if FileUtils.is_path_exists(directory):
            subprocess.run(['rm', '-rf', directory], cwd=cwd, capture_output=True)

    @staticmethod
    def remove_security_from_jar(jar_path: str) -> None:
        subprocess.run(['zip', '-d', jar_path, 'META-INF/*.SF', 'META-INF/*.DSA', 'META-INF/*.RSA'], capture_output=True)

    @staticmethod
    def update_java_home(java_version: str) -> dict:
        env = os.environ.copy()

        # Check if java version is a float
        try:
            float(java_version)
        except:
            return env
        
        # Convert version strings to floats for comparison
        requested_version = float(java_version.replace('1.', ''))
        available_versions = [float(v.replace('1.', '')) for v in JAVA_HOME_PATHS.keys()]
        
        # Find the closest available version that is >= requested version
        selected_version = min((v for v in available_versions if v >= requested_version), default=None)
        
        if selected_version:
            # Convert back to string format
            selected_version_str = f'1.{selected_version}' if selected_version < 9 else str(int(selected_version))
            java_home = JAVA_HOME_PATHS[selected_version_str]
            env['JAVA_HOME'] = java_home
            env['PATH'] = f"{java_home}/bin:" + env['PATH']
                
        return env
