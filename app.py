import os
from urllib.parse import urlparse

from flask import request, Flask, render_template, g, redirect, url_for, flash, jsonify
from flask_login import (
    LoginManager, UserMixin,
    login_user, logout_user, login_required, current_user,
)
from werkzeug.security import generate_password_hash, check_password_hash
import pandas
from bisect import bisect_left
from datetime import date, datetime
from supabase import create_client, Client
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = os.environ.get('SECRET_KEY', 'dev-change-me-in-production')

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'error'

supabase: Client = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_KEY")
)

gemini = OpenAI(
    api_key=os.environ.get("NEXT_PUBLIC_GEMINI_API_KEY"),
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
)

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

# def query_db(query, args=(), one=False):
#     cur = get_db().execute(query, args)
#     rv = cur.fetchall()
#     cur.close()
#     return (rv[0] if rv else None) if one else rv


# def init_db():
#     with sqlite3.connect('db/riseup.db') as conn:
#         conn.execute('''CREATE TABLE IF NOT EXISTS users (
#             id            INTEGER PRIMARY KEY AUTOINCREMENT,
#             email         TEXT NOT NULL UNIQUE,
#             password_hash TEXT NOT NULL
#         )''')
#         conn.execute('''CREATE TABLE IF NOT EXISTS children (
#             id       INTEGER PRIMARY KEY AUTOINCREMENT,
#             user_id  INTEGER,
#             name     TEXT NOT NULL,
#             birthday TEXT NOT NULL,
#             gender   TEXT NOT NULL,
#             height   REAL NOT NULL,
#             FOREIGN KEY (user_id) REFERENCES users(id)
#         )''')
#         conn.execute('''CREATE TABLE IF NOT EXISTS records (
#             id       INTEGER PRIMARY KEY AUTOINCREMENT,
#             child_id INTEGER NOT NULL,
#             height   REAL NOT NULL,
#             date     TEXT NOT NULL,
#             FOREIGN KEY (child_id) REFERENCES children(id)
#         )''')
#         # Migration: add user_id column to existing children tables that lack it
#         try:
#             conn.execute('ALTER TABLE children ADD COLUMN user_id INTEGER REFERENCES users(id)')
#         except sqlite3.OperationalError:
#             pass  # Column already exists


# ---------------------------------------------------------------------------
# Auth — User model + login_manager
# ---------------------------------------------------------------------------

class User(UserMixin):
    def __init__(self, id, email):
        self.id = id
        self.email = email


