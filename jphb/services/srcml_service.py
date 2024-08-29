import subprocess
import re
import os
import tempfile
import xml.etree.ElementTree as ET
from typing import Union

POS_NS = {'pos': 'http://www.srcML.org/srcML/position'}


class SrcMLService:

    """
    This module provides a service to work with srcML and extract information from Java code.

    The methods in this class are:
        - get_methods: This method returns the methods in the given code.
        - remove_comments: This method removes the comments from the given code.
    """

    def __init__(self) -> None:
        self.namespace = {'src': 'http://www.srcML.org/srcML/src'}

    def get_methods(self, code: str, with_body: bool = False, remove_comments: bool = False) -> list[str]:
        """
        This method returns the methods in the given code.
        Each method is represented as a string in the format of:
            <return type> <package name><class name>.<method name>(<parameters>)

        If with_body is True, the method will return the methods with their bodies.
            <return type> <package name><class name>.<method name>(<parameters>) { <method body> }
        """

        # Remove the comments from the code
        if remove_comments:
            code = self.remove_comments(code)

        root = self.__get_xml(code)
        methods = []

        for method in root.findall('.//src:function', self.namespace):
            method_name = self.__get_method_name(method)
            class_name = self.__get_method_class(method, root)

            try:
                m_name_only = method_name.split('(')[0]
                m_name_only = m_name_only.split(' ')[-1]
                m_name_only = m_name_only + '(' + method_name.split('(')[1]

                m_signature = method_name.split('(')[0]
                m_signature = ' '.join(m_signature.split(' ')[0:-1])

                method_declaration = ''
                if m_signature != '':
                    method_declaration = f'{m_signature} '
                if class_name != '':
                    method_declaration += f'{class_name}.'

                if with_body:
                    method_block = method.find('src:block', self.namespace)
                    if method_block is None:
                        continue
                    method_body = ''.join(method_block.itertext()).strip()
                    method_body = re.sub(' +', ' ', ''.join(method_body).strip().replace('\n', '').replace('\t', ''))
                    methods.append(f'{method_declaration}{m_name_only} {method_body}')
                else:
                    methods.append(f'{method_declaration}{m_name_only}')
            except:
                continue

        return methods

    def remove_comments(self, code: str) -> str:
        """
        In this method, we remove the comments from the given code.
        """

        root = self.__get_xml(code)

        for comment in root.findall('.//src:comment', self.namespace):
            comment.text = ''

        # Save the modified XML to a file with fixed namespace
        output_file = f'{tempfile.NamedTemporaryFile(delete=True).name}.xml'
        ET.ElementTree(root).write(output_file)

        # Convert the XML back to code
        subprocess.run(['srcml', output_file, '-o', output_file + '.java'], capture_output=True)
        with open(output_file + '.java') as f:
            code = f.read()

        os.remove(output_file)
        os.remove(output_file + '.java')

        return code

    def __get_xml(self, code: str) -> ET.Element:
        """
        This method converts the given code to an XML tree using srcML.
        """
        output_file = f'{tempfile.NamedTemporaryFile(delete=True).name}.java'
        with open(output_file, 'w') as f:
            f.write(str(code).encode('utf-8', errors='ignore').decode('utf-8'))

        subprocess.run(['srcml', output_file, '--position', '-o', output_file + '.xml'], capture_output=True)
        tree = ET.parse(output_file + '.xml')
        os.remove(output_file)
        os.remove(output_file + '.xml')
        return tree.getroot()

    def __get_method_class(self, method: Union[ET.Element, None], root: Union[ET.Element, None]) -> str:
        """
        Given a method and the root of the XML tree, this method returns the class name of the method.

        The class name is returned in the format of:
            <package name>.<class name>
        """

        if root is None or method is None:
            return ''

        for class_ in root.findall('.//src:class', self.namespace):
            class_start = int(class_.attrib[f'{{{POS_NS["pos"]}}}start'].split(':')[0])
            class_end = int(class_.attrib[f'{{{POS_NS["pos"]}}}end'].split(':')[0])

            method_start = int(method.attrib[f'{{{POS_NS["pos"]}}}start'].split(':')[0])

            if class_start < method_start < class_end:
                package_element = root.find('.//src:package', self.namespace)
                class_name_element = class_.find('src:name', self.namespace)

                package_name = ''
                class_name = ''

                if package_element is not None:
                    package_name = ''.join(package_element.itertext()).replace('package', '').replace(';','').strip()
                if class_name_element is not None:
                    class_name = ''.join(class_name_element.itertext()).strip()

                return f'{package_name}.{class_name}' if package_name else class_name

        return ''

    def __get_method_name(self, method: Union[ET.Element, None]) -> str:
        """
        Given a method, this method returns the method name.

        The method name is returned in the format of:
            <return type> <method name>(<parameters>)
        """

        if method is None:
            return ''

        method_name_element = method.find('src:name', self.namespace)
        method_name = ''
        if method_name_element is not None:
            method_name = ''.join(method_name_element.itertext()).strip()

        method_return_type_element = method.find('src:type', self.namespace)
        method_return_type = ''
        if method_return_type_element is not None:
            method_return_type = ''.join(method_return_type_element.itertext()).strip()

        method_parameters_element = method.find('src:parameter_list', self.namespace)
        method_parameters = ''
        if method_parameters_element is not None:
            method_parameters = ''.join(method_parameters_element.itertext()).replace('\n', '').strip()

        return re.sub(' +', ' ', f'{method_return_type} {method_name}{method_parameters}').strip()

    def __is_line_comment(self, line_number: int, root: ET.Element) -> bool:
        """
        This method checks if the given line number is in a comment.
        """

        for comment in root.findall('.//comment'):
            comment_start = int(comment.attrib[f'{{{POS_NS["pos"]}}}start'].split(':')[0])
            comment_end = int(comment.attrib[f'{{{POS_NS["pos"]}}}end'].split(':')[0])

            if comment_start <= line_number <= comment_end:
                return True

        return False

    def get_code_element_method_name(self, repo, line_number, commit, file_name):
        readed_file = (
            str(repo.git.show(f"{commit}:{file_name}"))
            .encode("utf-8", errors="ignore")
            .decode("utf-8")
        )

        method_name = self.get_method_name_by_start_line(readed_file, line_number)
        return method_name

        # # if code_element.startswith("package "):
        # #     code_element = code_element[8:].strip()

        # code_element = re.sub(r"\bpackage\b\s*", "", code_element)

        # file_methods = self.get_methods(readed_file)
        # for full_name in file_methods:
        #     fm_name = full_name.split("(")[0].split(" ")[-1].strip()
        #     fm_name_short = fm_name.split(".")[-1]
        #     comparable_name = full_name.replace(fm_name, fm_name_short)
        #     if comparable_name == code_element:
        #         return full_name
        #     else:
        #         print(full_name, "###", code_element, "=================", comparable_name)
        #         # exit()
        #         return code_element

    def get_method_name_by_start_line(self, code: str, line_number: int) -> str:
        """
        This method returns the method name of the method that contains the given line number.
        """

        root = self.__get_xml(code)

        for method in root.findall('.//src:function', self.namespace):
            method_start = int(method.attrib[f'{{{POS_NS["pos"]}}}start'].split(':')[0])
            method_end = int(method.attrib[f'{{{POS_NS["pos"]}}}end'].split(':')[0])

            if method_start <= line_number <= method_end:
                class_name = self.__get_method_class(method, root)
                method_name = self.__get_method_name(method)

                m_name_only = method_name.split('(')[0]
                m_name_only = m_name_only.split(' ')[-1]
                m_name_only = m_name_only + '(' + method_name.split('(')[1]

                m_signature = method_name.split('(')[0]
                m_signature = ' '.join(m_signature.split(' ')[0:-1])

                method_declaration = ''
                if m_signature != '':
                    method_declaration = f'{m_signature} '
                if class_name != '':
                    method_declaration += f'{class_name}.'

                return f'{method_declaration}{m_name_only}'

        return ''
