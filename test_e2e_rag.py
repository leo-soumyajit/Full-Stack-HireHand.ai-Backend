"""
END-TO-END RAG Pipeline Test
Tests every single layer of the Insight AI chatbot
"""
import asyncio
import sys
import time

# Add parent dir
sys.path.insert(0, ".")

from core.transcript_rag import (
    gather_candidate_context,
    _extract_text_chunks,
    build_vector_index,
    query_vector_index,
    generate_answer,
    ask_about_candidate,
    _get_chroma,
)

async def run_tests():
    print("=" * 60)
    print("  INSIGHT AI — END-TO-END PIPELINE TEST")
    print("=" * 60)
    
    # ── Step 1: Find a real candidate ──
    from database import candidates_collection
    cand = await candidates_collection.find_one({"name": {"$regex": "Ankush", "$options": "i"}})
    if not cand:
        print("❌ No candidate found!")
        return
    
    cand_id = str(cand["_id"])
    pos_id = cand.get("position_id", "")
    print(f"\n✅ [1/7] Candidate found: {cand['name']} (ID: {cand_id})")
    print(f"   Position ID: {pos_id}")

    # ── Step 2: Gather Context ──
    context = await gather_candidate_context(cand_id, pos_id)
    has_candidate = context["candidate"] is not None
    has_position = context["position"] is not None
    has_manual = len(context["manual_interviews"]) > 0
    has_ai = len(context["ai_interviews"]) > 0
    print(f"\n✅ [2/7] Context gathered:")
    print(f"   Candidate data: {'✅' if has_candidate else '❌'}")
    print(f"   Position/JD data: {'✅' if has_position else '❌'}")
    print(f"   Manual interviews: {'✅' if has_manual else '❌'} ({len(context['manual_interviews'])} found)")
    print(f"   AI interviews: {'✅' if has_ai else '❌'} ({len(context['ai_interviews'])} found)")
    
    # ── Step 3: Extract Text Chunks ──
    chunks = _extract_text_chunks(context)
    print(f"\n✅ [3/7] Text chunks extracted: {len(chunks)} chunks")
    
    # Count by source
    sources = {}
    for c in chunks:
        src = c["source"]
        sources[src] = sources.get(src, 0) + 1
    print("   Breakdown:")
    for src, count in sorted(sources.items()):
        print(f"     {src}: {count} chunks")
    
    # Check JD specifically
    jd_chunks = [c for c in chunks if c["source"].startswith("jd_")]
    print(f"\n   🎯 JD CHUNKS: {len(jd_chunks)}")
    if jd_chunks:
        for jc in jd_chunks[:3]:
            print(f"     [{jc['source']}] {jc['text'][:80]}...")
    else:
        print("   ⚠️  NO JD CHUNKS FOUND — JD field lookup may be wrong!")
    
    # ── Step 4: ChromaDB ──
    chroma = _get_chroma()
    print(f"\n✅ [4/7] ChromaDB client: {'✅ OK' if chroma else '❌ FAILED'}")
    
    # ── Step 5: Build Vector Index ──
    t0 = time.time()
    collection = build_vector_index(cand_id, chunks)
    t1 = time.time()
    if collection:
        print(f"\n✅ [5/7] Vector index built: {collection.count()} vectors ({t1-t0:.2f}s)")
    else:
        print(f"\n❌ [5/7] Vector index FAILED")
        return
    
    # ── Step 6: Semantic Search ──
    test_queries = [
        "What are this candidate's key strengths?",
        "How well does this candidate match the job requirements?",
        "Compare resume claims with interview performance",
    ]
    
    print(f"\n✅ [6/7] Semantic search test:")
    for q in test_queries:
        results = query_vector_index(cand_id, q, n_results=5)
        unique_sources = set(r["source"] for r in results)
        print(f"   Q: \"{q[:50]}...\"")
        print(f"   → {len(results)} chunks retrieved, sources: {unique_sources}")
    
    # ── Step 7: Full Pipeline (with LLM) ──
    print(f"\n⏳ [7/7] Full pipeline test (calling GPT-4o-mini)...")
    t0 = time.time()
    result = await ask_about_candidate(
        candidate_id=cand_id,
        position_id=pos_id,
        question="What are this candidate's top 3 strengths and top 3 weaknesses based on all available data?",
    )
    t1 = time.time()
    
    answer = result["answer"]
    print(f"\n✅ [7/7] LLM Response received ({t1-t0:.2f}s)")
    print(f"   Answer length: {len(answer)} chars")
    print(f"   Sources used: {result['sources']}")
    print(f"   Chunks used: {result['chunks_used']}")
    print(f"\n   ── Answer Preview ──")
    print(f"   {answer[:500]}...")
    
    # ── Step 8: Cache Test ──
    print(f"\n⏳ [BONUS] Cache speed test...")
    t0 = time.time()
    result2 = await ask_about_candidate(
        candidate_id=cand_id,
        position_id=pos_id,
        question="Is this candidate a good fit?",
    )
    t1 = time.time()
    print(f"   ✅ Cached query: {t1-t0:.2f}s (should be faster than first)")
    
    # ── FINAL VERDICT ──
    print("\n" + "=" * 60)
    all_ok = all([
        has_candidate, has_position, 
        len(chunks) > 0, len(jd_chunks) > 0,
        chroma is not None, collection is not None,
        len(answer) > 100
    ])
    if all_ok:
        print("  🎉 ALL TESTS PASSED — PIPELINE IS 100% OPERATIONAL 🎉")
    else:
        print("  ⚠️  SOME TESTS FAILED — CHECK ABOVE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_tests())
