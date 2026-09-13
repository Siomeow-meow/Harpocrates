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
    return db[name]


def load_blob(collection_name: str) -> dict:
    doc = get_collection(collection_name).find_one({"_id": "config"})
    if doc is None:
        return {}
    return doc.get("data", {})


def save_blob(collection_name: str, data: dict) -> bool:
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
    _client.admin.command("ping")