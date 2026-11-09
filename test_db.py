from mysite.db.database import engine

try:
    with engine.connect() as connection:
        print("DATABASE CONNECTED SUCCESSFULLY!")

except Exception as e:
    print("DATABASE ERROR:", repr(e))