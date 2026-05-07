from scraper import update_db_with_all_forecasts
from baseline import update_baseline_table
from flask import Flask, request

app = Flask(__name__)

@app.route("/worker", methods=["POST", "GET"])
def worker():
    """
    HTTP Cloud Function.
    """
    print("Entered worker function\n")
    data = request.get_json(silent=True) or {}
    print(data)

    zipcode = data.get("zipcode")
    city = data.get("city")
    state = data.get("state")

    update_db_with_all_forecasts(zipcode, city, state)
    update_baseline_table(city, state, zipcode)

if __name__ == "__main__":
    app.run(debug=True)