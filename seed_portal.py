"""
Seed demo data for the Job Seeker portal.

Safe & idempotent:
  - Creates a few PUBLISHED demo positions (tagged _seed="portal_demo") under the
    existing HR owner, each with a full JD + skills.
  - Also publishes any of your REAL positions that already have a JD (reversible
    from the HR "Publish" toggle).
  - Creates 3 verified demo job-seeker accounts with overlapping skills so
    recommendations light up immediately.

Run locally:   python seed_portal.py
Run on EC2:    docker compose -f docker-compose.prod.yml exec backend python seed_portal.py
Reset demo:    python seed_portal.py --reset   (removes only _seed demo docs)
"""
import os
import sys
from datetime import datetime, timezone

import bcrypt
from pymongo import MongoClient

# Read the connection string from the environment (set in your .env / container).
# Locally:  MONGO_URI="mongodb+srv://..." python seed_portal.py
MONGO_URI = os.getenv("MONGO_URI", "")
SEED_TAG = "portal_demo"
DEMO_PW = "Demo@1234"


def hpw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


DEMO_JOBS = [
    {
        "title": "Senior Frontend Engineer",
        "business_unit": "Engineering", "location": "Bengaluru, India", "level": "Senior",
        "years_of_experience": "4-7",
        "jd": {
            "purpose": "Build fast, accessible, delightful web experiences for our flagship product used by thousands of recruiters daily.",
            "education": ["B.Tech/B.E. in Computer Science or equivalent experience"],
            "experience": ["4+ years building production React apps", "Experience with component systems & performance tuning"],
            "responsibilities": ["Own frontend features end-to-end", "Collaborate with design on pixel-perfect UI", "Improve Core Web Vitals", "Mentor junior engineers"],
            "skills": ["React", "TypeScript", "Next.js", "Tailwind CSS", "Node.js"],
            "non_negotiables": ["Strong JavaScript fundamentals", "Hands-on React experience"],
        },
    },
    {
        "title": "Backend Engineer (Python)",
        "business_unit": "Platform", "location": "Remote", "level": "Mid",
        "years_of_experience": "2-5",
        "jd": {
            "purpose": "Design and scale the APIs and data pipelines powering our AI hiring platform.",
            "education": ["Bachelor's in CS or equivalent"],
            "experience": ["3+ years in backend development", "Experience with async Python and REST APIs"],
            "responsibilities": ["Build FastAPI services", "Model data in MongoDB", "Containerize with Docker", "Deploy on AWS"],
            "skills": ["Python", "FastAPI", "MongoDB", "Docker", "AWS"],
            "non_negotiables": ["Python proficiency", "Understanding of REST/async"],
        },
    },
    {
        "title": "Full Stack Developer",
        "business_unit": "Product", "location": "Pune, India", "level": "Mid",
        "years_of_experience": "2-4",
        "jd": {
            "purpose": "Ship features across the stack — from React UI to Node APIs — in a fast-moving product team.",
            "education": ["Any graduate with strong portfolio"],
            "experience": ["2+ years full-stack experience"],
            "responsibilities": ["Build React frontends", "Write Node/Express APIs", "Work with MongoDB", "Own features end-to-end"],
            "skills": ["React", "Node.js", "Express", "MongoDB", "TypeScript"],
            "non_negotiables": ["JavaScript/TypeScript", "Full-stack mindset"],
        },
    },
    {
        "title": "Data Analyst",
        "business_unit": "Analytics", "location": "Hyderabad, India", "level": "Junior",
        "years_of_experience": "0-2",
        "jd": {
            "purpose": "Turn hiring data into insights that help recruiters make better decisions.",
            "education": ["Bachelor's in Statistics, CS, or related"],
            "experience": ["Internship or 1+ year in analytics"],
            "responsibilities": ["Write SQL queries", "Build dashboards", "Analyze funnel metrics", "Present findings"],
            "skills": ["SQL", "Python", "Pandas", "Power BI", "Excel"],
            "non_negotiables": ["SQL basics", "Analytical thinking"],
        },
    },
]

