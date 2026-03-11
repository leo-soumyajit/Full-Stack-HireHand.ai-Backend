from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_DETAILS = os.getenv("MONGO_URI", "mongodb+srv://hirehand:721154@cluster0.yeg2mwi.mongodb.net/?appName=Cluster0")

client = AsyncIOMotorClient(MONGO_DETAILS)
database = client["hirehand"]

user_collection = database.get_collection("users")
positions_collection = database.get_collection("positions")
candidates_collection = database.get_collection("candidates")

# EOS-IA Psychometric collections
psychometric_profiles_collection = database.get_collection("psychometric_profiles")
psychometric_scores_collection = database.get_collection("psychometric_scores")
psychometric_reports_collection = database.get_collection("psychometric_reports")


async def init_db():
    """Create all indexes on startup for O(1) / low-latency queries."""
    # Users
    await user_collection.create_index("email", unique=True)

    # Positions
    await positions_collection.create_index([("user_id", 1), ("updated_at", -1)])
    await positions_collection.create_index([("user_id", 1), ("status", 1), ("updated_at", -1)])

    # Candidates
    await candidates_collection.create_index([("position_id", 1), ("user_id", 1)])
    await candidates_collection.create_index([("position_id", 1), ("added_date", -1)])

    # EOS-IA Psychometric — unique per position/candidate
    await psychometric_profiles_collection.create_index(
        [("position_id", 1), ("user_id", 1)], unique=True
    )
    await psychometric_scores_collection.create_index(
        [("candidate_id", 1), ("user_id", 1)], unique=True
    )
    await psychometric_reports_collection.create_index(
        [("candidate_id", 1), ("user_id", 1)], unique=True
    )
