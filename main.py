from fastapi import FastAPI
from fastapi import Depends
from mysite.db.models import Users

from mysite.api.auth import router as auth_router
from mysite.api.users import router as user_router
from mysite.security.permissions import (
    get_current_user,
    director_required,
    admin_required,
    teacher_required,
    student_required,
    parent_required
)

app = FastAPI(title="Smart School API",description="Smart School Backend System",version="1.0.0")
app.include_router(auth_router)
app.include_router(user_router)

@app.get("/test/me")
def test_me(
    user: Users = Depends(get_current_user)
):
    return {
        "message": "Авторизация ийгиликтүү!",
        "name": user.full_name,
        "role": user.role,
        "school_id": user.school_id
    }


@app.get("/test/director")
def test_director(
    user: Users = Depends(director_required)
):
    return {
        "message": "Director access granted",
        "name": user.full_name
    }


@app.get("/test/admin")
def test_admin(
    user: Users = Depends(admin_required)
):
    return {
        "message": "Admin access granted",
        "name": user.full_name
    }


@app.get("/test/teacher")
def test_teacher(
    user: Users = Depends(teacher_required)
):
    return {
        "message": "Teacher access granted"
    }


@app.get("/")
def home():
    return {
        "message": "Smart School API is running!"
    }