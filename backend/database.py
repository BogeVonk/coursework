
import os
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker, declarative_base

# Подключение к PostgreSQL
DATABASE_URL = URL.create(
    drivername="postgresql+psycopg2",
    username=os.getenv('POTOLOK_DB_USER', 'postgres'),
    password=os.getenv('POTOLOK_DB_PASSWORD', ''),
    host=os.getenv('POTOLOK_DB_HOST', 'localhost'),
    port=int(os.getenv('POTOLOK_DB_PORT', '5432')),
    database=os.getenv('POTOLOK_DB_NAME', 'potolok_db')
)

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()


# Получение подключения к базе данных
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
