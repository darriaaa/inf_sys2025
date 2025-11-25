from flask import Flask, request, jsonify, render_template_string, redirect, make_response
from flask_sqlalchemy import SQLAlchemy
import jwt
import datetime

app = Flask(__name__)

# SQLite у файлі всередині контейнера
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///auth.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'supersecretkey'  # для JWT

db = SQLAlchemy(app)


class User(db.Model):
    """ Проста модель користувача: username + password """
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)


def init_db():
    """
    Створюємо таблиці й додаємо одного дефолтного користувача admin/admin.
    Викликаємо руками при старті, без before_first_request (воно випиляне у Flask 3).
    """
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            u = User(username='admin', password='admin')
            db.session.add(u)
            db.session.commit()


LOGIN_PAGE = """
<!doctype html>
<html>
<head><title>Login</title></head>
<body>
  <h2>Login to Monitoring System</h2>
  <form method="post" action="/auth/login">
    <label>Username: <input type="text" name="username" /></label><br/>
    <label>Password: <input type="password" name="password" /></label><br/>
    <button type="submit">Login</button>
  </form>
  {% if error %}
    <p style="color:red;">{{ error }}</p>
  {% endif %}
</body>
</html>
"""

@app.get('/')
@app.get('/auth/')
def index():
    """Головна сторінка """
    return render_template_string(LOGIN_PAGE)


def create_token(username: str) -> str:
    """Створюємо JWT-токен з терміном дії 1 година."""
    payload = {
        'sub': username,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=1)
    }
    token = jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')
    return token

@app.post('/login')
@app.post('/auth/login')
def login():
    """ Обробка логіну з HTML-форми. Записуємо JWT в cookie "access_token" """
    username = request.form.get('username')
    password = request.form.get('password')

    user = User.query.filter_by(username=username, password=password).first()
    if not user:
        return render_template_string(LOGIN_PAGE, error="Invalid credentials")

    token = create_token(user.username)

    # редіректимось на /auth/success — цей шлях точно існує за проксі
    resp = make_response(redirect("/auth/success"))
    resp.set_cookie("access_token", token, httponly=True)
    return resp

@app.get('/success')
@app.get('/auth/success')
def success():
    return "<h3>Login successful. You can now access /grafana/ and /prometheus/ via Nginx.</h3>"


@app.get('/api/login')
@app.get('/auth/api/login')
def api_login():
    """
    Варіант логіну через API:  /auth/api/login?username=admin&password=admin
    """
    username = request.args.get('username')
    password = request.args.get('password')
    user = User.query.filter_by(username=username, password=password).first()
    if not user:
        return jsonify({'error': 'invalid credentials'}), 401

    token = create_token(user.username)
    return jsonify({'token': token})


@app.get('/verify')
@app.get('/auth/verify')
def verify():
    """
    Ендпойнт для Nginx (auth_request).
    Зчитує JWT з cookie "access_token". Якщо токен валідний — 200,
    інакше 401.
    """
    token = request.cookies.get('access_token', '')

    if not token:
        return "No token", 401

    try:
        jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        return "OK", 200
    except jwt.ExpiredSignatureError:
        return "Token expired", 401
    except Exception:
        return "Invalid token", 401


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000)
