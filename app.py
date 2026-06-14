import os
from urllib.parse import urlparse

from flask import request, Flask, render_template, g, redirect, url_for, flash
from flask_login import (
    LoginManager, UserMixin,
    login_user, logout_user, login_required, current_user,
)
from werkzeug.security import generate_password_hash, check_password_hash
import pandas
from bisect import bisect_left
from datetime import date, datetime
import sqlite3

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = os.environ.get('SECRET_KEY', 'dev-change-me-in-production')

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'error'

# ---------------------------------------------------------------------------
# WHO data — loaded once at startup
# ---------------------------------------------------------------------------
df_b013 = pandas.read_excel("data/tab_lhfa_boys_p_0_13.xlsx")
df_g013 = pandas.read_excel("data/tab_lhfa_girls_p_0_13.xlsx")
df_b02  = pandas.read_excel("data/tab_lhfa_boys_p_0_2.xlsx")
df_g02  = pandas.read_excel("data/tab_lhfa_girls_p_0_2.xlsx")
df_b25  = pandas.read_excel("data/tab_lhfa_boys_p_2_5.xlsx")
df_g25  = pandas.read_excel("data/tab_lhfa_girls_p_2_5.xlsx")
df_b520 = pandas.read_excel("data/hfa-boys-perc-who2007-exp.xlsx")
df_g520 = pandas.read_excel("data/hfa-girls-perc-who2007-exp.xlsx")

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect('db/riseup.db')
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


def query_db(query, args=(), one=False):
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv


