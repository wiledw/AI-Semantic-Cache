from __future__ import annotations

import math
import re
from typing import Iterable, Sequence


def cosine_similarity(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
    if len(vec_a) != len(vec_b):
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for a, b in zip(vec_a, vec_b):
        dot += a * b
        norm_a += a * a
        norm_b += b * b
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


# Common contractions mapping
CONTRACTIONS = {
    "i'm": "i am",
    "you're": "you are",
    "he's": "he is",
    "she's": "she is",
    "it's": "it is",
    "we're": "we are",
    "they're": "they are",
    "i've": "i have",
    "you've": "you have",
    "we've": "we have",
    "they've": "they have",
    "i'd": "i would",
    "you'd": "you would",
    "he'd": "he would",
    "she'd": "she would",
    "we'd": "we would",
    "they'd": "they would",
    "i'll": "i will",
    "you'll": "you will",
    "he'll": "he will",
    "she'll": "she will",
    "we'll": "we will",
    "they'll": "they will",
    "don't": "do not",
    "doesn't": "does not",
    "didn't": "did not",
    "won't": "will not",
    "wouldn't": "would not",
    "couldn't": "could not",
    "shouldn't": "should not",
    "can't": "cannot",
    "isn't": "is not",
    "aren't": "are not",
    "wasn't": "was not",
    "weren't": "were not",
    "haven't": "have not",
    "hasn't": "has not",
    "hadn't": "had not",
    "mustn't": "must not",
    "let's": "let us",
    "that's": "that is",
    "what's": "what is",
    "who's": "who is",
    "where's": "where is",
    "here's": "here is",
    "there's": "there is",
}

# Common synonyms/phrases that can be normalized (conservative - only very safe ones)
SYNONYMS = {
    # Common question starters - normalize to consistent form
    "how do i": "how to",
    "how can i": "how to",
    "how would i": "how to",
    "how should i": "how to",
    # Common action verbs - normalize to most common form
    "update": "change",
    "modify": "change",
    "edit": "change",
    # Common request phrases - remove to focus on core intent
    "i want to": "",
    "i need to": "",
    "i'd like to": "",
    "i would like to": "",
    # Common polite requests - remove
    "can you": "",
    "could you": "",
    "would you": "",
    # Common location phrases - normalize
    "where can i": "where",
    "where do i": "where",
    # Common help phrases - remove
    "help me": "",
}

# Common filler words/phrases to remove (very conservative - only remove when safe)
# Note: We're conservative with articles as they can sometimes affect meaning
FILLER_WORDS = {
    "please", "kindly",  # Politeness markers - safe to remove
    "really", "very", "quite", "rather",  # Intensifiers - safe to remove
}


def normalize_query(text: str, enhanced: bool = True) -> str:
    """
    Normalize query text for better cache matching.
    
    Args:
        text: Input query text
        enhanced: If True, apply enhanced preprocessing (contractions, synonyms, etc.)
    
    Returns:
        Normalized query string
    """
    if not text:
        return ""
    
    # Basic normalization
    normalized = text.lower().strip()
    
    # Remove extra whitespace
    normalized = re.sub(r'\s+', ' ', normalized)
    
    if not enhanced:
        return normalized.strip()
    
    # Enhanced preprocessing
    
    # 1. Expand contractions
    words = normalized.split()
    expanded_words = []
    for word in words:
        # Remove punctuation for contraction matching
        word_clean = re.sub(r'[^\w\']', '', word)
        if word_clean in CONTRACTIONS:
            expanded_words.extend(CONTRACTIONS[word_clean].split())
        else:
            expanded_words.append(word)
    normalized = " ".join(expanded_words)
    
    # 2. Normalize common synonyms/phrases (order matters - longer phrases first)
    # Sort by length descending to match longer phrases first
    sorted_synonyms = sorted(SYNONYMS.items(), key=lambda x: len(x[0]), reverse=True)
    for phrase, replacement in sorted_synonyms:
        # Use word boundaries to avoid partial matches
        pattern = r'\b' + re.escape(phrase) + r'\b'
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
    
    # 3. Remove common filler words (conservative - only very common ones)
    words = normalized.split()
    filtered_words = [w for w in words if w.lower() not in FILLER_WORDS]
    normalized = " ".join(filtered_words)
    
    # 4. Remove punctuation (except apostrophes which might be part of words)
    normalized = re.sub(r'[^\w\s\']', '', normalized)
    
    # 5. Final cleanup - remove extra whitespace
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    return normalized


def as_float_list(values: Iterable[float]) -> list[float]:
    return [float(v) for v in values]
