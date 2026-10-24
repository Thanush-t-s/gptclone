import os
os.chdir(r'C:\Users\tstha\.claude\projects\gpt')

from app import app

print("=" * 60)
print("Flask App Test")
print("=" * 60)

# Check config
print(f"\nSECRET_KEY: {app.config.get('SECRET_KEY')}")
print(f"SQLALCHEMY_DATABASE_URI: {app.config.get('SQLALCHEMY_DATABASE_URI')}")
print(f"FLASK_ENV: {app.config.get('FLASK_ENV')}")
print(f"SQLALCHEMY_ECHO: {app.config.get('SQLALCHEMY_ECHO')}")

# Try to create app context and db
try:
    with app.app_context():
        print("\nCreating database tables...")
        from extensions import db
        db.create_all()
        print("Database tables created successfully!")
        
        # List tables
        from sqlalchemy import inspect
        inspector = db.inspect(db.engine)
        tables = inspector.get_table_names()
        print(f"Tables: {tables}")
except Exception as e:
    print(f"\nError during db creation: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()