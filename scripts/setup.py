#!/usr/bin/env python3
import os
import sys
from dotenv import load_dotenv

load_dotenv()

def check_env_vars():
    required = [
        "OPENAI_API_KEY",
        "MONGODB_URI",
        "MONGODB_DB_NAME",
        "PINECONE_API_KEY",
        "PINECONE_INDEX_NAME",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "GMAIL_ADDRESS",
        "BREVO_API_KEY",
        "TAVILY_API_KEY",
    ]
    missing = [var for var in required if not os.getenv(var)]
    if missing:
        print(f"ERROR: Missing env vars: {', '.join(missing)}")
        return False
    print("✓ All required environment variables present")
    return True

def check_mongodb():
    try:
        from pymongo import MongoClient
        uri = os.getenv("MONGODB_URI")
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.server_info()
        print("✓ MongoDB connection successful")
        return True
    except Exception as e:
        print(f"ERROR: MongoDB connection failed: {e}")
        return False

def check_pinecone():
    try:
        from pinecone import Pinecone
        pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        indexes = pc.list_indexes()
        print(f"✓ Pinecone connected ({len(indexes.indexes)} indexes found)")
        return True
    except Exception as e:
        print(f"ERROR: Pinecone connection failed: {e}")
        return False

def check_openai():
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        client.models.list()
        print("✓ OpenAI connection successful")
        return True
    except Exception as e:
        print(f"ERROR: OpenAI connection failed: {e}")
        return False

def create_mongodb_indexes():
    try:
        from pymongo import MongoClient
        uri = os.getenv("MONGODB_URI")
        db_name = os.getenv("MONGODB_DB_NAME", "recruiting_pipeline")
        client = MongoClient(uri)
        db = client[db_name]

        db.pipeline_runs.create_index([("thread_id", 1)], unique=True)
        db.pipeline_runs.create_index([("user_id", 1)])
        db.pipeline_runs.create_index([("created_at", -1)])
        db.google_tokens.create_index([("user_id", 1)], unique=True)
        db.recruiters.create_index([("email", 1)], unique=True)
        db.lg_checkpoints.create_index([("thread_id", 1)])

        print("✓ MongoDB indexes created")
        return True
    except Exception as e:
        print(f"ERROR: Failed to create indexes: {e}")
        return False

def main():
    print("=== HireGraph Setup ===\n")

    checks = [
        ("Environment variables", check_env_vars),
        ("MongoDB", check_mongodb),
        ("Pinecone", check_pinecone),
        ("OpenAI", check_openai),
        ("MongoDB indexes", create_mongodb_indexes),
    ]

    results = []
    for name, check in checks:
        print(f"\nChecking {name}...")
        result = check()
        results.append(result)

    print("\n" + "="*40)
    if all(results):
        print("✓ All checks passed! Ready to run.")
        return 0
    else:
        print("✗ Some checks failed. Fix errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