def init_db():
    with sqlite3.connect('db/riseup.db') as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS Users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            email         TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS Children (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id  INTEGER,
            name     TEXT NOT NULL,
            birthday TEXT NOT NULL,
            gender   TEXT NOT NULL,
            height   REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES Users(id)
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS Records (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id INTEGER NOT NULL,
            height   REAL NOT NULL,
            date     TEXT NOT NULL,
            FOREIGN KEY (child_id) REFERENCES Children(id)
        )''')
        # Migration: add user_id column to existing Children tables that lack it
        try:
            conn.execute('ALTER TABLE Children ADD COLUMN user_id INTEGER REFERENCES Users(id)')
        except sqlite3.OperationalError:
            pass  # Column already exists


# ---------------------------------------------------------------------------
# Auth — User model + login_manager
# ---------------------------------------------------------------------------

class User(UserMixin):
    def __init__(self, id, email):
        self.id = id
        self.email = email


@login_manager.user_loader
def load_user(user_id):
    row = query_db('SELECT * FROM Users WHERE id=?', (user_id,), one=True)
    if row is None:
        return None
    return User(row['id'], row['email'])


# ---------------------------------------------------------------------------
# Growth helpers
# ---------------------------------------------------------------------------

def get_df(weeks, months, gender):
    if weeks <= 13:
        return df_b013 if gender == 'male' else df_g013
    elif months <= 24:
        return df_b02 if gender == 'male' else df_g02
    elif months <= 60:
        return df_b25 if gender == 'male' else df_g25
    elif months <= 228:
        return df_b520 if gender == 'male' else df_g520
    return None


def compute_percentile(height, weeks, months, gender):
    df = get_df(weeks, months, gender)
    if df is None:
        return None
    if 'Week' in df.columns:
        row = df[df['Week'] == weeks]
    elif 'Month' in df.columns:
        row = df[df['Month'] == months]
    else:
        return None
    if row.empty:
        return None
    values = row.iloc[0].values.tolist()
    heights = [v for v in values[5:] if isinstance(v, (int, float)) and not pandas.isna(v)]
    i = bisect_left(heights, float(height))
    col_idx = min(i + 5, len(df.columns) - 1)
    return str(df.columns[col_idx])


def format_age_between(birth_date, ref_date):
    total_months = (ref_date.year - birth_date.year) * 12 + (ref_date.month - birth_date.month)
    if ref_date.day < birth_date.day:
        total_months -= 1
    total_months = max(0, total_months)
    years, months = divmod(total_months, 12)
    if years == 0:
        return f"{months} mo"
    elif months == 0:
        return f"{years} yr"
    return f"{years} yr {months} mo"


def format_age(birthday_str):
    birth_date = datetime.strptime(birthday_str, '%Y-%m-%d').date()
    return format_age_between(birth_date, date.today())


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']
        confirm = request.form['confirm']

        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return render_template('register.html', email=email)

        if password != confirm:
            flash('Passwords do not match.', 'error')
            return render_template('register.html', email=email)

        if query_db('SELECT id FROM Users WHERE email=?', (email,), one=True):
            flash('That email is already registered.', 'error')
            return render_template('register.html', email=email)

        pw_hash = generate_password_hash(password)
        with sqlite3.connect('db/riseup.db') as conn:
            conn.execute('INSERT INTO Users (email, password_hash) VALUES (?,?)', (email, pw_hash))

        flash('Account created — please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html', email='')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']

        row = query_db('SELECT * FROM Users WHERE email=?', (email,), one=True)
        if row is None or not check_password_hash(row['password_hash'], password):
            flash('Invalid email or password.', 'error')
            return render_template('login.html', email=email)

        login_user(User(row['id'], row['email']))
        next_page = request.args.get('next')
        # Guard against open-redirect attacks
        if next_page and urlparse(next_page).netloc != '':
            next_page = None
        return redirect(next_page or url_for('home'))

    return render_template('login.html', email='')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('landing'))


# ---------------------------------------------------------------------------
# App routes
# ---------------------------------------------------------------------------

@app.route('/')
def landing():
    return render_template('landing.html')


@app.route('/home')
@login_required
def home():
    rows = query_db('SELECT * FROM Children WHERE user_id=? ORDER BY name', (current_user.id,))
    children = []
    for row in rows:
        child = dict(row)
        child['age_display'] = format_age(child['birthday'])
        children.append(child)
    return render_template('home.html', children=children)


@app.route('/child/<int:child_id>')
@login_required
def child_history(child_id):
    child_row = query_db(
        'SELECT * FROM Children WHERE id=? AND user_id=?',
        (child_id, current_user.id), one=True
    )
    if child_row is None:
        return "Not found", 404

    child = dict(child_row)
    child['age_display'] = format_age(child['birthday'])
    birth_date = datetime.strptime(child['birthday'], '%Y-%m-%d').date()

    record_rows = query_db('SELECT * FROM Records WHERE child_id=? ORDER BY date DESC', (child_id,))
    records = []
    for rec in record_rows:
        try:
            rec_date = datetime.strptime(rec['date'], '%Y-%m-%d').date()
        except ValueError:
            rec_date = datetime.strptime(rec['date'], '%m-%d-%Y').date()
        days = (rec_date - birth_date).days
        records.append({
            'date': rec_date.strftime('%Y-%m-%d'),
            'height': rec['height'],
            'age': format_age_between(birth_date, rec_date),
            'percentile': compute_percentile(rec['height'], days // 7, days // 30, child['gender']) or 'N/A',
        })

    return render_template('child.html', child=child, records=records)


@app.route('/child/<int:child_id>/add', methods=['POST'])
@login_required
def add_measurement(child_id):
    child_row = query_db(
        'SELECT * FROM Children WHERE id=? AND user_id=?',
        (child_id, current_user.id), one=True
    )
    if child_row is None:
        return "Not found", 404

    height = float(request.form['height'])
    meas_date = request.form['date']

    with sqlite3.connect('db/riseup.db') as conn:
        conn.execute('INSERT INTO Records (child_id, height, date) VALUES (?,?,?)', (child_id, height, meas_date))
        conn.execute('UPDATE Children SET height=? WHERE id=?', (height, child_id))

    return redirect(url_for('child_history', child_id=child_id))


@app.route('/form', methods=['GET', 'POST'])
@login_required
def form():
    if request.method == 'GET':
        return render_template('form.html')

    name = request.form['name']
    birthday = request.form['date']
    height = float(request.form['height'])
    gender = request.form['gender']

    birth_date = datetime.strptime(birthday, '%Y-%m-%d').date()
    days = (date.today() - birth_date).days

    with sqlite3.connect('db/riseup.db') as conn:
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO Children (user_id, name, birthday, gender, height) VALUES (?,?,?,?,?)',
            (current_user.id, name, birthday, gender, height)
        )
        child_id = cursor.lastrowid
        cursor.execute(
            'INSERT INTO Records (child_id, height, date) VALUES (?,?,?)',
            (child_id, height, date.today().strftime('%Y-%m-%d'))
        )

    percentile = compute_percentile(height, days // 7, days // 30, gender)
    return render_template('result.html', name=name, height=height, percentile=percentile, child_id=child_id)


if __name__ == '__main__':
    init_db()
    app.run(port=8080, host='127.0.0.1', debug=True)
