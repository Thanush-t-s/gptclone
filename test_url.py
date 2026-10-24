import os
os.chdir(r'C:\Users\tstha\.claude\projects\gpt')
from app import app
c = app.test_client()
r1 = c.get('/login')
r2 = c.get('/register')
r3 = c.get('/')
print('/login:', r1.status_code)
print('/register:', r2.status_code)
print('/', r3.status_code)
print()
if r1.status_code == 200:
    print('SUCCESS: /login works! Visit http://127.0.0.1:5000/login')
else:
    print('FAILED: /login did not return 200')