
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


def create_embedding(text, filename):
    try:
        response = requests.post(
            "http://localhost:11434/api/embeddings",
            json={
                "model": MODEL_NAME,
                "prompt": text
            },
            timeout=120
        )

        if response.status_code != 200:
            print(f"\nEmbedding failed for: {filename}")
            print(f"Status code: {response.status_code}")
            print(f"Error: {response.text}")

        response.raise_for_status()

        return response.json()["embedding"]

    except requests.exceptions.RequestException as error:
        print(f"\nError processing: {filename}")
        print(error)
        raise


def main():
    files = sorted(KNOWLEDGE_FOLDER.glob("*.txt"))

    if not files:
        print("No .txt files found in the knowledge folder.")
        return

    print(f"Found {len(files)} knowledge documents.\n")

    successful = 0
    failed = 0

    for file in files:
        try:
            content = file.read_text(encoding="utf-8")

            if not content.strip():
                print(f"Skipped empty file: {file.name}")
                continue

            embedding = create_embedding(content, file.name)

            collection.upsert(
                ids=[file.name],
                documents=[content],
                embeddings=[embedding],
                metadatas=[{"source": file.name}]
            )

            successful += 1
            print(f"Indexed: {file.name}")

        except Exception as error:
            failed += 1
            print(f"Failed: {file.name}")
            print(f"Reason: {error}\n")

    print("\n========== INGESTION SUMMARY ==========")
    print(f"Successfully indexed: {successful}")
    print(f"Failed: {failed}")
    print(f"Total documents in database: {collection.count()}")
    print("=======================================")


if __name__ == "__main__":
    main()
