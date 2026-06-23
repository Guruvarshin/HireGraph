from __future__ import annotations

import os

from dotenv import load_dotenv
from langgraph.checkpoint.mongodb import MongoDBSaver
from pymongo import MongoClient

load_dotenv()

_MONGODB_URI = os.getenv("MONGODB_URI", "")
_DB_NAME     = os.getenv("MONGODB_DB_NAME", "recruiting_pipeline")

_client      = MongoClient(_MONGODB_URI, serverSelectionTimeoutMS=5000)
checkpointer = MongoDBSaver(
    client=_client,
    db_name=_DB_NAME,
    checkpoint_collection_name="lg_checkpoints",
    writes_collection_name="lg_checkpoint_writes",
)
