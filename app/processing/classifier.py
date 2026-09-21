import re
from typing import List, Dict, Any
from app.llm import gemini_service

AI_LLM_PATTERNS = [
    r"\b(llm|llms|large language model|gpt|claude|gemini|deepseek|llama|mistral|chatgpt|openai|anthropic|generative ai|genai|prompt|rag|transformer|attention mechanism|fine-tun|rlhf|reasoning model|diffusion model|text-to-image|sora|whisper)\b"
]

DATA_SCIENCE_ML_PATTERNS = [
    r"\b(data science|machine learning|deep learning|neural network|pytorch|tensorflow|scikit-learn|pandas|numpy|kaggle|computer vision|object detection|reinforcement learning|regression|classification|clustering|feature engineering|random forest)\b"
]

DATA_ENG_CLOUD_PATTERNS = [
    r"\b(data engineering|etl|elt|data pipeline|apache spark|kafka|snowflake|databricks|airflow|dbt|sql|postgres|vector database|cloud infrastructure|aws|azure|gcp|kubernetes|docker|mlops)\b"
]

def rule_based_classify(title: str, summary: str, hint: str = "TECH_GENERAL") -> Dict[str, Any]:
    """Fast regex-based classification with confidence score."""
    content = f"{title} {summary}".lower()

    if hint == "AI_RESEARCH":
        return {"category": "AI_RESEARCH", "confidence": 0.95, "tags": ["AI Research", "Paper"]}

    for pattern in AI_LLM_PATTERNS:
        if re.search(pattern, content):
            return {"category": "AI_LLM", "confidence": 0.9, "tags": ["AI", "Generative AI"]}

    for pattern in DATA_SCIENCE_ML_PATTERNS:
        if re.search(pattern, content):
            return {"category": "DATA_SCIENCE_ML", "confidence": 0.85, "tags": ["Data Science", "Machine Learning"]}

    for pattern in DATA_ENG_CLOUD_PATTERNS:
        if re.search(pattern, content):
            return {"category": "DATA_ENG_CLOUD", "confidence": 0.8, "tags": ["Data Engineering", "Cloud"]}

    # Default to category_hint if provided
    if hint in ["AI_LLM", "DATA_SCIENCE_ML", "DATA_ENG_CLOUD"]:
        return {"category": hint, "confidence": 0.7, "tags": [hint.replace("_", " ").title()]}

    return {"category": "TECH_GENERAL", "confidence": 0.5, "tags": ["Tech"]}

def classify_articles(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Hybrid classifier:
    1. Runs rule-based classifier first.
    2. Identifies low-confidence (<0.75) ambiguous items.
    3. Batches low-confidence items to Gemini (gemini-3.5-flash-lite) if API is active.
    """
    results = []
    ambiguous_indices = []
    ambiguous_items = []

    for i, a in enumerate(articles):
        hint = a.get("category_hint", "TECH_GENERAL")
        rule_res = rule_based_classify(a.get("title", ""), a.get("summary", ""), hint)
        results.append(rule_res)

        if rule_res["confidence"] < 0.75:
            ambiguous_indices.append(i)
            ambiguous_items.append(a)

    # If ambiguous items exist and Gemini is ready, invoke batched classifier
    if ambiguous_items and gemini_service.is_available():
        gemini_results = gemini_service.classify_articles_batch(ambiguous_items)
        for orig_idx, gemini_res in zip(ambiguous_indices, gemini_results):
            results[orig_idx] = {
                "category": gemini_res["category"],
                "confidence": 0.95,
                "tags": gemini_res.get("tags", ["AI"])
            }

    return results
