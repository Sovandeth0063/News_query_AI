import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.rag.generator import answer_user_query

if __name__ == "__main__":
    question = "What are the latest breakthroughs and developments in generative AI and models?"
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])

    print("==================================================")
    print(f"Testing RAG Query: '{question}'")
    print("==================================================")
    result = answer_user_query(question)

    print(f"\nModel Used: {result.get('model_used')}\n")
    print("Answer:")
    print("--------------------------------------------------")
    print(result.get("answer"))
    print("--------------------------------------------------")
    print(f"\nSources ({len(result.get('sources', []))}):")
    for s in result.get("sources", []):
        print(f"[{s.get('index')}] {s.get('title')} ({s.get('source')})")
        print(f"    URL: {s.get('url')}")
