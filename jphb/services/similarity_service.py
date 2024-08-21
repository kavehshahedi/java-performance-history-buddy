from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity

import difflib

SIMILARITY_THRESHOLD = 0.90

class SimilarityService:

    """
    This module provides a service to work with similarity between texts (i.e., Java codes in our case).
    """

    def __init__(self, first_code_tokens: list[str], second_code_tokens: list[str]) -> None:
        self.first_code_tokens = first_code_tokens
        self.second_code_tokens = second_code_tokens
    
    def are_similar(self) -> bool:
        """
        This method checks if the two given Java code snippets are similar.

        We use multiple steps to check the similarity:
            1. We use the SequenceMatcher from difflib to compare the tokens of the two methods.
            2. We use the cosine similarity to compare the two methods.
            3. We use Jacard similarity to compare the two methods.
        """
        if not self.first_code_tokens or not self.second_code_tokens:
            return False
        
        if len(self.first_code_tokens) == 0 or len(self.second_code_tokens) == 0:
            return False

        difflib_similarity = self.__get_difflib_similarity()
        cosine_similarity = self.__get_cosine_similarity()
        jaccard_similarity = self.__get_jaccard_similarity()
        
        # All three methods should return a similarity greater than the threshold
        return difflib_similarity > SIMILARITY_THRESHOLD and cosine_similarity > SIMILARITY_THRESHOLD and jaccard_similarity > SIMILARITY_THRESHOLD
    
    def __get_cosine_similarity(self) -> float:
        """
        This method calculates the cosine similarity between the two given Java code snippets.
        """
        vectorizer = CountVectorizer()
        
        # Convert the token lists back into strings
        first_code_snippet = ' '.join(self.first_code_tokens)
        second_code_snippet = ' '.join(self.second_code_tokens)
        
        # Fit and transform the vectorizer on the two snippets
        X = vectorizer.fit_transform([first_code_snippet, second_code_snippet])
        
        # Calculate the cosine similarity between the frequency vectors
        similarity = cosine_similarity(X[0:1], X[1:2]) # type: ignore
        
        return similarity[0][0]
    
    def __get_jaccard_similarity(self) -> float:
        """
        This method calculates the Jaccard similarity between the two given Java code snippets.
        """
        intersection = len(list(set(self.first_code_tokens) & set(self.second_code_tokens)))
        union = len(list(set(self.first_code_tokens) | set(self.second_code_tokens)))
        return float(intersection) / union
    
    def __get_difflib_similarity(self) -> float:
        """
        This method calculates the similarity between the two given Java code snippets using difflib.
        """
        return difflib.SequenceMatcher(None, self.first_code_tokens, self.second_code_tokens).ratio()