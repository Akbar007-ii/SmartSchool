import os

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from mysite.api import (auth,schools,users,classes,subjects,teacher_assignments,teacher_import,
                        student_import,students,student_promotion,parents,
                        admin,excel_templates,journal,homeworks,absence_requests,
                        ratings,olympiad,me,announcements,notifications,public)
from mysite.db.database import get_db
from mysite.services.files import MEDIA_ROOT, MEDIA_URL

app = FastAPI(title="Smart School API",description="Smart School Backend System",version="2.0.0")

# CORS: фронтенддин даректери .env файлында CORS_ORIGINS аркылуу берилет
# (үтүр менен бөлүнгөн), мис: CORS_ORIGINS=https://smartschool.kg,http://localhost:3000
# MVP үчүн CORS_ORIGINS=* коюлса, бардык даректерге уруксат берилет.
# Авторизация cookie эмес, Bearer токен менен болгондуктан бул коопсуз.
cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]
allow_all_origins = "*" in cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if allow_all_origins else cors_origins,
    allow_credentials=not allow_all_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Жүктөлгөн сүрөттөр жана файлдар (үй тапшырма, баннер, аватар)
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
app.mount(MEDIA_URL, StaticFiles(directory=MEDIA_ROOT), name="media")

app.include_router(auth.router)
app.include_router(me.router)
app.include_router(public.router)
app.include_router(admin.router)
app.include_router(excel_templates.router)
# /classes/{id}/temp-passwords (класс жетекчинин сыр сөздөр тизмеси)
app.include_router(admin.classes_router)
app.include_router(journal.router)
app.include_router(homeworks.router)
app.include_router(absence_requests.router)
app.include_router(ratings.router)
app.include_router(olympiad.router)
app.include_router(announcements.router)
app.include_router(notifications.router)
app.include_router(users.router)
app.include_router(schools.router)
app.include_router(classes.router)
app.include_router(subjects.router)
app.include_router(teacher_assignments.router)
app.include_router(teacher_import.router)
app.include_router(student_promotion.router)
app.include_router(student_import.router)
app.include_router(students.router)
app.include_router(parents.router)


@app.get("/", tags=["Health"])
def home():
    return {
        "message": "Smart School API is running!"
    }


# Docker healthcheck жана мониторинг үчүн: API да, база да иштеп жатабы
@app.get("/health", tags=["Health"])
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=503, detail="База жеткиликсиз")
    return {"status": "ok"}
