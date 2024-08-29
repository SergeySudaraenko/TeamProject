from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from src.routes import auth, comments, photos, profile, rating, search, users
from src.config.config import settings
from src.database.db import get_db
from src.services.auth_service import Auth
from src.database.models import Role, User

origins = [
    "http://localhost:3000"
]

app = FastAPI()

# Налаштування CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Інстанс для перевірки токенів
auth_service = Auth()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# Утиліти для ролей
def role_required(required_role: Role):
    def decorator(func):
        async def wrapper(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
            user = await auth_service.get_current_user(token, db)
            if not user or user.role != required_role:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостатньо прав")
            return await func(user, db)
        return wrapper
    return decorator

@app.post("/auth/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(form_data.username, form_data.password, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неправильні облікові дані")
    access_token = await auth_service.create_access_token(data={"sub": user.username, "role": user.role.value})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/auth/logout")
async def logout(token: str = Depends(oauth2_scheme)):
    # Реалізація механізму виходу через чорний список токенів
    await auth_service.blacklist_token(token)

# Включення маршрутів
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(comments.router, prefix="/comments", tags=["comments"])
app.include_router(profile.router, prefix="/profile", tags=["profile"])
app.include_router(rating.router, prefix="/rating", tags=["rating"])
app.include_router(search.router, prefix="/search", tags=["search"])
app.include_router(photos.router, prefix="/photos", tags=["photos"])
app.include_router(users.router, prefix="/users", tags=["users"])

@app.get('/')
def index():
    return {'message': 'Контактний додаток'}

@app.get('/api/healthcheker')
async def healthcheker(db: AsyncSession = Depends(get_db)):
    try:
        # Перевірка з'єднання з базою даних
        result = await db.execute(text('SELECT 1'))
        result = result.fetchone()
        if result is None:
            raise HTTPException(status_code=500, detail='База даних не налаштована правильно')
        return {'message': 'Ласкаво просимо до FastAPI!'}
    except Exception as e:
        raise HTTPException(status_code=500, detail='Помилка підключення до бази даних')

@app.on_event("startup")
async def startup():
    # Перевірка, чи є перший користувач адміністратором
    async with get_db() as session:
        result = await session.execute("SELECT COUNT(*) FROM users")
        count = result.scalar()
        if count == 0:
            # Створення адміністратора за замовчуванням
            admin_user = User(
                username="admin",
                email="admin@example.com",
                password="admin_password",  # Замініть на хешований пароль
                role=Role.admin
            )
            session.add(admin_user)
            await session.commit()

@app.on_event("shutdown")
async def shutdown():
    # Очищення ресурсів
    pass

async def authenticate_user(username: str, password: str, db: AsyncSession):
    # Перевірка існування користувача і відповідність пароля
    user = await db.execute("SELECT * FROM users WHERE username = :username", {"username": username})
    user = user.fetchone()
    if user and auth_service.verify_password(password, user['password']):
        return user
    return None