DEMO_SEEKERS = [
    {
        "name": "Riya Sharma", "email": "riya.sharma@example.com",
        "headline": "Frontend Engineer • React & TypeScript",
        "location": "Bengaluru, India", "current_role": "Frontend Engineer",
        "total_experience_years": 5,
        "summary": "Frontend engineer with 5 years building performant React apps, design systems and accessible UIs.",
        "skills": ["React", "TypeScript", "Next.js", "Tailwind CSS", "JavaScript", "Redux"],
        "resume_text": "Riya Sharma — Frontend Engineer. 5 years of React, TypeScript, Next.js, Tailwind. Built design systems, improved Core Web Vitals, led UI for a SaaS product.",
    },
    {
        "name": "Arjun Mehta", "email": "arjun.mehta@example.com",
        "headline": "Backend Engineer • Python & FastAPI",
        "location": "Remote", "current_role": "Backend Developer",
        "total_experience_years": 3,
        "summary": "Backend developer specializing in async Python, FastAPI microservices, MongoDB and Docker on AWS.",
        "skills": ["Python", "FastAPI", "MongoDB", "Docker", "AWS", "REST APIs"],
        "resume_text": "Arjun Mehta — Backend Developer. 3 years Python/FastAPI, MongoDB, Dockerized services on AWS EC2. Built scalable REST APIs and data pipelines.",
    },
    {
        "name": "Neha Verma", "email": "neha.verma@example.com",
        "headline": "Full Stack Developer • MERN",
        "location": "Pune, India", "current_role": "Full Stack Developer",
        "total_experience_years": 3,
        "summary": "Full-stack developer comfortable across React, Node/Express and MongoDB, shipping features end-to-end.",
        "skills": ["React", "Node.js", "Express", "MongoDB", "TypeScript", "JavaScript"],
        "resume_text": "Neha Verma — Full Stack Developer. 3 years MERN stack (MongoDB, Express, React, Node). Delivered end-to-end product features with TypeScript.",
    },
]


def main():
    reset = "--reset" in sys.argv
    if not MONGO_URI:
        print("❌ Set MONGO_URI first, e.g.  MONGO_URI='mongodb+srv://...' python seed_portal.py")
        return
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=15000)
    db = client["hirehand"]
    # trigger connection
    db.command("ping")
    print("✅ Connected to MongoDB")

    positions = db["positions"]
    users = db["users"]
    seekers = db["job_seekers"]

    if reset:
        d1 = positions.delete_many({"_seed": SEED_TAG}).deleted_count
        d2 = seekers.delete_many({"_seed": SEED_TAG}).deleted_count
        print(f"🧹 Removed {d1} demo positions, {d2} demo seekers")
        return

    # 1) Find the HR owner (first user) to attach demo positions to
    owner = users.find_one({"role": "owner"}) or users.find_one({})
    if not owner:
        print("⚠️ No HR user found — create an HR account first, then re-run.")
        return
    owner_id = str(owner["_id"])
    print(f"👤 HR owner: {owner.get('email')} ({owner_id})")

    now = datetime.now(timezone.utc).isoformat()

    # 2) Publish existing REAL positions that have a JD
    real_published = 0
    for p in positions.find({"_seed": {"$exists": False}, "jd": {"$ne": None}}):
        if not p.get("is_published"):
            positions.update_one({"_id": p["_id"]}, {"$set": {"is_published": True, "published_at": now, "updated_at": now}})
            real_published += 1
    print(f"📢 Published {real_published} of your existing positions (with JD)")

    # 3) Create demo published positions (idempotent by title+_seed)
    created = 0
    for i, job in enumerate(DEMO_JOBS):
        exists = positions.find_one({"_seed": SEED_TAG, "title": job["title"]})
        if exists:
            continue
        doc = {
            "user_id": owner_id,
            "req_id": f"REQ-DEMO-{1000 + i}",
            "title": job["title"],
            "business_unit": job["business_unit"],
            "location": job["location"],
            "level": job["level"],
            "years_of_experience": job["years_of_experience"],
            "status": "Active",
            "jd": job["jd"],
            "jd_versions": [],
            "l1_questions": [],
            "candidates_count": 0,
            "shortlisted_count": 0,
            "is_published": True,
            "published_at": now,
            "created_at": now,
            "updated_at": now,
            "_seed": SEED_TAG,
        }
        positions.insert_one(doc)
        created += 1
    print(f"🧩 Created {created} demo published positions")

    # 4) Create verified demo seekers
    seeded = 0
    for s in DEMO_SEEKERS:
        if seekers.find_one({"email": s["email"]}):
            continue
        doc = {
            "name": s["name"],
            "email": s["email"],
            "hashed_password": hpw(DEMO_PW),
            "is_verified": True,
            "headline": s["headline"],
            "location": s["location"],
            "current_role": s["current_role"],
            "total_experience_years": s["total_experience_years"],
            "summary": s["summary"],
            "skills": s["skills"],
            "education": [{"degree": "B.Tech Computer Science", "institution": "Demo University", "year": "2019"}],
            "work_experience": [{"title": s["current_role"], "company": "Prev Corp", "duration": "2021-Present", "description": s["summary"]}],
            "resume_text": s["resume_text"],
            "structured_profile": {"skills": s["skills"], "summary": s["summary"]},
            "resume_url": None,
            "preferences": {"desired_roles": [s["current_role"]], "preferred_locations": [s["location"]], "job_type": "Full-time"},
            "created_at": now,
            "_seed": SEED_TAG,
        }
        seekers.insert_one(doc)
        seeded += 1
    print(f"🙋 Created {seeded} demo seekers (password for all: {DEMO_PW})")
    for s in DEMO_SEEKERS:
        print(f"     • {s['email']}")

    print("\n✅ Seed complete. Visit /jobs and log in as a demo seeker to see recommendations.")


if __name__ == "__main__":
    main()
