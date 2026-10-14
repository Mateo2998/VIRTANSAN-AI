
from pathlib import Path

import chromadb
import requests

KNOWLEDGE_FOLDER = Path("knowledge")
DATABASE_FOLDER = "./chroma_data"
MODEL_NAME = "nomic-embed-text"

client = chromadb.PersistentClient(path=DATABASE_FOLDER)

collection = client.get_or_create_collection(
    name="it_knowledge"
)


def create_embedding(text):
    response = requests.post(
        "http://localhost:11434/api/embeddings",
        json={
            "model": MODEL_NAME,
            "prompt": text
        },
        timeout=120
    )

    response.raise_for_status()
    return response.json()["embedding"]


def main():
    files = list(KNOWLEDGE_FOLDER.glob("*.txt"))

    if not files:
        print("No .txt files found in the knowledge folder.")
        return

    for file in files:
        content = file.read_text(encoding="utf-8")

        collection.upsert(
            ids=[file.name],
            documents=[content],
            embeddings=[create_embedding(content)],
            metadatas=[{"source": file.name}]
        )

        print(f"Indexed: {file.name}")

    print(f"Total documents indexed: {collection.count()}")


if __name__ == "__main__":
    main()
