from scraper import get_wunderground_forecast
from flask import Flask, request

app = Flask(__name__)

@app.route("/worker")
def worker():
    """
    HTTP Cloud Function.
    """
    data = request.get_json(silent=True) or {}
    print(data)
    zipcode = data["zipcode"]
    
    print(zipcode)

    get_wunderground_forecast(zipcode)

    return "test"

if __name__ == "__main__":
    app.run(debug=True)