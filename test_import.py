import sys
sys.path.insert(0, r'C:\Users\tstha\.claude\projects\gpt')

from app import app
print('App imported successfully')

# Test that blueprints are initialized
print('Routes registered:', list(app.blueprints.keys()))