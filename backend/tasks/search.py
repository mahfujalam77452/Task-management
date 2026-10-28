import os
import re
from difflib import SequenceMatcher

from django.conf import settings

from .models import Task

try:
    import chromadb
except ImportError:  # pragma: no cover - optional in lightweight local installs
    chromadb = None


STOP_WORDS = {
    "a", "an", "and", "are", "about", "all", "find", "for", "me", "of",
    "do", "for", "i", "in", "need", "of", "only", "related", "show", "task", "tasks",
    "has", "that", "the", "to", "today", "tomorrow", "what", "which",
}


def normalize_query(query):
    words = [word for word in re.findall(r"[a-z0-9]+", query.lower()) if word not in STOP_WORDS and len(word) > 2]
    return " ".join(words)


def _fallback_score(query, task):
    query_words = set(normalize_query(query).split())
    text_words = set(re.findall(r"[a-z0-9]+", f"{task.title} {task.description}".lower()))
    overlap = len(query_words & text_words) / max(len(query_words), 1)
    phrase = SequenceMatcher(None, normalize_query(query), f"{task.title} {task.description}".lower()).ratio()
    return overlap * 0.75 + phrase * 0.25


def semantic_tasks(query, tasks):
    tasks = list(tasks)
    if not query or not tasks:
        return tasks
    normalized_query = normalize_query(query)
    if not normalized_query:
        return tasks
    lexical_matches = [
        task for task in tasks
        if any(word in re.findall(r"[a-z0-9]+", f"{task.title} {task.description}".lower())
               for word in normalized_query.split())
    ]
    key = os.getenv("GEMINI_API_KEY")
    if chromadb and key:
        try:
            path = os.getenv("CHROMA_PATH") or None
            client = chromadb.PersistentClient(path=path) if path else chromadb.Client()
            collection = client.get_or_create_collection("taskflow_tasks", metadata={"hnsw:space": "cosine"})
            from google import genai
            ai = genai.Client(api_key=key)
            texts = [f"{task.title}\n{task.description}" for task in tasks]
            embeddings = ai.models.embed_content(
                model=os.getenv("GEMINI_EMBEDDING_MODEL", "text-embedding-004"),
                contents=texts,
            ).embeddings
            collection.upsert(
                ids=[str(task.id) for task in tasks],
                documents=texts,
                embeddings=[embedding.values for embedding in embeddings],
                metadatas=[{"task_id": str(task.id)} for task in tasks],
            )
            query_embedding = ai.models.embed_content(
                model=os.getenv("GEMINI_EMBEDDING_MODEL", "text-embedding-004"),
                contents=[normalized_query],
            ).embeddings[0].values
            result = collection.query(
                query_embeddings=[query_embedding],
                n_results=len(tasks),
                include=["distances", "metadatas"],
            )
            threshold = float(os.getenv("SEARCH_MAX_DISTANCE", "0.65"))
            ids = [
                metadata["task_id"]
                for metadata, distance in zip(result["metadatas"][0], result["distances"][0])
                if distance <= threshold
            ]
            by_id = {str(task.id): task for task in tasks}
            semantic_matches = [by_id[task_id] for task_id in ids if task_id in by_id]
            return list(dict.fromkeys(lexical_matches + semantic_matches))
        except Exception:
            pass
    ranked = sorted(((task, _fallback_score(query, task)) for task in tasks), key=lambda item: item[1], reverse=True)
    return list(dict.fromkeys(lexical_matches + [task for task, score in ranked if score >= 0.25]))
