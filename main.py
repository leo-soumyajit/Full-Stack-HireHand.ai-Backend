import traceback
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from database import init_db
from routers import auth, positions, candidates, psychometric, resume_screen, schedules, assessment, ai_tools

app = FastAPI(
    title="HireHand AI Backend",
    description="Production-ready FastAPI backend — EOS-IA Psychometric + AI Resume Screening + Positions + Candidates + Auth",
    version="3.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_db_client():
    await init_db()
    print("✅ MongoDB indexes initialized (EOS-IA v3.0)")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    tc = traceback.format_exc()
    print("CRASH:", str(exc))
    print(tc)
    # NOTE: Do NOT manually set CORS headers here.
    # CORSMiddleware wraps the entire app and handles CORS on ALL responses
    # (including error responses). Adding it here creates duplicate headers
    # which Chrome blocks as a CORS violation → net::ERR_FAILED.
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "error": str(exc)},
    )


# Routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(positions.router, prefix="/api/positions", tags=["Positions"])
app.include_router(candidates.router, prefix="/api/positions", tags=["Candidates"])
app.include_router(psychometric.router, prefix="/api/psychometric", tags=["EOS-IA Psychometric"])
app.include_router(resume_screen.router, prefix="/api", tags=["AI Resume Screening"])
app.include_router(schedules.router, prefix="/api/schedules", tags=["Schedules"])
app.include_router(assessment.router, prefix="/api/assessment", tags=["Candidate Assessment"])
app.include_router(ai_tools.router, prefix="/api/ai", tags=["Dashboard AI Tools"])


@app.get("/")
def read_root():
    return {"message": "HireHand AI API v3.1 — EOS-IA Psychometric + AI Resume Screening 🧠🚀"}
