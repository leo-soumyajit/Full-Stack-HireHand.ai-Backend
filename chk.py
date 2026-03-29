import asyncio
from database import psychometric_reports_collection

async def chk():
    d = await psychometric_reports_collection.find_one({"candidate_id": "69c7ff4b41b78b436d7cf738"})
    print("Keys:")
    for k in sorted(d.keys()):
        print("  ", k)
        
    print("Pattern Cluster:")
    print(d.get("pattern_cluster"))

if __name__ == '__main__':
    asyncio.run(chk())
