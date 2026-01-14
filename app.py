from dotenv import load_dotenv
load_dotenv()
from flask import Flask, render_template, jsonify, request
import requests
import os
import math

app = Flask(__name__)

API_KEY = os.environ.get("OPENWEATHER_API_KEY")

# API request timeout in seconds
REQUEST_TIMEOUT = 10



# calculate km from coordinates
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


# Get neighborhood/county/city name from coordinates using Nominatim
def get_location_name_from_coords(lat, lon):
    try:
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {
            'lat': lat,
            'lon': lon,
            'format': 'json',
            'addressdetails': 1
        }
        headers = {
            'User-Agent': 'weather-app/1.0'  # Required by Nominatim
        }

        response = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()

        address = data.get("address", {})
        mahalle = address.get("neighbourhood") or address.get("suburb")
        ilce = address.get("county")
        sehir = address.get("city") or address.get("town") or address.get("village")

        return ", ".join(filter(None, [mahalle, ilce, sehir])) or "Konum"
    except Exception as e:
        # Return simple location name on error instead of technical details
        return "Konum"


# Main weather data fetching function
def fetch_weather_data(params):
    if not API_KEY:
        return jsonify({"error": "API anahtarı yapılandırılmamış. OPENWEATHER_API_KEY ortam değişkenini ayarlayın."}), 500
    
    geocoding_url = "https://api.openweathermap.org/geo/1.0/direct"
    one_call_url = "https://api.openweathermap.org/data/3.0/onecall"
    air_pollution_url = "https://api.openweathermap.org/data/2.5/air_pollution"

    try:
        if 'q' in params:
            geo_params = {'q': params['q'], 'limit': 1, 'appid': API_KEY}
            geo_response = requests.get(geocoding_url, params=geo_params, timeout=REQUEST_TIMEOUT)
            geo_response.raise_for_status()
            geo_data = geo_response.json()
            if not geo_data:
                return jsonify({"error": f"'{params['q']}' yeri bulunamadı."}), 404
            lat, lon = geo_data[0]['lat'], geo_data[0]['lon']
            city_name = geo_data[0].get('local_names', {}).get('tr', geo_data[0]['name'])

        elif 'lat' in params and 'lon' in params:
            lat = float(params['lat'])
            lon = float(params['lon'])
            city_name = get_location_name_from_coords(lat, lon)
        else:
            return jsonify({"error": "Konum bilgisi gerekli (q ya da lat/lon)."}), 400

    except (KeyError, ValueError):
        return jsonify({"error": "Geçersiz konum verisi."}), 400
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Geocoding API hatası: {str(e)}"}), 502

    # Weather and air pollution API calls
    one_call_params = {
        'lat': lat,
        'lon': lon,
        'appid': API_KEY,
        'units': params.get('units', 'metric'),
        'lang': 'tr',
        'exclude': 'minutely,alerts'
    }

    air_params = {'lat': lat, 'lon': lon, 'appid': API_KEY}

    try:
        one_call_resp = requests.get(one_call_url, params=one_call_params, timeout=REQUEST_TIMEOUT)
        one_call_resp.raise_for_status()
        weather_data = one_call_resp.json()

        air_resp = requests.get(air_pollution_url, params=air_params, timeout=REQUEST_TIMEOUT)
        air_resp.raise_for_status()
        air_data = air_resp.json()
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Hava durumu API'sine ulaşılamadı: {e}"}), 502

    return jsonify({
        "cityName": city_name,
        "oneCall": weather_data,
        "airQuality": air_data
    })


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/weather/coords')
def get_weather_by_coords():
    lat = request.args.get('lat')
    lon = request.args.get('lon')
    units = request.args.get('units', 'metric')

    if not lat or not lon:
        return jsonify({"error": "Eksik koordinat bilgisi."}), 400

    params = {'lat': lat, 'lon': lon, 'units': units}
    return fetch_weather_data(params)


@app.route('/weather/city/<path:city>')
def get_weather_by_city(city):
    return fetch_weather_data({
        'q': city,
        'units': request.args.get('units', 'metric')
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
