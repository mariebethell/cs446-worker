from playwright.sync_api import sync_playwright

import time
import requests
import json
import os
import zipcodes
import pgeocode
from datetime import datetime

# Google Cloud imports
from google.cloud import tasks_v2
client = tasks_v2.CloudTasksClient()


PROJECT = "weatherscore-491006"
QUEUE = "update-tables"
LOCATION = "us-central1"
# insert_forecast_weather_data Cloud Function URL
insert_forecast_weather_data_url = "https://insert-weather-data-700897000697.us-central1.run.app"


### HELPER FUNCTIONS ###
def get_city_state_from_zipcode(zipcode: str):
    details = zipcodes.matching(zipcode)
    if details:
        city = details[0]['city']
        state = details[0]['state']
        return {'city': city, 'state': state}
    return None

def celsius_to_fahrenheit(c):
    return (c * 9/5) + 32

########################

### FORECAST RETRIEVAL FUNCTIONS ###
def get_wunderground_forecast(zipcode: str, state: str):
    """
    Get 10-day forecast from Wunderground.
    
    Args:
        zipcode (str): The postal code to search for.
        
    Returns:
        list[dict]: List of daily forecasts with keys {day, high, low}.
    """
    start = time.time()

    url = f"https://www.wunderground.com/forecast/us/{state.lower()}/{zipcode}"
    print(url)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        page = browser.new_page()

        page.goto(url, wait_until="domcontentloaded", timeout=15000)

        page.wait_for_selector(".temp-hi", timeout=10000)

        highs = page.locator(".temp-hi").all_text_contents()
        lows = page.locator(".temp-lo").all_text_contents()
        days = page.locator(".forecast-date .obs-date div").all_text_contents()

        forecast_list = []
        for d, h, l in zip(days, highs, lows):
            current_year = datetime.now().year
            full_date_str = f"{d}/{current_year}"
            date_obj = datetime.strptime(full_date_str, "%a %m/%d/%Y")
            
            d = date_obj.strftime("%Y-%m-%d")
            h = "".join(filter(str.isdigit, h))
            l = "".join(filter(str.isdigit, l))

            if h and l:
                forecast_list.append({
                    "day": d,
                    "high": h,
                    "low": l
                })

        browser.close()
        print("Time taken:", time.time() - start)

        return forecast_list

def get_accuweather_forecast(zipcode: str):
    """
    Retrieves a 10-day forecast from AccuWeather. Requires an API key.
    
    Args:
    zipcode (str): The postal code to search for.
        
    Returns:
        list[dict]: List of daily forecasts with keys {day, high, low}.
    """
    api_key = os.environ.get('ACCUWEATHER_API_KEY')

    base_url = "https://dataservice.accuweather.com"
    
    try:
        # Get location key from zipcode
        # Endpoint: /locations/v1/postalcodes/search
        loc_url = f"{base_url}/locations/v1/postalcodes/search"
        loc_params = {
            "apikey": api_key,
            "q": zipcode
        }
        
        loc_res = requests.get(loc_url, params=loc_params)
        loc_res.raise_for_status()
        loc_data = loc_res.json()
        
        if not loc_data:
            return {"error": "Location not found."}
            
        location_key = loc_data[0]['Key']

        # Get 10-Day Forecast
        # Endpoint: /forecasts/v1/daily/10day/{locationKey}
        fore_url = f"{base_url}/forecasts/v1/daily/10day/{location_key}"
        fore_params = {
            "apikey": api_key,
            "metric": "false"  # Set to True for Celsius
        }
        
        fore_res = requests.get(fore_url, params=fore_params)
        fore_res.raise_for_status()
        fore_data = fore_res.json()

        # Format result
        results = []
        for day in fore_data.get('DailyForecasts', []):
            results.append({
                "day": day['Date'].split('T')[0], # Extract SQL date (YYYY-MM-DD)
                "high": int(round(day['Temperature']['Maximum']['Value'])),
                "low": int(round(day['Temperature']['Minimum']['Value']))
            })
            
        return results

    except requests.exceptions.RequestException as e:
        return {"error": f"API request failed: {e}"}


def get_open_meteo_forecast(zipcode: str):
    """
    Retrieves a 10-day weather forecast from OpenMeteo for a given zipcode.
    
    Args:
        zipcode (str): The postal code to search for.
        country_code (str): ISO country code (default 'us').
        
    Returns:
        list[dict]: List of daily forecasts with keys {day, high, low}.
    """
    # Convert zipcode to coordinates
    nomi = pgeocode.Nominatim('us')
    location_data = nomi.query_postal_code(zipcode)
    
    if location_data['latitude'] is None or location_data['longitude'] is None:
        return {"error": f"Coordinates not found for zipcode: {zipcode}"}
    
    lat = location_data['latitude']
    lon = location_data['longitude']

    # Query Open-Meteo API
    # 'temperature_2m_max' and 'temperature_2m_min' are the standard daily variables
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": ["temperature_2m_max", "temperature_2m_min"],
        "forecast_days": 10,
        "timezone": "auto"
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        # Format the response into daily 
        daily_data = data.get('daily', {})
        forecast_list = []
        
        for date, high, low in zip(
            daily_data.get('time', []),
            daily_data.get('temperature_2m_max', []),
            daily_data.get('temperature_2m_min', [])
        ):
            forecast_list.append({
                "day": date,
                "high": round(celsius_to_fahrenheit(float(high))),
                "low": round(celsius_to_fahrenheit(float(low)))
            })
            
        return forecast_list

    except requests.exceptions.RequestException as e:
        return {"error": f"API request failed: {str(e)}"}


### DATABASE UPDATE FUNCTIONS ###
def insert_forecast_into_table(city, state, zip_code, date, source, high_temp, low_temp):
    parent = client.queue_path(PROJECT, LOCATION, QUEUE)

    payload = {
        "city": city,
        "state": state,
        "zip_code": zip_code,
        "date": date,
        "source": source,
        "high_temp": high_temp,
        "low_temp": low_temp,
        "table_type": "forecast"
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

def update_db_with_all_forecasts(city, state, zip_code):
    for forecast in get_wunderground_forecast(zip_code, state):
        insert_forecast_into_table(city, state, zip_code, forecast.get("day"), "wunderground", forecast.get("high"), forecast.get("low"))
    for forecast in get_accuweather_forecast(zip_code):
        insert_forecast_into_table(city, state, zip_code, forecast.get("day"), "accuweather", forecast.get("high"), forecast.get("low"))
    for forecast in get_open_meteo_forecast(zip_code):
        insert_forecast_into_table(city, state, zip_code, forecast.get("day"), "openmeteo", forecast.get("high"), forecast.get("low"))

####################################