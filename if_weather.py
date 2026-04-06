import datetime as dt
import requests
from unified_config import get_config, set_config
import threading
import time
import json
import string
from loguru import logger

class WeatherHandler:
    # API URLs
    BASE_URL = "http://api.openweathermap.org/data/2.5/weather?"
    FORECAST_URL = "http://api.openweathermap.org/data/2.5/forecast?"

    def __init__(self, device_id=None):
        """Initialize WeatherHandler instance"""
        self.device_id = device_id



    def get_weather_forecast(self, city_name, lang="zh_cn"):
        """
        Retrieve weather forecast data

        Args:
            city_name: Name of the city
            lang: Language (zh_cn for Chinese, en for English)

        Returns:
            dict: Processed weather forecast data
        """
        try:
            # Get API key from config
            api_key = get_config("weather.api_key")
            if not api_key:
                logger.error("Weather API key is not configured")
                return None

            if not city_name:
                logger.error("City name is empty")
                return None

            # Construct API URL
            complete_url = self.FORECAST_URL + "appid=" + api_key + "&q=" + city_name + "&lang=" + lang
            logger.debug(f"Requesting weather API: {complete_url.replace(api_key, '***')}")

            # Send request
            response = requests.get(complete_url, timeout=10)

            # Check HTTP status code
            if response.status_code != 200:
                logger.error(f"Weather API request failed, status code: {response.status_code}, response: {response.text}")
                return None

            # Parse JSON response
            data = response.json()

            if data.get("cod") == "200":  # API returned success
                logger.debug(f"Successfully retrieved weather forecast data for {city_name}")
                # Process into structured forecast data
                forecast_data = self.process_forecast_data(data)
                return forecast_data
            else:
                error_msg = data.get('message', 'Unknown error')
                logger.error(f"Unable to retrieve weather forecast for {city_name}: {error_msg}")
                # Log more detailed error information
                if "city not found" in error_msg.lower():
                    logger.error(f"City '{city_name}' not found, please check if the city name is correct")
                elif "invalid api key" in error_msg.lower():
                    logger.error("Invalid API key, please check the configuration")
                return None
        except requests.exceptions.Timeout:
            logger.error(f"Timeout while retrieving weather forecast for {city_name}")
            return None
        except requests.exceptions.ConnectionError:
            logger.error(f"Failed to connect to the weather API server, please check your network connection")
            return None
        except json.JSONDecodeError:
            logger.error(f"Failed to parse weather API response, response is not valid JSON format")
            return None
        except Exception as e:
            logger.error(f"Error occurred while retrieving weather forecast: {e}")
            return None

    def process_forecast_data(self, raw_data):
        """
        Process raw weather forecast data into structured format

        Args:
            raw_data: Raw response from OpenWeatherMap API

        Returns:
            dict: Structured weather forecast data organized by date
        """
        forecast_items = raw_data["list"]
        forecast_by_day = {}

        # Get basic city information
        city_info = {
            "name": raw_data["city"]["name"],
            "country": raw_data["city"]["country"],
            "timezone": raw_data["city"]["timezone"],
            "sunrise": dt.datetime.fromtimestamp(raw_data["city"]["sunrise"]),
            "sunset": dt.datetime.fromtimestamp(raw_data["city"]["sunset"])
        }

        for item in forecast_items:
            # Convert timestamp to datetime object
            timestamp = dt.datetime.fromtimestamp(item["dt"])
            date_key = timestamp.strftime("%Y-%m-%d")

            # Extract weather information for the current period
            weather_data = {
                "timestamp": timestamp,
                "time": timestamp.strftime("%H:%M"),
                "temperature_celsius": round(item["main"]["temp"] - 273.15, 2),
                "feels_like_celsius": round(item["main"]["feels_like"] - 273.15, 2),
                "humidity": item["main"]["humidity"],
                "pressure": item["main"]["pressure"],
                "weather_description": item["weather"][0]["description"],
                "weather_id": item["weather"][0]["id"],
                "weather_icon": item["weather"][0]["icon"],
                "clouds": item["clouds"]["all"],
                "wind_speed": item["wind"]["speed"],
                "wind_direction": item["wind"]["deg"],
                "rain": item.get("rain", {}).get("3h", 0),  # 3-hour rainfall, may not exist
                "probability": item.get("pop", 0) * 100,  # Precipitation probability (0-1 converted to percentage)
            }

            # Organize data by date
            if date_key not in forecast_by_day:
                forecast_by_day[date_key] = []

            forecast_by_day[date_key].append(weather_data)

        # Retain only three days of data
        now = dt.datetime.now()
        forecast_days = []
        for i in range(4):
            day = (now + dt.timedelta(days=i)).strftime("%Y-%m-%d")
            forecast_days.append(day)

        # Filter to retain only four days of data
        forecast_by_day = {k: v for k, v in forecast_by_day.items() if k in forecast_days}

        # Generate final structure
        result = {
            "city": city_info,
            "forecast": forecast_by_day,
            "updated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        return result

    def get_daily_summary(self, forecast_data):
        """
        Generate daily weather summary

        Args:
            forecast_data: Processed forecast data from self.process_forecast_data()

        Returns:
            dict: Daily summary containing minimum/maximum temperature, overall description, etc.
        """
        daily_summary = {}

        for date, periods in forecast_data["forecast"].items():
            # Initialize daily summary data
            temps = [p["temperature_celsius"] for p in periods]
            rain_amounts = [p["rain"] for p in periods]
            descriptions = [p["weather_description"] for p in periods]

            # Count the most frequent weather description
            from collections import Counter
            description_counts = Counter(descriptions)
            most_common_desc = description_counts.most_common(1)[0][0]

            # Get the ID of the most common weather
            weather_ids = [p["weather_id"] for p in periods if p["weather_description"] == most_common_desc]
            most_common_id = weather_ids[0] if weather_ids else 800  # Default to clear weather

            # Calculate total rainfall
            total_rain = sum(rain_amounts)

            # Calculate precipitation probability
            max_probability = max(p["probability"] for p in periods)

            daily_summary[date] = {
                "min_temp": round(min(temps), 1),
                "max_temp": round(max(temps), 1),
                "avg_temp": round(sum(temps) / len(temps), 1),
                "description": most_common_desc,
                "weather_id": most_common_id,
                "rain_amount": round(total_rain, 1),
                "rain_probability": round(max_probability),
                "periods": len(periods),
                "humidity": round(sum(p["humidity"] for p in periods) / len(periods)),
                "wind_speed": round(sum(p["wind_speed"] for p in periods) / len(periods), 1)
            }

        return daily_summary

    def update_weather_data(self):
        """
        Update weather data in the configuration

        This function retrieves the latest weather data and updates the weather section in the config
        """

        try:
            # Get city name
            location = get_config("weather.location", device_id=self.device_id)
            if not location:
                logger.error(f"Weather location is not configured, please set weather.location in the configuration for device {self.device_id}")
                return False

            logger.info(f"Retrieving weather data for {location}...")

            # Weather forecast with Chinese descriptions
            zh_forecast = self.get_weather_forecast(location, "zh_cn")
            if not zh_forecast:
                logger.error(f"Unable to retrieve Chinese weather forecast data for {location}")
                return False

            # Weather forecast with English descriptions (used only for English descriptions)
            en_forecast = self.get_weather_forecast(location, "en")
            if not en_forecast:
                logger.warning(f"Unable to retrieve English weather forecast data for {location}, using Chinese data instead")
                en_forecast = zh_forecast  # Fallback, use Chinese data

            # Check forecast data structure
            if not zh_forecast.get("forecast") or not en_forecast.get("forecast"):
                logger.error("Incomplete weather forecast data structure")
                return False

            # Process into daily summary
            try:
                zh_summary = self.get_daily_summary(zh_forecast)
                en_summary = self.get_daily_summary(en_forecast)

                if not zh_summary or not en_summary:
                    logger.error("Unable to generate weather summary")
                    return False

                logger.debug(f"Successfully generated weather summary, containing data for {len(zh_summary)} days")
            except Exception as e:
                logger.error(f"Error occurred while processing weather summary: {e}")
                return False

            # Get basic city information
            city_info = zh_forecast.get("city", {})
            if not city_info:
                logger.warning("Unable to retrieve basic city information")

            # Prepare weather data update
            days_data = []  # Will contain weather data

            # Get current date
            today = dt.datetime.now().strftime("%Y-%m-%d")
            logger.debug(f"Current date: {today}")

            # Add weather data
            date_objects = []
            for i in range(4):
                date_obj = dt.datetime.now() + dt.timedelta(days=i)
                date_objects.append(date_obj.strftime("%Y-%m-%d"))

            # Get available dates from summary
            available_dates = sorted(list(zh_summary.keys()))
            logger.debug(f"Available dates: {available_dates}")

            # For each desired date, add if available, otherwise skip
            for date in date_objects:
                if date not in available_dates:
                    logger.warning(f"Weather data for date {date} is not available")
                    continue

                zh_day_data = zh_summary[date]
                en_day_data = en_summary[date]

                # Construct weather data for one day
                day_data = {
                    "date": date,
                    "min_temp": zh_day_data["min_temp"],
                    "max_temp": zh_day_data["max_temp"],
                    "avg_temp": zh_day_data["avg_temp"],
                    "description_zh": zh_day_data["description"],
                    "description_en": en_day_data["description"],
                    "weather_id": zh_day_data["weather_id"],
                    "rain_amount": zh_day_data["rain_amount"],
                    "rain_probability": zh_day_data["rain_probability"],
                    "humidity": zh_day_data["humidity"],
                    "wind_speed": zh_day_data["wind_speed"]
                }

                # If today, add more detailed current weather information
                if date == today:
                    try:
                        # Find the nearest time period as current weather
                        now_hour = dt.datetime.now().hour
                        current_period = None

                        for period in zh_forecast["forecast"][date]:
                            period_hour = period["timestamp"].hour
                            if current_period is None or abs(period_hour - now_hour) < abs(current_period["timestamp"].hour - now_hour):
                                current_period = period

                        if not current_period:
                            logger.warning(f"Unable to find weather data near current time {now_hour}:00")
                            # Use the first period as fallback
                            if zh_forecast["forecast"][date]:
                                current_period = zh_forecast["forecast"][date][0]
                                logger.debug(f"Using the first available period {current_period['time']} as current weather")
                            else:
                                logger.error(f"No available weather period data for date {date}")
                                continue

                        # Find corresponding English description
                        en_description = ""
                        for period in en_forecast["forecast"].get(date, []):
                            if abs(period["timestamp"].hour - current_period["timestamp"].hour) < 1:
                                en_description = period["weather_description"]
                                break

                        # Add detailed information for the current period to today's data
                        day_data.update({
                            "current_temperature": current_period["temperature_celsius"],
                            "current_feels_like": current_period["feels_like_celsius"],
                            "current_humidity": current_period["humidity"],
                            "current_description_zh": current_period["weather_description"],
                            "current_description_en": en_description or current_period["weather_description"],
                            "current_wind_speed": current_period["wind_speed"],
                            "current_wind_direction": current_period["wind_direction"],
                            "current_clouds": current_period["clouds"],
                            "current_probability": current_period["probability"],
                        })

                        logger.debug(f"Current weather: {current_period['weather_description']}, {current_period['temperature_celsius']}°C")
                    except Exception as e:
                        logger.error(f"Error occurred while processing current weather data: {e}")
                        # Do not add current weather data, but retain date data

                days_data.append(day_data)
                logger.debug(f"Added weather data for {date}")

            # Check if valid weather data was retrieved
            if not days_data or len(days_data) == 0:
                logger.error("No valid weather data retrieved")
                return False

            # Check if today's weather data contains necessary fields
            today_data = days_data[0]
            current_desc = today_data.get('current_description_zh')
            current_temp = today_data.get('current_temperature')

            if current_desc is None or current_desc == 'Unknown' or current_temp is None:
                logger.warning(f"Incomplete weather data: description={current_desc}, temperature={current_temp}")
                # If data is incomplete but at least some data exists, still update but return a warning
                if len(days_data) > 0 and (today_data.get('description_zh') or today_data.get('min_temp')):
                    set_config("weather.last_updated", dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), device_id=self.device_id)
                    set_config("weather.days", days_data, device_id=self.device_id)
                    logger.warning(f"Weather data updated but incomplete: {current_desc or 'Unknown'}, {current_temp or 0}°C")
                    return True
                else:
                    logger.error("Severely incomplete weather data, update abandoned")
                    return False

            # Update weather data in the configuration
            set_config("weather.last_updated", dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), device_id=self.device_id)
            set_config("weather.days", days_data, device_id=self.device_id)

            logger.success(f"Weather data updated: {current_desc}, {current_temp}°C")
            return True

        except Exception as e:
            logger.error(f"Failed to update weather data: {e}")
            return False

    def get_current_weather(self):
        """
        Retrieve current weather data from the configuration

        Returns:
            dict: Current weather data from the configuration
            None: If weather data is unavailable or expired
        """

        # Check if weather data exists and is not expired
        last_updated = get_config("weather.last_updated", "", device_id=self.device_id)
        if not last_updated:
            logger.warning("Weather data has not been initialized")
            self.update_weather_data()  # Attempt to update immediately
            # Check again if the update was successful
            if not get_config("weather.last_updated", device_id=self.device_id):
                return None

        # Parse the last update time
        try:
            last_time = dt.datetime.strptime(last_updated, "%Y-%m-%d %H:%M:%S")
            now = dt.datetime.now()

            # If data is older than 4 hours, consider it expired
            if (now - last_time).total_seconds() > 14400:  # 4 hours
                logger.warning("Weather data expired, updating...")
                self.update_weather_data()  # Update immediately
        except Exception:
            logger.error("Unable to parse weather data update time")

        # Build the weather data dictionary
        weather_data = {
            "last_updated": get_config("weather.last_updated", "", device_id=self.device_id),
            "location": get_config("weather.location", "", device_id=self.device_id),
            "days": get_config("weather.days", [], device_id=self.device_id)
        }

        return weather_data

    def format_forecast_response(self, days=3, is_chinese=True):
        """
        Format weather forecast response

        Args:
            days: Number of days to include (1-4)
            is_chinese: Whether to use Chinese format

        Returns:
            str: Formatted weather forecast response
        """
        # Retrieve weather data
        weather_data = self.get_current_weather()
        if not weather_data or not weather_data.get("days") or len(weather_data["days"]) == 0:
            return "无法获取天气预报数据" if is_chinese else "Unable to fetch forecast data"

        # Limit days to 1-4
        days = max(1, min(days, 4))

        # Retrieve city name
        city_name = weather_data.get("city_name", get_config("weather.location", device_id=self.device_id))

        # Build response
        if is_chinese:
            response = f"**{city_name} 未来{days}天天气预报**\n\n"

            for i, day_data in enumerate(weather_data["days"][:days]):
                date_obj = dt.datetime.strptime(day_data["date"], "%Y-%m-%d")
                weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
                weekday = weekday_names[date_obj.weekday()]

                # 当日或未来
                date_prefix = "今天" if i == 0 else "明天" if i == 1 else "后天" if i == 2 else "大后天"

                response += f"**{date_prefix}（{weekday}）**: {day_data['description_zh']}\n"
                response += f"温度: {day_data['min_temp']}°C ~ {day_data['max_temp']}°C，"

                if day_data['rain_amount'] > 0:
                    response += f"预计降水量: {day_data['rain_amount']}mm，"

                response += f"降水概率: {day_data['rain_probability']}%\n\n"
        else:
            response = f"**{city_name} {days}-Day Weather Forecast**\n\n"

            for i, day_data in enumerate(weather_data["days"][:days]):
                date_obj = dt.datetime.strptime(day_data["date"], "%Y-%m-%d")
                weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                weekday = weekday_names[date_obj.weekday()]

                # Today or future
                date_prefix = "Today" if i == 0 else "Tomorrow" if i == 1 else "Day After Tomorrow" if i == 2 else "In Four Days"

                response += f"**{date_prefix} ({weekday})**: {day_data['description_en']}\n"
                response += f"Temperature: {day_data['min_temp']}°C ~ {day_data['max_temp']}°C, "

                if day_data['rain_amount'] > 0:
                    response += f"Expected rainfall: {day_data['rain_amount']}mm, "

                response += f"Precipitation chance: {day_data['rain_probability']}%\n\n"

        # Add update time
        updated_time = weather_data["last_updated"]
        response += f"_数据更新时间: {updated_time}_" if is_chinese else f"_Data updated: {updated_time}_"

        return response

    def check_weather_forecast_query(self, query: str) -> tuple[str, bool]:
        """
        Check if the query requests a weather forecast and respond accordingly

        Args:
            query: User's query text

        Returns:
            tuple: (Response message, Boolean indicating whether the query was processed)
        """
        # Determine language
        is_chinese = any('\u4e00' <= char <= '\u9fff' for char in query)

        # 预测相关的关键词
        forecast_keywords = {
            'chinese': [
                '天气预报', '未来天气', '明天天气', '后天天气', '未来几天', '天气预测',
                '未来', '预测', '预报', '趋势', '会不会下雨', '明天会下雨吗',
                '天气怎么样', '未来天气怎么样', '明天天气怎么样', '下周天气',
                '这周天气', '今后', '接下来', '往后', '几天', '之后',
                '天气趋势', '气象预报', '未来几天天气', '接下来几天'
            ],
            'english': [
                'weather forecast', 'future weather', 'tomorrow weather',
                'weather prediction', 'forecast', 'weather trend',
                'will it rain', 'next few days', 'upcoming weather',
                'next week weather', 'weather next week', 'weather tomorrow',
                'upcoming days', 'weather trend', 'following days',
                'days ahead', 'future days', 'weather outlook'
            ]
        }

        # 检测相关关键词
        keywords = forecast_keywords['chinese'] if is_chinese else forecast_keywords['english']
        if not any(keyword in query.lower() for keyword in keywords):
            return "", False

        # 检测查询的天数
        days = 3  # 默认3天
        day_patterns = {
            'chinese': {'一': 1, '二': 2, '三': 3, '1': 1, '2': 2, '3': 3},
            'english': {'one': 1, 'two': 2, 'three': 3, '1': 1, '2': 2, '3': 3}
        }

        patterns = day_patterns['chinese'] if is_chinese else day_patterns['english']
        for pattern, value in patterns.items():
            if pattern in query.lower():
                days = value
                break

        try:
            # 确保天气数据最新
            weather_data = self.get_current_weather()
            if not weather_data or not weather_data.get("days"):
                self.update_weather_data()

            # 格式化响应
            response = self.format_forecast_response(days, is_chinese)
            return response, True

        except Exception as e:
            logger.error(f"Error processing weather forecast query: {e}")
            return "Error getting weather forecast" if not is_chinese else "获取天气预报时出错", True

    def check_weather_query(self, query: str) -> str:
        """
        Handle all weather-related queries using full sentence matching, retrieving current data from today_data instead of the current field
        """
        # Preprocess the text
        processed_text, lang = self.preprocess_text(query)

        # Retrieve weather data
        weather_data = self.get_current_weather()
        if not weather_data or not weather_data.get("days") or len(weather_data["days"]) < 3:
            return "抱歉，无法获取天气信息" if lang == 'chinese' else "Sorry, unable to get weather information"

        # Retrieve three days of weather data
        today_data = weather_data["days"][0]
        tomorrow_data = weather_data["days"][1] if len(weather_data["days"]) > 1 else None
        day_after_tomorrow_data = weather_data["days"][2] if len(weather_data["days"]) > 2 else None

        # Define full query sentence patterns using a nested dictionary structure
        weather_patterns = {
            'chinese': {
                'weather': {
                    'today': [
                        '天气怎么样', '外面天气怎么样', '外面的天气怎么样', '今天天气怎么样',
                        '天气如何', '现在天气如何', '今天天气如何', '外面天气如何',
                        '外面的天气如何', '现在外面天气如何', '今天外面天气如何',
                        '现在外面的天气如何', '今天外面的天气如何', '现在的天气',
                        '当前天气', '今天的天气', '查询天气', '现在怎么样',
                        '天气情况', '今日天气', '请告诉我现在的天气情况', '告诉我现在的天气情况',
                        '今天的气候如何', '现在的气候怎么样', '当前天气状况如何', '现在天气状况如何',
                        '今天天气状况如何', '播报天气', '播报今天的天气', '播报现在的天气',
                        '播报今天的天气状况', '播报现在的天气情况', '播报当前的天气情况',
                        '今天的天气如何', '现在的天气如何', '今天的天气状况如何',
                        '现在的天气状况如何', '今天的天气趋势如何',
                    ],
                    'tomorrow': [
                        '明天天气怎么样', '明天天气如何', '明天的天气', '明天的天气如何',
                        '明天的天气状况如何', '明天天气状况如何', '明天的气候如何',
                        '播报明天的天气', '播报明天的天气状况', '明天天气预报',
                        '明天外面天气怎么样', '明天外面的天气如何', '请告诉我明天的天气情况',
                        '告诉我明天的天气情况', '明天气象情况', '明天的天气趋势如何',
                        '明天是什么天气', '明天会是什么天气', '明天是什么样的天气'
                    ],
                    'day_after_tomorrow': [
                        '后天天气怎么样', '后天天气如何', '后天的天气', '后天的天气如何',
                        '后天的天气状况如何', '后天天气状况如何', '后天的气候如何',
                        '播报后天的天气', '播报后天的天气状况', '后天天气预报',
                        '后天外面天气怎么样', '后天外面的天气如何', '请告诉我后天的天气情况',
                        '告诉我后天的天气情况', '后天气象情况', '后天的天气趋势如何',
                        '后天是什么天气', '后天会是什么天气', '后天是什么样的天气'
                    ]
                },
                'temperature': {
                    'today': [
                        '温度多少', '气温多少', '今天温度多少', '今天气温多少', '现在温度多少',
                        '现在气温多少', '今天的温度多少', '今天的气温多少', '现在的温度多少',
                        '现在的气温多少', '现在温度', '当前温度', '现在的温度', '当前的温度',
                        '现在多少度', '今天温度', '今天气温', '现在几度', '温度如何',
                        '请报一下温度', '请报一下今天的温度', '请报一下现在的温度', '请报一下当前的温度',
                        '现在几度了', '请告诉我当前的温度', '室外温度是多少', '目前气温是多少',
                        '现在的温度是多少度', '当前体感温度是多少', '体感温度多少',
                        '现在的气温高还是低', '今天是热天还是冷天', '今天天气热吗', '今天天气冷吗',
                        '当前是热还是冷', '现在气温适中吗', '当前气温如何', '室外温度如何',
                        '今天几度', '室外体感温度如何', '今天会被热死吗', '今天会被冷死吗',
                        '今天会热死吗', '今天会冷死吗', '今天是热到暴汗还是冷到发抖',
                    ],
                    'tomorrow': [
                        '明天温度多少', '明天气温多少', '明天的温度多少', '明天的气温多少',
                        '明天温度', '明天气温', '明天多少度', '明天几度', '明天温度如何',
                        '请报一下明天的温度', '明天的温度是多少度', '明天的体感温度是多少',
                        '明天的气温高还是低', '明天是热天还是冷天', '明天天气热吗', '明天天气冷吗',
                        '明天气温适中吗', '明天气温如何', '明天会被热死吗', '明天会被冷死吗'
                    ],
                    'day_after_tomorrow': [
                        '后天温度多少', '后天气温多少', '后天的温度多少', '后天的气温多少',
                        '后天温度', '后天气温', '后天多少度', '后天几度', '后天温度如何',
                        '请报一下后天的温度', '后天的温度是多少度', '后天的体感温度是多少',
                        '后天的气温高还是低', '后天是热天还是冷天', '后天天气热吗', '后天天气冷吗',
                        '后天气温适中吗', '后天气温如何', '后天会被热死吗', '后天会被冷死吗'
                    ]
                },
                'humidity': {
                    'today': [
                        '现在的湿度是多少', '当前湿度是多少', '空气湿度是多少', '请告诉我湿度情况',
                        '湿度多少', '空气湿度', '现在湿度', '当前湿度', '湿度如何', '今天湿度',
                        '现在的空气湿度是多少', '当前湿度如何', '体感湿度如何',
                    ],
                    'tomorrow': [
                        '明天的湿度是多少', '明天空气湿度是多少', '请告诉我明天的湿度情况',
                        '明天湿度多少', '明天的空气湿度', '明天湿度如何'
                    ],
                    'day_after_tomorrow': [
                        '后天的湿度是多少', '后天空气湿度是多少', '请告诉我后天的湿度情况',
                        '后天湿度多少', '后天的空气湿度', '后天湿度如何'
                    ]
                }
            },
            'english': {
                'weather': {
                    'today': [
                        'hows the weather', 'whats the weather like', 'current weather',
                        'weather today', 'weather condition', 'weather report',
                        'hows the weather right now', 'what is the current weather',
                        'tell me the weather conditions', 'how is it outside',
                        'is the weather good today', 'outside weather', 'today weather',
                        'todays forecast'
                    ],
                    'tomorrow': [
                        'weather tomorrow', 'tomorrows weather', 'tomorrows forecast',
                        'how will the weather be tomorrow', 'whats the weather like tomorrow',
                        'tell me the weather for tomorrow', 'will it be nice tomorrow',
                        'what is tomorrows weather forecast', 'forecast for tomorrow',
                        'tomorrows weather conditions', 'weather report for tomorrow',
                        'weather outlook tomorrow'
                    ],
                    'day_after_tomorrow': [
                        'day after tomorrow weather', 'weather day after tomorrow',
                        'forecast for day after tomorrow', 'what will the weather be day after tomorrow',
                        'tell me the weather for day after tomorrow', 'weather report for day after tomorrow',
                        'day after tomorrows forecast', 'day after tomorrows weather conditions',
                        'weather outlook for day after tomorrow'
                    ]
                },
                'temperature': {
                    'today': [
                        'how hot is it', 'how cold is it', 'current temperature',
                        'whats the temperature', 'temperature now', 'how many degrees',
                        'what is the temperature now', 'tell me the current temperature',
                        'whats the outdoor temperature', 'what is the temperature',
                        'please report the temperature', 'outside temperature',
                        'is it hot or cold today', 'is it too hot or too cold',
                        'what is the current temperature reading', 'how is the temperature right now',
                        'what is the real feel temperature', 'is it cold or hot',
                        'can you tell me the temperature', 'what is the temperature outside',
                    ],
                    'tomorrow': [
                        'tomorrow temperature', 'temperature tomorrow', 'how hot will it be tomorrow',
                        'how cold will it be tomorrow', 'tomorrows temperature',
                        'tell me the temperature for tomorrow', 'what temperature tomorrow',
                        'degrees tomorrow', 'will it be hot tomorrow', 'will it be cold tomorrow',
                        'temperature forecast for tomorrow', 'how many degrees tomorrow'
                    ],
                    'day_after_tomorrow': [
                        'day after tomorrow temperature', 'temperature day after tomorrow',
                        'how hot will it be day after tomorrow', 'how cold will it be day after tomorrow',
                        'day after tomorrows temperature', 'tell me the temperature for day after tomorrow',
                        'what temperature day after tomorrow', 'degrees day after tomorrow',
                        'will it be hot day after tomorrow', 'will it be cold day after tomorrow'
                    ]
                },
                'humidity': {
                    'today': [
                        'humidity level', 'current humidity', 'how humid is it',
                        'whats the humidity', 'what is the humidity level right now',
                        'tell me the humidity', 'what is the current humidity level',
                        'is the humidity high or low', 'huminity percentage',
                        'what is the humidity percentage', 'todays humidity reading',
                        'tell me todays humidity reading',
                    ],
                    'tomorrow': [
                        'tomorrow humidity', 'humidity tomorrow', 'how humid will it be tomorrow',
                        'tomorrows humidity', 'tell me the humidity for tomorrow',
                        'what humidity tomorrow', 'will it be humid tomorrow',
                        'humidity forecast for tomorrow'
                    ],
                    'day_after_tomorrow': [
                        'day after tomorrow humidity', 'humidity day after tomorrow',
                        'how humid will it be day after tomorrow', 'day after tomorrows humidity',
                        'tell me the humidity for day after tomorrow', 'what humidity day after tomorrow',
                        'will it be humid day after tomorrow'
                    ]
                }
            }
        }

        patterns = weather_patterns[lang]

        # Check weather forecast
        for day_key, day_data in [('today', today_data), ('tomorrow', tomorrow_data), ('day_after_tomorrow', day_after_tomorrow_data)]:
            if day_data is None:
                continue

            # Weather queries
            if processed_text in patterns['weather'][day_key]:
                if day_key == 'today':
                    return (f"当前天气：{day_data.get('current_description_zh', '未知')}") if lang == 'chinese' else (
                        f"Current weather: {day_data.get('current_description_en', 'unknown')}")
                else:
                    if lang == 'chinese':
                        day_name = "明天" if day_key == 'tomorrow' else "后天"
                        return f"{day_name}天气：{day_data.get('description_zh', '未知')}"
                    else:
                        day_name = "Tomorrow" if day_key == 'tomorrow' else "Day after tomorrow"
                        return f"{day_name}'s weather: {day_data.get('description_en', 'unknown')}"

            # temperature query
            if processed_text in patterns['temperature'][day_key]:
                if day_key == 'today':
                    return (f"当前温度{day_data.get('current_temperature', '未知')}度，体感温度{day_data.get('current_feels_like', '未知')}度") if lang == 'chinese' else (
                        f"Current temperature is {day_data.get('current_temperature', 'unknown')}°C, "
                        f"feels like {day_data.get('current_feels_like', 'unknown')}°C")
                else:
                    if lang == 'chinese':
                        day_name = "明天" if day_key == 'tomorrow' else "后天"
                        return f"{day_name}温度{day_data.get('min_temp', '未知')}°C ~ {day_data.get('max_temp', '未知')}°C，平均温度{day_data.get('avg_temp', '未知')}°C"
                    else:
                        day_name = "Tomorrow" if day_key == 'tomorrow' else "Day after tomorrow"
                        return f"{day_name}'s temperature: {day_data.get('min_temp', 'unknown')}°C ~ {day_data.get('max_temp', 'unknown')}°C, average {day_data.get('avg_temp', 'unknown')}°C"

            # Humidity queries
            if 'humidity' in patterns and processed_text in patterns['humidity'][day_key]:
                if day_key == 'today':
                    return (f"当前湿度{day_data.get('current_humidity', '未知')}%") if lang == 'chinese' else (
                        f"Current humidity is {day_data.get('current_humidity', 'unknown')}%")
                else:
                    if lang == 'chinese':
                        day_name = "明天" if day_key == 'tomorrow' else "后天"
                        return f"{day_name}湿度预计为{day_data.get('humidity', '未知')}%"
                    else:
                        day_name = "Tomorrow" if day_key == 'tomorrow' else "Day after tomorrow"
                        return f"{day_name}'s humidity is expected to be {day_data.get('humidity', 'unknown')}%"

        # If no queries match
        return None

    def preprocess_text(self, text: str) -> tuple[str, str]:
        """
        Preprocess text by removing punctuation, converting to lowercase, and detecting language type
        """
        # Define additional Chinese punctuation
        chinese_punctuation = '，。！？；：""''【】（）《》、…￥'

        # Create translation table for English and Chinese punctuation
        trans_table = str.maketrans('', '', string.punctuation + chinese_punctuation)

        # Remove all punctuation and convert to lowercase
        text = text.lower().translate(trans_table)

        # Detect language type (simple check: contains Chinese characters = Chinese)
        is_chinese = any('\u4e00' <= char <= '\u9fff' for char in text)
        lang = 'chinese' if is_chinese else 'english'

        # For Chinese text, remove all spaces
        if lang == 'chinese':
            text = text.replace(' ', '')
        else:
            # For English text, replace multiple spaces with a single space
            text = ' '.join(text.split())

        return text, lang

    def start_weather_update_thread(self):
        """
        Start a background thread to periodically update weather data

        Returns:
            bool: Always returns True (the function does not actually return because it contains an infinite loop)
        """
        # Log thread startup
        logger.info("Weather update thread started")

        # Use self reference to ensure proper access to instance in class methods
        weather_handler = self

        def _update_loop():
            """Internal function containing the actual update loop"""
            while True:
                try:
                    # Update weather data
                    logger.info("Updating weather data...")
                    success = weather_handler.update_weather_data()

                    if success:
                        logger.info("Weather data updated successfully, will update again in 3 hours")
                        time.sleep(10800)  # 3 hours
                    else:
                        logger.warning("Weather data update failed, retrying in 5 minutes")
                        time.sleep(300)  # 5 minutes
                except Exception as e:
                    logger.error(f"Error in weather update loop: {e}")
                    time.sleep(1800)  # Retry in 30 minutes after error

        # Create and start the update thread
        update_thread = threading.Thread(target=_update_loop, daemon=True)
        update_thread.start()

        return True

# Test code
if __name__ == "__main__":
    print("\n=== Weather System Test ===\n")
    weatherhandler = WeatherHandler()
    # Test updating weather data
    print("Updating weather data...")
    if weatherhandler.update_weather_data():
        print("Weather data updated successfully!")
    else:
        print("Weather data update failed!")

    print(weatherhandler.check_weather_query("今天天气怎么样"))
    print(weatherhandler.check_weather_query("明天天气怎么样"))
    print(weatherhandler.check_weather_query("后天天气怎么样"))
    print(weatherhandler.check_weather_query("明天的湿度是多少"))
    print(weatherhandler.check_weather_query("后天的天气预报是什么"))
    print(weatherhandler.check_weather_query("后天的湿度是多少"))
    print(weatherhandler.check_weather_query("what's the weather like?"))
    print(weatherhandler.check_weather_query("What is the humidity tomorrow?"))
    print(weatherhandler.check_weather_query("What is the weather forecast for the day after tomorrow?"))
    print(weatherhandler.check_weather_query("What is the humidity level the day after tomorrow?"))
    print(weatherhandler.check_weather_query("Weather forecast?"))