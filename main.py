import traceback
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from database import init_db
from routers import auth, positions, candidates, psychometric

app = FastAPI(
    title="HireHand AI Backend",
    description="Production-ready FastAPI backend — EOS-IA Psychometric + Positions + Candidates + Auth",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:8080",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8080",
    ],
    allow_credentials=True,
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
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "error": str(exc)},
        headers={"Access-Control-Allow-Origin": "*"},
    )


# Routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(positions.router, prefix="/api/positions", tags=["Positions"])
app.include_router(candidates.router, prefix="/api/positions", tags=["Candidates"])
app.include_router(psychometric.router, prefix="/api/psychometric", tags=["EOS-IA Psychometric"])


@app.get("/")
def read_root():
    return {"message": "HireHand AI API v3.0 — EOS-IA Psychometric Intelligence 🧠🚀"}
