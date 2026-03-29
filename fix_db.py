import asyncio
from database import psychometric_reports_collection

async def fix():
    docs = await psychometric_reports_collection.find().to_list(length=100)
    fixed = 0
    for d in docs:
        uid = d.get('user_id')
        if uid and type(uid) is not str:
            print(f"Fixing doc {d['_id']} user_id to string '{str(uid)}'")
            await psychometric_reports_collection.update_one({'_id': d['_id']}, {'$set': {'user_id': str(uid)}})
            fixed += 1
    print(f"Fixed {fixed} documents!")

if __name__ == "__main__":
    asyncio.run(fix())
