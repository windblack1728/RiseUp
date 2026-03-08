from flask import request, Flask, render_template
import pandas
from bisect import bisect_left
from datetime import date

app = Flask(__name__, template_folder='templates', static_folder="static")
df = pandas.read_excel("data/tab_lhfa_boys_p_0_2.xlsx")


@app.route('/')
@app.route('/index/<height>/<agemonths>')
def index(height, agemonths):
    height = int(height)
    agemonths = int(agemonths)
    heights = df[df["Month"] == agemonths].iloc[0].values.tolist()[5:]
    i = bisect_left(heights, height)
    return "Your child's percentile:" + df.columns[min(i + 5, 19)]


@app.route('/form', methods=['POST', 'GET'])
def form():
    if request.method == 'GET':
        return render_template("form.html")
    elif request.method == 'POST':
        birth_date = date(*list(map(int, request.form['date'].split('-'))))
        months = ((date.today() - birth_date).days)//30
        height = int(request.form['height'])
        heights = df[df["Month"] == months].iloc[0].values.tolist()[5:]
        i = bisect_left(heights, height)
        return "Your child's percentile:" + df.columns[min(i + 5, 19)]


if __name__ == '__main__':
    app.run(port=8080, host='127.0.0.1')