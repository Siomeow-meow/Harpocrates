# db.py
"""
Shared MongoDB connection for the whole bot.

All cogs that used to read/write JSON files under data/*.json now read/write
a single document in their own MongoDB collection instead. Each collection
stores one document with _id="config" whose "data" field holds exactly the
same dict structure that used to be dumped to the JSON file. This keeps the
change to each cog small: load -> fetch that document's "data" field (or {}),
save -> upsert it back.

Requires MONGO_PASSWORD (and optionally MONGO_URI) to be set in apikeys.env
or as real environment variables.
"""

import sys
import os
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from dotenv import load_dotenv

load_dotenv("apikeys.env")

_uri = os.environ.get("MONGO_URI")
_password = os.environ.get("MONGO_PASSWORD")

if not _uri:
    print("❌ MONGO_URI is not set. Add it to apikeys.py or the environment.")
    sys.exit(1)

if "<db_password>" in _uri:
    if not _password:
        print("❌ MONGO_PASSWORD is not set (apikeys.py or environment), "
            "but MONGO_URI still contains the <db_password> placeholder.")
        sys.exit(1)
    _uri = _uri.replace("<db_password>", _password)

_client = MongoClient(_uri, server_api=ServerApi('1'))


DB_NAME = "HarpocratesDB"
db = _client[DB_NAME]


def get_collection(name: str):
    """Return the MongoDB collection backing a given cog's data."""
    return db[name]


def load_blob(collection_name: str) -> dict:
    """Load the single config document for a collection. Returns {} if missing."""
    doc = get_collection(collection_name).find_one({"_id": "config"})
    if doc is None:
        return {}
    return doc.get("data", {})


def save_blob(collection_name: str, data: dict) -> bool:
    """Upsert the single config document for a collection."""
    try:
        get_collection(collection_name).update_one(
            {"_id": "config"},
            {"$set": {"data": data}},
            upsert=True,
        )
        return True
    except Exception as e:
        print(f"❌ MongoDB save failed for '{collection_name}': {e}")
        return False


def ping():
    """Quick connectivity check, call once at startup."""
    _client.admin.command("ping")
