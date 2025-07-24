# Gerekli kütüphaneleri içe aktarın
from flask import Flask, render_template, jsonify, request
import requests
import os
from datetime import datetime

# Flask uygulamasını başlat
app = Flask(__name__)

# OpenWeatherMap API anahtarını ortam değişkenlerinden veya varsayılan olarak al
API_KEY = os.environ.get("OPENWEATHER_API_KEY", "e00cc35bbd91c23fc447c254ae58e531")

# Ana sayfayı yükler
@app.route('/')
def index():
    return render_template('index.html')

# Bu fonksiyon, birden çok API çağrısı yaparak OneCall'ı simüle eder.
def fetch_weather_data_fallback(params):
    base_url = "https://api.openweathermap.org/data/2.5/"
    geocoding_url = "http://api.openweathermap.org/geo/1.0/direct"

    try:
        lat, lon, city_name = None, None, "Bilinmeyen Konum"

        # Adım 1: Koordinatları Al
        if 'q' in params:
            geo_params = {'q': params['q'], 'limit': 1, 'appid': API_KEY}
            geo_response = requests.get(geocoding_url, params=geo_params)
            geo_response.raise_for_status()
            geo_data = geo_response.json()
            if not geo_data:
                return jsonify({"error": f"'{params['q']}' şehri bulunamadı."}), 404
            lat, lon = geo_data[0]['lat'], geo_data[0]['lon']
            city_name = geo_data[0].get('local_names', {}).get('tr', geo_data[0]['name'])
        elif 'lat' in params and 'lon' in params:
            lat, lon = params['lat'], params['lon']
        else:
            return jsonify({"error": "Konum bilgisi gerekli."}), 400

        # API istekleri için ortak parametreler
        api_params = {
            'lat': lat, 'lon': lon, 'appid': API_KEY,
            'units': params.get('units', 'metric'), 'lang': params.get('lang', 'tr')
        }

        # Adım 2: Anlık Hava Durumu Verisini Çek
        current_weather_response = requests.get(f"{base_url}weather", params=api_params)
        current_weather_response.raise_for_status()
        current_data = current_weather_response.json()

        # Adım 3: 5 Günlük / 3 Saatlik Tahmin Verisini Çek
        forecast_response = requests.get(f"{base_url}forecast", params=api_params)
        forecast_response.raise_for_status()
        forecast_data = forecast_response.json()

        # Adım 4: Hava Kirliliği Verisini Çek
        air_pollution_response = requests.get(f"{base_url}air_pollution", params={'lat': lat, 'lon': lon, 'appid': API_KEY})
        air_pollution_response.raise_for_status()
        air_data = air_pollution_response.json()
        
        # Adım 5: UV İndeksi Verisini Çek
        uv_response = requests.get(f"{base_url}uvi", params={'lat': lat, 'lon': lon, 'appid': API_KEY})
        uv_response.raise_for_status()
        uv_data = uv_response.json()

        # Eğer konumdan arama yapıldıysa şehir adını anlık veriden al
        if 'q' not in params and city_name == "Bilinmeyen Konum":
             city_name = current_data.get('name', 'Bilinmeyen Konum')

        # Adım 6: Verileri OneCall formatına dönüştür
        
        # Anlık hava durumu verisi
        processed_current = {
            "dt": current_data.get('dt'),
            "sunrise": current_data.get('sys', {}).get('sunrise'),
            "sunset": current_data.get('sys', {}).get('sunset'),
            "temp": current_data.get('main', {}).get('temp'),
            "feels_like": current_data.get('main', {}).get('feels_like'),
            "pressure": current_data.get('main', {}).get('pressure'),
            "humidity": current_data.get('main', {}).get('humidity'),
            "uvi": uv_data.get('value', 0), # Gerçek UV verisini kullan
            "visibility": current_data.get('visibility'),
            "wind_speed": current_data.get('wind', {}).get('speed'),
            "weather": current_data.get('weather', [])
        }
        
        # Saatlik veri
        processed_hourly = []
        for item in forecast_data.get('list', []):
            new_item = item.copy()
            new_item['temp'] = item.get('main', {}).get('temp')
            processed_hourly.append(new_item)

        # Günlük veri
        daily_forecasts = {}
        for item in forecast_data.get('list', []):
            day_str = datetime.fromtimestamp(item['dt']).strftime('%Y-%m-%d')
            if day_str not in daily_forecasts:
                daily_forecasts[day_str] = {
                    'dt': item['dt'],
                    'temp': {'min': item['main']['temp_min'], 'max': item['main']['temp_max']},
                    'weather': item.get('weather', []),
                    'humidity': item['main']['humidity'],
                    'wind_speed': item['wind']['speed']
                }
            else:
                daily_forecasts[day_str]['temp']['min'] = min(daily_forecasts[day_str]['temp']['min'], item['main']['temp_min'])
                daily_forecasts[day_str]['temp']['max'] = max(daily_forecasts[day_str]['temp']['max'], item['main']['temp_max'])
                if datetime.fromtimestamp(item['dt']).hour == 12:
                    daily_forecasts[day_str]['weather'] = item.get('weather', [])

        processed_daily = list(daily_forecasts.values())

        # Tüm verileri ön yüzün beklediği yapıya birleştir
        response_data = {
            "oneCall": {
                "current": processed_current,
                "hourly": processed_hourly,
                "daily": processed_daily,
                "alerts": []
            },
            "airQuality": air_data,
            "cityName": city_name
        }
        return jsonify(response_data)

    except requests.exceptions.HTTPError as err:
        status_code = err.response.status_code if err.response else 500
        error_message = f"Veri alınamadı (HTTP {status_code}). API anahtarınızı veya şehir adını kontrol edin."
        return jsonify({"error": error_message, "status_code": status_code}), status_code
    except requests.exceptions.RequestException as err:
        return jsonify({"error": "Ağ hatası oluştu. Sunucuya bağlanılamadı.", "details": str(err)}), 500
    except (IndexError, KeyError) as err:
        return jsonify({"error": "API'den gelen veri ayrıştırılamadı.", "details": str(err)}), 500
    except Exception as err:
        import traceback
        print(traceback.format_exc())
        return jsonify({"error": "Beklenmedik bir sunucu hatası oluştu.", "details": str(err)}), 500

# Endpoint'ler
@app.route('/weather/city/<string:city_name>')
def get_weather_by_city(city_name):
    units = request.args.get('units', 'metric')
    params = {'q': city_name, 'units': units, 'lang': 'tr'}
    return fetch_weather_data_fallback(params)

@app.route('/weather/coords')
def get_weather_by_coords():
    lat = request.args.get('lat')
    lon = request.args.get('lon')
    units = request.args.get('units', 'metric')
    if not lat or not lon:
        return jsonify({"error": "Eksik koordinat bilgisi."}), 400
    
    params = {'lat': lat, 'lon': lon, 'units': units, 'lang': 'tr'}
    return fetch_weather_data_fallback(params)

# Uygulamayı çalıştır
if __name__ == '__main__':
    app.run(debug=True)
