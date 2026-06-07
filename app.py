from flask import request, Flask, render_template, g
import pandas
from bisect import bisect_left
from datetime import date
import sqlite3
from datetime import datetime

app = Flask(__name__, template_folder='templates', static_folder="static")
df_b013 = pandas.read_excel("data/tab_lhfa_boys_p_0_13.xlsx") # 0 to 13 weeks
df_g013 = pandas.read_excel("data/tab_lhfa_girls_p_0_13.xlsx")
df_b02 = pandas.read_excel("data/tab_lhfa_boys_p_0_2.xlsx") # 0 to 24 months (inclusive)
df_g02 = pandas.read_excel("data/tab_lhfa_girls_p_0_2.xlsx")
df_b25 = pandas.read_excel("data/tab_lhfa_boys_p_2_5.xlsx") # 2 to 5 years (inclusive)
df_g25 = pandas.read_excel("data/tab_lhfa_girls_p_2_5.xlsx")
df_b520 = pandas.read_excel("data/hfa-boys-perc-who2007-exp.xlsx") # months 61 to 228 
df_g520 = pandas.read_excel("data/hfa-girls-perc-who2007-exp.xlsx")

# https://www.bcm.edu/bodycomplab/BMIapp/BMI-calculator-kids.html

children_ids = []

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect('db/riseup.db')
    return db

def get_df(weeks, months, gender):
    if weeks <= 13:
        if gender == 'male':
            return df_b013
        elif gender == 'female':
            return df_g013
    elif months <= 24:
        if gender == 'male':
            return df_b02
        elif gender == 'female':
            return df_g02
    elif 60 >= months > 24:
        if gender == 'male':
            return df_b25
        elif gender == 'female':
            return df_g25
    elif 228 >= months > 60:
        if gender == 'male':
            return df_b520
        elif gender == 'female':
            return df_g520
    return None

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

def get_age(birthday):
    return (date.today() - datetime.strftime(birthday, '%m-%d-%Y').date())//365


@app.route('/')
@app.route('/home')
def home():
    children_fetch = []

    with sqlite3.connect('db/riseup.db') as users:
        cursor = users.cursor()
        for id in children_ids:
            child = cursor.execute('SELECT * FROM Children WHERE id=?;', id)
            history = cursor.execute('SELECT * FROM Records WHERE child_id=?;', id)
            children_fetch.push_back({
                'name': child['name'], 
                'age': get_age(child['age']), 'gender': child['gender'], 'history': [
                
            ]})
            
        
    return render_template('home.html', children=children_fetch)
# form
@app.route('/form', methods=['POST', 'GET'])
def form():
    if request.method == 'GET':
        return render_template("form.html")
    elif request.method == 'POST':
        name = request.form['name']
        birthday = request.form['date']
        birth_date = date(*list(map(int, birthday.split('-'))))
        months = ((date.today() - birth_date).days)//30
        weeks = ((date.today() - birth_date).days)//7
        height = int(request.form['height'])
        gender = request.form['gender']

        with sqlite3.connect('db/riseup.db') as users:
            cursor = users.cursor()
            cursor.execute('INSERT INTO Children (name,birthday,gender,height) VALUES (?,?,?,?)', (name, birthday, gender, height))
            child_id = cursor.lastrowid
            children_ids.append(child_id)
            cursor.execute('INSERT INTO Records (child_id, height, date) VALUES (?,?,?)', (child_id, height, datetime.today().strftime('%m-%d-%Y')))

        print(weeks, months, gender)
        df = get_df(weeks, months, gender)
        heights = df[df["Month"] == months].iloc[0].values.tolist()[5:]
        i = bisect_left(heights, height)
        return render_template('result.html', percentile=df.columns[min(i + 5, 19)])


@app.route('/odd_even') 
def odd_even(): 
    return render_template('odd_even.html', number=3)

if __name__ == '__main__':
    app.run(port=8080, host='127.0.0.1')