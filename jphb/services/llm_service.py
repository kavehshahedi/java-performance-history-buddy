from openai import OpenAI
import dotenv
import os

dotenv.load_dotenv()

SYSTEM_PROMPT = """
Given two versions of a function, determine if the code change is significant or not.
The code change is significant if it changes the behavior of the code, introduces a new feature, or alters the performance.
Just reply with 'YES' or 'NO' with no more explanation.
"""


class LLMService:
    """
    This module aims to determine the significance of code changes using the Language Model.
    We use OpenAI's API to interact with the model.

    We want to use LLM as a helper to determine if the code changes between two versions of a method is significant or not.
    """


    def __init__(self, model_name: str = os.getenv('LLM_MODEL_NAME', 'gpt-4o-mini'),
                    api_key: str = os.getenv('OPENAI_API_KEY', 'INVALID_OPENAI_API_KEY')) -> None:
        self.client = OpenAI(api_key=api_key)
        self.model_name = model_name

    def is_code_change_significant(self, code_version_1: str, code_version_2: str, wrap_codes: bool = False) -> bool:
        # If wrap_codes is True, we wrap the code versions in a class block
        if wrap_codes:
            code_version_1 = f'class A {{\n{code_version_1}\n}}'
            code_version_2 = f'class A {{\n{code_version_2}\n}}'

        # Send the code versions to the model to determine the significance
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": code_version_1
                },
                {
                    "role": "user",
                    "content": code_version_2
                }
            ]
        )

        try:
            result = response.choices[0].message.content

            # If the result is None or not 'YES' or 'NO', we return True since we can't determine the significance
            if result is None or result not in ['YES', 'NO']:
                return True
            
            # If the result is 'YES', we return True, otherwise False
            return result == 'YES'
        except:
            # If there is an error, we return True
            return True