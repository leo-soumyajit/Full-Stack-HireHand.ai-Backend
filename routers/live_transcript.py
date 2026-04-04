"""
Live Transcript Sync — Backend-powered real-time transcript sharing.
PeerJS data channels are unreliable across NATs/TURN, so we use
simple REST endpoints with MongoDB for guaranteed delivery.

- Both Host (Interviewer) and Guest (Candidate) POST their speech entries.
- Host polls GET to receive all entries (both parties) sorted by timestamp.
- Entries are keyed by roomId so no auth is needed (guest has no JWT).
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone
from database import database

router = APIRouter()

# Use a dedicated MongoDB collection for live transcripts
live_transcripts = database["live_transcripts"]


class TranscriptEntryIn(BaseModel):
    room_id: str
    speaker: str
    text: str
    timestamp: str


class TranscriptEntryOut(BaseModel):
    id: str
    room_id: str
    speaker: str
    text: str
    timestamp: str
    created_at: str


@router.post("/live-transcript", status_code=201)
async def post_transcript_entry(entry: TranscriptEntryIn):
    """
    Both interviewer and candidate call this to save their transcript entries.
    No auth required — keyed by room_id which is a secret shared link.
    """
    doc = {
        "room_id": entry.room_id,
        "speaker": entry.speaker,
        "text": entry.text,
        "timestamp": entry.timestamp,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await live_transcripts.insert_one(doc)
    return {"id": str(result.inserted_id), "status": "saved"}


@router.get("/live-transcript/{room_id}")
async def get_transcript_entries(room_id: str, after: Optional[str] = None):
    """
    Host polls this to get all transcript entries for the room.
    Optional 'after' param (ISO timestamp) to get only new entries (incremental).
    """
    query = {"room_id": room_id}
    if after:
        query["created_at"] = {"$gt": after}
    
    cursor = live_transcripts.find(query).sort("created_at", 1)
    docs = await cursor.to_list(length=500)
    
    return [
        {
            "id": str(d["_id"]),
            "room_id": d["room_id"],
            "speaker": d["speaker"],
            "text": d["text"],
            "timestamp": d["timestamp"],
            "created_at": d["created_at"],
        }
        for d in docs
    ]


@router.delete("/live-transcript/{room_id}")
async def cleanup_transcript(room_id: str):
    """Cleanup live transcripts after interview ends."""
    result = await live_transcripts.delete_many({"room_id": room_id})
    return {"deleted": result.deleted_count}