@login_manager.user_loader
def load_user(user_id):
    # row = query_db('SELECT * FROM users WHERE id=?', (user_id,), one=True)
    row = (
        supabase.table('users')
        .select("*")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    if not row:
        return None
    return User(row.data['id'], row.data['email'])


# Growth helpers


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


# Auth routes


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

        # if query_db('SELECT id FROM users WHERE email=?', (email,), one=True):
        response = (
            supabase.table("users")
            .select("*")
            .eq("email", email)
            .maybe_single()
            .execute()
        )
        if response:
            flash('That email is already registered.', 'error')
            return render_template('register.html', email=email)

        pw_hash = generate_password_hash(password)
        response = (
            supabase.table("users")
            .insert({"email": email, "password_hash": pw_hash})
            .execute()
        )


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

        # row = query_db('SELECT * FROM users WHERE email=?', (email,), one=True)
        row = (
            supabase.table("users")
            .select("*")
            .eq("email", email)
            .maybe_single()
            .execute()
        )
        if not row or not check_password_hash(row.data['password_hash'], password):
            flash('Invalid email or password.', 'error')
            return render_template('login.html', email=email)

        login_user(User(row.data['id'], row.data['email']))
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


# App routes


@app.route('/')
def landing():
    return render_template('landing.html')


@app.route('/home')
@login_required
def home():
    # rows = query_db('SELECT * FROM children WHERE user_id=? ORDER BY name', (current_user.id,))
    rows = (
        supabase.table("children")
        .select("*")
        .eq("user_id", current_user.id)
        .order("name", desc=False)
        .execute()
    )
    children = []
    for row in rows.data:
        child = dict(row)
        child['age_display'] = format_age(child['birthday'])
        children.append(child)
    return render_template('home.html', children=children)


@app.route('/child/<int:child_id>')
@login_required
def child_history(child_id):
    # child_row = query_db(
    #     'SELECT * FROM children WHERE id=? AND user_id=?',
    #     (child_id, current_user.id), one=True
    # )
    child_row = (
        supabase.table("children")
        .select("*")
        .eq("id", child_id)
        .eq("user_id", current_user.id)
        .maybe_single()
        .execute()
    )
    if not child_row:
        return "Not found", 404

    child = dict(child_row.data)
    child['age_display'] = format_age(child['birthday'])
    birth_date = datetime.strptime(child['birthday'], '%Y-%m-%d').date()

    # record_rows = query_db('SELECT * FROM records WHERE child_id=? ORDER BY date DESC', (child_id,))
    record_rows = (
        supabase.table("records")
        .select("*")
        .eq("child_id", child_id)
        .order("date", desc=True)
        .execute()
    )
    records = []
    for rec in record_rows.data:
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
    # child_row = query_db(
    #     'SELECT * FROM children WHERE id=? AND user_id=?',
    #     (child_id, current_user.id), one=True
    # )
    child_row = (
        supabase.table("children")
        .select("*")
        .eq("id", child_id)
        .eq("user_id", current_user.id)
        .maybe_single()
        .execute()
    )
    if not child_row:
        return "Not found", 404

    height = float(request.form['height'])
    meas_date = request.form['date']

    # with sqlite3.connect('db/riseup.db') as conn:
    #     conn.execute('INSERT INTO records (child_id, height, date) VALUES (?,?,?)', (child_id, height, meas_date))
    #     conn.execute('UPDATE children SET height=? WHERE id=?', (height, child_id))
    response = (
        supabase.table("records")
        .insert({"child_id": child_id, "height": height, "date": meas_date})
        .execute()
    )

    response = (
        supabase.table("children")
        .select("height")
        .eq("id", child_id)
        .single()
        .execute()
    )

    latest_height = response.data["height"]
    if latest_height < height:
        response = (
            supabase.table("children")
            .update({"height": height})
            .eq("id", child_id)
            .execute()
        )

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

    # with sqlite3.connect('db/riseup.db') as conn:
    #     cursor = conn.cursor()
    #     cursor.execute(
    #         'INSERT INTO children (user_id, name, birthday, gender, height) VALUES (?,?,?,?,?)',
    #         (current_user.id, name, birthday, gender, height)
    #     )
    #     child_id = cursor.lastrowid
    #     cursor.execute(
    #         'INSERT INTO records (child_id, height, date) VALUES (?,?,?)',
    #         (child_id, height, date.today().strftime('%Y-%m-%d'))
    #     )
    response = (
        supabase.table("children")
        .insert({"user_id": current_user.id, "name": name, "birthday": birthday, "gender": gender, "height": height})
        .execute()
    )
    child_id = response.data[0]["id"]
    response = (
        supabase.table("records")
        .insert({"child_id": child_id, "height": height, "date": date.today().strftime('%Y-%m-%d')})
        .execute()    
    )

    percentile = compute_percentile(height, days // 7, days // 30, gender)
    return render_template('result.html', name=name, height=height, percentile=percentile, child_id=child_id)


@app.route('/chatbot', methods=['GET'])
@login_required
def chatbot():
    return render_template('chatbot.html')


@app.route('/chatbot/send', methods=['POST'])
@login_required
def chatbot_send():
    data = request.get_json()
    user_message = data.get('message', '').strip()
    history = data.get('history', [])

    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    # Fetch all children and their records to build the system prompt
    children_rows = supabase.table("children").select("*").eq("user_id", current_user.id).execute()

    children_context = []
    for child in children_rows.data:
        birth_date = datetime.strptime(child['birthday'], '%Y-%m-%d').date()
        records_rows = (
            supabase.table("records")
            .select("*")
            .eq("child_id", child['id'])
            .order("date", desc=False)
            .execute()
        )
        record_lines = []
        for rec in records_rows.data:
            try:
                rec_date = datetime.strptime(rec['date'], '%Y-%m-%d').date()
            except ValueError:
                rec_date = datetime.strptime(rec['date'], '%m-%d-%Y').date()
            days = (rec_date - birth_date).days
            pct = compute_percentile(rec['height'], days // 7, days // 30, child['gender']) or 'N/A'
            record_lines.append(f"    {rec_date}: {rec['height']} cm (WHO percentile: {pct})")

        age = format_age(child['birthday'])
        records_text = "\n".join(record_lines) if record_lines else "    No records yet."
        children_context.append(
            f"- {child['name']} ({child['gender']}, age {age}, born {child['birthday']})\n"
            f"  Height history:\n{records_text}"
        )

    system_prompt = (
        "You are a warm and knowledgeable child growth assistant. "
        "The parent has the following children registered in the RiseUp growth tracking app:\n\n"
        + ("\n\n".join(children_context) if children_context else "  (No children added yet.)")
        + "\n\nWHO percentiles show how the child's height compares to peers of the same age and gender. "
        "Answer questions about growth, explain what percentiles mean, and give general guidance. "
        "Always advise consulting a pediatrician for medical concerns."
    )

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    response = gemini.chat.completions.create(
        model="gemini-2.5-flash",
        messages=messages,
    )

    return jsonify({"reply": response.choices[0].message.content})

if __name__ == '__main__':
    # init_db()
    app.run(port=8080, host='127.0.0.1', debug=True)
