import asyncio
from database import candidates_collection, interview_analyses_collection

async def test():
    cand = await candidates_collection.find_one({"name": {"$regex": "Ankush", "$options": "i"}})
    print(f"Cand: {cand['name']}")
    analysis = await interview_analyses_collection.find_one({"candidate_id": str(cand["_id"])})
    for msg in analysis.get("transcript", []):
        if isinstance(msg, dict):
            print(f"[{msg.get('speaker')}]: {msg.get('text')}")
        else:
            print(str(msg))

if __name__ == "__main__":
    asyncio.run(test())
