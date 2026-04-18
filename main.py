from scraper import *
from flask import Flask, request

app = Flask(__name__)

@app.route("/worker", methods=["POST"])
def worker():
    """
    HTTP Cloud Function.
    """
    data = request.get_json(silent=True) or {}
    zipcode = data["zipcode"]
    
    print(zipcode)

    get_wunderground_forecast(zipcode)

    return "test"