import asyncio
from database import positions_collection, candidates_collection
from bson import ObjectId

async def test():
    cand = await candidates_collection.find_one({"name": {"$regex": "Ankush", "$options": "i"}})
    pos_id = cand.get("position_id")
    pos = await positions_collection.find_one({"_id": ObjectId(pos_id)})
    
    jd = pos.get("jd", {})
    print("=== JD RAW DATA ===")
    print(f"Purpose: {jd.get('purpose', 'N/A')[:300]}")
    print(f"\nEducation: {jd.get('education', 'N/A')}")
    print(f"\nExperience: {jd.get('experience', 'N/A')}")
    
    print(f"\n=== RESPONSIBILITIES ===")
    for r in jd.get("responsibilities", []):
        print(f"  - {r}")
    
    print(f"\n=== SKILLS ===")
    for s in jd.get("skills", []):
        print(f"  - {s}")

if __name__ == "__main__":
    asyncio.run(test())
