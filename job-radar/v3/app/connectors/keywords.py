"""Shared AI/ML keyword filter for job connectors.

Centralized to prevent drift across connectors. Uses proper word boundaries.
"""
import re

# Core AI/ML keywords — must match at word boundaries
AI_KEYWORDS = re.compile(
    r'\b(?:'
    r'AI|ML|machine learning|deep learning|NLP|LLM|GPT|computer vision|'
    r'data scientist|data science|data engineering|'
    r'pytorch|tensorflow|mlops|GenAI|langchain|embeddings|'
    r'RAG|fine[- ]tun(?:e|ing|ed)|hugging\s?face|openai|anthropic'
    r')\b', re.IGNORECASE
)
