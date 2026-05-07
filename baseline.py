import pgeocode
import requests
import json
from datetime import datetime, timedelta

# Google Cloud imports
from google.cloud import tasks_v2
client = tasks_v2.CloudTasksClient()

PROJECT = "weatherscore-491006"
QUEUE = "update-tables"
LOCATION = "us-central1"
# insert_forecast_weather_data Cloud Function URL
insert_forecast_weather_data_url = "https://insert-weather-data-700897000697.us-central1.run.app"

def get_nws_historical_by_zip(zipcode, user_agent, country='us'):
    """
    Retrieves yesterday's high/low for a zipcode via NWS API.
    
    Args:
        zipcode (str): US Zipcode.
        user_agent (str): Your app name/email (required by NWS).
    """
    headers = {'User-Agent': user_agent}
    yesterday_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    # 1. Geocode Zipcode to Lat/Lon
    nomi = pgeocode.Nominatim(country)
    loc = nomi.query_postal_code(zipcode)
    if  loc['latitude'] is None or loc['longitude'] is None:
        return {"error": "Invalid zipcode"}
    
    lat, lon = loc['latitude'], loc['longitude']

    try:
        # 2. Find closest Station
        points_res = requests.get(f"https://api.weather.gov/points/{lat},{lon}", headers=headers)
        points_res.raise_for_status()
        stations_url = points_res.json()['properties']['observationStations']
        
        stations_res = requests.get(stations_url, headers=headers)
        stations_res.raise_for_status()
        station_id = stations_res.json()['features'][0]['properties']['stationIdentifier']

        # 3. Get Yesterday's Observations
        obs_url = f"https://api.weather.gov/stations/{station_id}/observations"
        params = {
            "start": f"{yesterday_date}T00:00:00Z",
            "end": f"{yesterday_date}T23:59:59Z"
        }
        
        obs_res = requests.get(obs_url, headers=headers, params=params)
        obs_res.raise_for_status()
        observations = obs_res.json()['features']

        # 4. Parse High/Low
        temps_c = [
            o['properties']['temperature']['value'] 
            for o in observations if o['properties']['temperature']['value'] is not None
        ]

        if not temps_c:
            return {"error": "No data available for this station yesterday."}

        # Conversion helper
        c_to_f = lambda c: (c * 9/5) + 32

        return {
            "day": yesterday_date,
            "high": int(round(c_to_f(max(temps_c)))),
            "low": int(round(c_to_f(min(temps_c))))
        }

    except Exception as e:
        return {"error": str(e)}
    
def insert_into_baseline_table(city, state, zip_code, date, source, high_temp, low_temp):
    parent = client.queue_path(PROJECT, LOCATION, QUEUE)

    payload = {
        "city": city,
        "state": state,
        "zip_code": zip_code,
        "date": date,
        "source": source,
        "high_temp": high_temp,
        "low_temp": low_temp,
        "table_type": "baseline"
    }

    # Construct the task.
    task = tasks_v2.Task(
        http_request=tasks_v2.HttpRequest(
            http_method=tasks_v2.HttpMethod.POST,
            url=insert_forecast_weather_data_url,
            headers={"Content-type": "application/json"},
            body=json.dumps(payload).encode(),
        )
    )

    client.create_task(parent=parent, task=task)

def update_baseline_table(city, state, zip_code):
    baseline = get_nws_historical_by_zip(zip_code)
    insert_into_baseline_table(city, state, zip_code, baseline.get("day"), "NWS", baseline.get("high"), baseline.get("low"))