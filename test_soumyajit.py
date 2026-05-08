import asyncio
import sys
sys.path.insert(0, ".")

from database import candidates_collection, interview_analyses_collection, ai_interview_sessions_collection
from bson import ObjectId

async def check():
    cursor = candidates_collection.find({"name": {"$regex": "Swastika", "$options": "i"}})
    candidates = []
    async for c in cursor:
        candidates.append(c)
    
    print(f"Found {len(candidates)} Swastika candidates:\n")
    
    for cand in candidates:
        cand_id = str(cand["_id"])
        print(f"{'='*60}")
        print(f"Name: {cand['name']}")
        print(f"ID: {cand_id}")
        print(f"Position ID: {cand.get('position_id', 'N/A')}")
        print(f"Role: {cand.get('role', 'N/A')}")
        print(f"Stage: {cand.get('stage', 'N/A')}")
        print(f"Verdict: {cand.get('verdict', 'N/A')}")
        print(f"Scores: {cand.get('scores', {})}")
        
        # Manual Interviews
        m_cursor = interview_analyses_collection.find({"candidate_id": cand_id})
        m_count = 0
        async for doc in m_cursor:
            m_count += 1
            print(f"  MANUAL [{m_count}]: Round L{doc.get('interview_round','?')}, "
                  f"Created: {str(doc.get('created_at','?'))[:19]}, "
                  f"Transcript: {len(doc.get('transcript',''))} chars, "
                  f"Strengths: {len(doc.get('key_strengths', []))}, "
                  f"Concerns: {len(doc.get('areas_of_concern', []))}")
        
        # AI Interviews
        a_cursor = ai_interview_sessions_collection.find({"candidate_id": cand_id})
        a_count = 0
        async for doc in a_cursor:
            a_count += 1
            entries = doc.get("transcript_entries", [])
            print(f"  AI [{a_count}]: Round L{doc.get('round','?')}, "
                  f"Created: {str(doc.get('created_at','?'))[:19]}, "
                  f"Entries: {len(entries)}, "
                  f"Raw transcript: {len(doc.get('transcript',''))} chars")
        
        print(f"\n  TOTAL: {m_count} manual + {a_count} AI = {m_count + a_count} interviews")
        print()

if __name__ == "__main__":
    asyncio.run(check())
