import time
import json
import re
from loguru import logger
from datetime import datetime, timedelta
import string


class TimeHandler:
    # Time-related function names
    TIME_FUNCTIONS = {"get_time", "get_relative_time", "get_time_difference"}

    def __init__(self):
        """Initialize TimeHandler instance"""
        pass

    def is_time_function(self, function_name: str) -> bool:
        """Check if the function is time-related"""
        return function_name in self.TIME_FUNCTIONS

    def format_for_tts(self, value: str, format_type: str = None, lang: str = 'english') -> str:
        """Format values to be more TTS-friendly while keeping numbers"""
        if format_type == "year":
            return f"Year {value}" if lang == 'english' else f"{value}年"

        elif format_type == "date":
            date_obj = datetime.strptime(value, "%Y-%m-%d")
            if lang == 'english':
                day = date_obj.day
                suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
                return f"{date_obj.strftime('%B')} {day}{suffix}, {date_obj.year}"
            else:
                return f"{date_obj.year}年{int(date_obj.month)}月{date_obj.day}日"

        elif format_type == "time":
            time_obj = datetime.strptime(value, "%H:%M")
            if lang == 'english':
                return time_obj.strftime("%I:%M %p").lstrip("0")
            else:
                hour = time_obj.hour
                minute = time_obj.minute
                return f"{hour}点{minute}分" if minute != 0 else f"{hour}点整"

        return value

    def get_time_info(self, time_format: str = None) -> str:
        """Unified time information retrieval function"""
        now = datetime.now()
        period = "morning" if now.hour < 12 else "afternoon" if now.hour < 18 else "evening"

        time_formats = {
            "time": self.format_for_tts(now.strftime("%H:%M"), "time"),
            "date": self.format_for_tts(now.strftime("%Y-%m-%d"), "date"),
            "weekday": now.strftime("%A"),
            "month": now.strftime("%B"),
            "year": self.format_for_tts(now.strftime("%Y"), "year"),
            "week_number": f"Week {now.strftime('%U')}",
            "period": period,
            "time_with_period": f"{period} {self.format_for_tts(now.strftime('%H:%M'), 'time')}"
        }

        return time_formats.get(time_format, self.format_for_tts(now.strftime("%H:%M"), "time"))

    def get_relative_time(self, value: int, unit: str) -> datetime:
        """Calculate relative time"""
        now = datetime.now()
        time_units = {
            "minutes": lambda x: timedelta(minutes=x),
            "hours": lambda x: timedelta(hours=x),
            "days": lambda x: timedelta(days=x),
            "weeks": lambda x: timedelta(weeks=x),
            "months": lambda x: timedelta(days=x*30),  # Approximate value
            "years": lambda x: timedelta(days=x*365)   # Approximate value
        }
        delta = time_units.get(unit, lambda x: timedelta(minutes=x))(value)
        return now + delta

    def process_time_response(self, ai_response: dict) -> str:
        """Process time-related responses"""
        response_text = ai_response["response"]
        function_name = ai_response["function_name"]

        # Handle get_time_difference function
        if function_name == "get_time_difference":
            value = ai_response.get("parameters", {}).get("value", "")
            diff_result = self.get_time_difference({"value": value})

            # Replace all placeholders in the response text
            if "error" not in diff_result:
                for key, value in diff_result.items():
                    placeholder = f"{{{key}}}"
                    if placeholder in response_text:
                        response_text = response_text.replace(placeholder, str(value))
            else:
                return "Unable to calculate time difference"

            return response_text

        # Handle relative time
        relative_formats = ["minutes", "hours", "days", "weeks", "months", "years"]
        for format_key in relative_formats:
            placeholder = f"{{relative_time_{format_key}}}"
            if placeholder in response_text:
                value = ai_response.get("parameters", {}).get(format_key, 0)
                future_time = self.get_relative_time(value, format_key)
                # Format the future time in a more readable way
                formatted_date = self.format_for_tts(future_time.strftime("%Y-%m-%d"), "date")
                formatted_time = self.format_for_tts(future_time.strftime("%H:%M"), "time")
                formatted_result = f"{formatted_date} at {formatted_time}"
                response_text = response_text.replace(placeholder, formatted_result)

        # Handle other time information
        for format_key in ["time", "date", "weekday", "month", "year", "week_number", "period", "time_with_period"]:
            if f"{{{format_key}}}" in response_text:
                value = self.get_time_info(format_key)
                response_text = response_text.replace(f"{{{format_key}}}", str(value))

        return response_text

    def process_response(self, ai_response: str | dict) -> str:
        """Process AI response based on function type"""
        try:
            # Parse JSON if input is string
            if isinstance(ai_response, str):
                json_pattern = r"```json\s*([\s\S]*?)\s*```"
                json_match = re.search(json_pattern, ai_response)

                if json_match:
                    json_str = json_match.group(1).strip()
                else:
                    json_str = ai_response.strip()

                try:
                    ai_response = json.loads(json_str)
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON string: {e}")
                    return "Invalid JSON format"

            # Check if it's a function call
            if ai_response.get("type") != "function call":
                logger.error("Not a function call")
                return "Invalid response type"

            # Get parameters from the new structure
            parameters = ai_response.get("parameters", {})
            function_name = parameters.get("function_name")

            if not function_name:
                logger.error("No function_name provided in parameters")
                return "Invalid response format"

            if self.is_time_function(function_name):
                return self.process_time_response({
                    "function_name": function_name,
                    "response": parameters.get("format", "Current time is {time}"),
                    "parameters": parameters
                })
            else:
                logger.info(f"Non-time function: {function_name}")
                return str(parameters)

        except Exception as e:
            logger.error(f"Error processing response: {e}")
            return "Error processing response"

    def preprocess_text(self, text: str) -> tuple[str, str]:
        """
        Preprocess text, including removing punctuation, converting to lowercase, and determining language type

        Args:
            text: Input text

        Returns:
            tuple: (Processed text, Language type ('chinese' or 'english'))
        """
        # Define additional Chinese punctuation
        chinese_punctuation = '，。！？；：""''【】（）《》、…￥'

        # Create translation table for both English and Chinese punctuation
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
            # For English text, replace multiple spaces with single space
            text = ' '.join(text.split())

        return text, lang

    def get_time_difference(self, target: dict) -> dict:
        """
        Calculate time difference between current time and target time/date.
        """
        now = datetime.now()

        if not isinstance(target, dict):
            return {"error": "Invalid target format"}

        target_value = target.get("value", "")
        if not target_value:
            return {"error": "Missing target value"}

        try:
            # Try to parse complete time string
            parts = target_value.replace(",", "").split()

            # Parse time
            time_str = " ".join(parts[0:2])  # "3:00 PM"
            target_time = datetime.strptime(time_str, "%I:%M %p")

            # Parse date
            month = parts[3]  # "March"
            day = int(parts[4])  # "12"
            year = int(parts[6])  # "2024" - skip "Year" word

            # Build complete target time
            target_dt = datetime(
                year=year,
                month=datetime.strptime(month, "%B").month,
                day=day,
                hour=target_time.hour,
                minute=target_time.minute
            )

            # Calculate time difference
            diff = target_dt - now
            total_seconds = diff.total_seconds()

            # If target time has passed, calculate difference to next occurrence
            if total_seconds < 0:
                # If today's time has passed, calculate to same time tomorrow
                if target_dt.date() == now.date():
                    target_dt = target_dt + timedelta(days=1)
                    diff = target_dt - now
                    total_seconds = diff.total_seconds()

            # Calculate time units
            days = int(total_seconds // (24 * 3600))
            remaining_seconds = total_seconds % (24 * 3600)
            hours = int(remaining_seconds // 3600)
            minutes = int((remaining_seconds % 3600) // 60)

            # Calculate total time
            total_hours = int(total_seconds // 3600)
            total_minutes = int(total_seconds // 60)

            # Format target time for readability
            formatted_target = self.format_for_tts(target_dt.strftime("%Y-%m-%d"), "date")
            formatted_time = self.format_for_tts(target_dt.strftime("%H:%M"), "time")

            # Return dictionary with detailed time difference information
            return {
                "days": days,                      # Days difference (integer part)
                "hours": hours,                    # Hours difference (remaining hours after days)
                "minutes": minutes,                # Minutes difference (remaining minutes after hours)
                "target_date": formatted_target,   # Formatted target date, e.g. "March 12th, 2024"
                "target_time": formatted_time,     # Formatted target time, e.g. "3:00 PM"
                "target_weekday": target_dt.strftime("%A"),  # Target date weekday, e.g. "Tuesday"
                "total_hours": total_hours,        # Total hours (including days converted to hours)
                "total_minutes": total_minutes,    # Total minutes (including hours converted to minutes)
                "total_seconds": int(total_seconds),  # Total seconds
                "is_future": total_seconds > 0,    # Boolean indicating if target time is in future
                "years": days // 365,              # Years difference (estimated)
                "months": (days % 365) // 30,      # Months difference (remaining months after years, estimated)
                "remaining_days": days % 30        # Remaining days (remaining days after months)
            }

        except Exception as e:
            return {"error": f"Invalid datetime format: {str(e)}"}

    def check_time_query(self, query: str) -> str:
        """
        Process all time-related queries using complete sentence matching
        """
        # Preprocess text
        processed_text, lang = self.preprocess_text(query)
        now = datetime.now()

        # Define complete query sentence patterns
        time_patterns = {
            'chinese': {
                'current_time': [
                    '几点了',
                    '现在几点',
                    '现在几点了',
                    '现在是几点',
                    '请问现在几点',
                    '能告诉我现在几点吗',
                    '现在时间',
                    '当前时间',
                    '现在的时间',
                    '当前的时间',
                    '现在的时间是多少',
                    '当前时间是多少',
                    '当前的时间是多少',
                    '能告诉我现在的时间吗',
                    '请告诉我现在的时间',
                    '你能报一下时间吗',
                    '报时',
                    '请报一下时间',
                    '请问现在几点了',
                    '你能告诉我现在几点了吗',
                    '你能告诉我现在是什么时间吗',
                    '播报时间',
                    '请播报时间',
                    '报一下时间',
                    '什么时候了',
                    '什么时间了',
                    '现在是什么时候',
                    '现在是什么时间',
                    '现在什么时间',
                    '请问现在是什么时候',
                    '几点钟了',
                    '现在几点钟了',
                    '现在几点来着',
                    '现在几点钟来着',
                    '现在的具体时间是多少呢',
                    '具体时间是多少呢',
                    '告诉我具体时间',
                    '现在是几时几刻',
                    '请告诉我现在是几时几刻',
                    '现在是早上几点',
                    '现在是下午几点',
                    '现在是晚上几点',
                    '现在是傍晚几点',
                    '现在是凌晨几点',
                    '现在是中午几点',
                    '现在是半夜几点',
                    '准确告诉我现在几点了',
                    '准确告诉我现在几点钟了',
                    '准确告诉我现在几点钟来着',
                    '准确告诉我现在具体时间',
                    '准确告诉我现在是几时几刻',
                    '准确告诉我现在是早上几点',
                    '准确告诉我现在是下午几点',
                    '准确告诉我现在是晚上几点',
                    '准确告诉我现在是半夜几点',
                    '准确告诉我现在是中午几点',
                    '准确告诉我现在是几点钟',
                    '大约几点了',
                    '大约几点钟了',
                    '现在是大约几点了',
                    '现在是大约几点钟了',
                    '我想知道现在的时间'
                ],
                'full_datetime': [
                    '现在的日期和时间',
                    '现在的日期和时间是多少',
                    '请告诉我当前的日期和时间',
                    '当前日期和时间是多少',
                    '今天是几月几号几点了',
                    '今天是几月几号几点钟了',
                    '告诉我现在的日期和时间',
                    '告诉我当前的日期和时间',
                    '请问今天的日期和时间是多少',
                    '请问今天的日期和时间是什么',
                    '播报今天的日期和时间',
                    '播报当前的日期和时间',
                    '请播报当前的日期和时间',
                    '报一下当前的日期和时间',
                    '现在是几月几号几点了',
                    '现在是几月几号几点钟了',
                    '准确告诉我当前的日期和时间',
                    '请准确告诉我今天的日期和时间',
                    '请准确告诉我现在的日期和时间',
                    '今天是星期几，几号，几点',
                    '今天是几号几点星期几呢',
                    '我想知道现在的日期和时间',
                    '我想知道当前的日期和时间'
                ],
                'date_only': [
                    '今天几号',
                    '今天是几号',
                    '今天几号了',
                    '今天日期',
                    '现在日期',
                    '今天的日期',
                    '请问今天几号',
                    '今天日期是什么',
                    '今天的日期是什么',
                    '今天日期是几号',
                    '今天日期是多少',
                    '今天是什么日期',
                    '今天的日期是几号',
                    '今天的日期是多少',
                    '现在的日期是多少',
                    '请告诉我当前的日期',
                    '请告诉我当前日期'
                ],
                'weekday_only': [
                    '今天星期几',
                    '今天是星期几',
                    '今天周几',
                    '现在是星期几',
                    '星期几',
                    '请问今天是星期几',
                    '星期几了今天',
                    '拜几了',
                    '今天拜几了',
                    '播报一下今天星期几了',
                    '请播报一下今天星期几了'
                ],
                'month_only': [
                    '这是几月',
                    '现在几月',
                    '现在是几月',
                    '现在几月了',
                    '这个月是几月',
                    '几月份',
                    '当前月份',
                    '当前是几月',
                    '请问现在几月',
                    '现在是哪一月',
                    '今天几月了',
                    '今天是几月了',
                    '今天几月份了',
                    '现在是几月份了',
                    '请告诉我现在是几月份了',
                    '请告诉我现在是几月',
                    '请告诉我现在是几月份',
                    '播报当前月份',
                    '播报一下当前的月份',
                    '请播报一下当前的月份',
                    '现在是哪一个月份了',
                    '现在是几月份',
                    '几月了'
                ],
                'year_only': [
                    '现在是哪一年',
                    '今年是哪年',
                    '今年多少年',
                    '现在是几年',
                    '今年是几几年',
                    '当前年份',
                    '请问现在是哪一年',
                    '请问现在是几几年',
                    '今年是哪一年',
                    '今年几几年',
                    '今年几年',
                    '今年是多少年',
                    '当前年份是多少',
                    '现在几年了',
                    '现在的年份是多少',
                    '请告诉我现在是哪一年',
                    '播报当前年份',
                    '准确告诉我今年年份',
                    '准确告诉我现在是哪一年',
                    '告诉我现在的年份',
                    '准确告诉我现在的年份',
                    '播报一下当前年份',
                    '播报一下当前年份是多少',
                    '如今多少年了',
                    '多少年了',
                    '今年年份是多少',
                    '今年几年了'
                ]
            },
            'english': {
                'current_time': [
                    'what time is it',
                    'whats the time',
                    'can you tell me the time',
                    'could you please tell me the time',
                    'tell me the time',
                    'may i know the current time',
                    'do you know what time it is',
                    'current time',
                    'what time is it now',
                    'what time is now',
                    'now the time is',
                    'what time is it exactly',
                    'now is what time',
                    'right now the time is',
                    'the exactly time is',
                    'now the time is what',
                    'what is the current time now',
                    'tell me the current time',
                    'what the time now'
                ],
                'full_datetime': [
                    'what is the current date and time',
                    'whats the date and time now',
                    'can you tell me the current date and time',
                    'could you please tell me the date and time',
                    'tell me the date and time',
                    'what time and date is it',
                    'current date and time'
                ],
                'date_only': [
                    'what date is it',
                    'whats the date',
                    'current date',
                    'what is the date today',
                    'whats todays date',
                    'can you tell me the date',
                    'what date is it today',
                    'may i know todays date',
                    'tell me the date today',
                    'today is what date',
                    'let me know the date today',
                    'do you know todays date'
                ],
                'weekday_only': [
                    'what day is it',
                    'which day is today',
                    'what day of the week is it',
                    'what day is it today',
                    'which day of the week is it',
                    'do you know what day it is',
                    'whats the day today',
                    'can you tell me what day it is',
                    'what day is today'
                    'today is which day',
                    'let me know the day today',
                ],
                'month_only': [
                    'what month is it',
                    'which month are we in',
                    'current month',
                    'tell me the month',
                    'can you tell me the current month',
                    'what is the current month',
                    'may i know what month it is',
                    'what is the month of today',
                    'now is which month',
                    'what month is today',
                    'let me know the month today',
                    'do you know the current month'
                ],
                'year_only': [
                    'what year is it',
                    'which year are we in',
                    'current year',
                    'tell me the year',
                    'can you tell me the current year',
                    'whats the current year',
                    'may i know what year it is',
                    'let me know the year is',
                    'do you know the current year',
                    'now we are in which year',
                    'which year we are now in',
                    'what year is it exactly',
                    'what year is it now'
                ]
            }
        }

        patterns = time_patterns[lang]

        # Process time queries (complete sentence matching)
        if lang == 'chinese':
            # Current time query
            if processed_text in patterns['current_time']:
                period_label = ("凌晨" if now.hour < 6 else
                            "上午" if now.hour < 12 else
                            "中午" if now.hour < 13 else
                            "下午" if now.hour < 18 else "晚上")
                formatted_time = self.format_for_tts(now.strftime("%H:%M"), "time", lang)
                return f"现在是{period_label}{formatted_time}。"

            # Complete date and time query
            if processed_text in patterns['full_datetime']:
                period_label = ("凌晨" if now.hour < 6 else
                            "上午" if now.hour < 12 else
                            "中午" if now.hour < 13 else
                            "下午" if now.hour < 18 else "晚上")
                formatted_time = self.format_for_tts(now.strftime("%H:%M"), "time", lang)
                formatted_date = self.format_for_tts(now.strftime("%Y-%m-%d"), "date", lang)
                weekday_map = {'0': '星期日', '1': '星期一', '2': '星期二', '3': '星期三',
                            '4': '星期四', '5': '星期五', '6': '星期六'}
                weekday = weekday_map.get(now.strftime("%w"))
                return f"现在是{period_label}{formatted_time}，{formatted_date} {weekday}"

            # Date only query
            if processed_text in patterns['date_only']:
                formatted_date = self.format_for_tts(now.strftime("%Y-%m-%d"), "date", lang)
                return f"今天是{formatted_date}"

            # Weekday only query
            if processed_text in patterns['weekday_only']:
                weekday_map = {'0': '星期日', '1': '星期一', '2': '星期二', '3': '星期三',
                            '4': '星期四', '5': '星期五', '6': '星期六'}
                weekday = weekday_map.get(now.strftime("%w"))
                return f"今天是{weekday}"

            # Month only query
            if processed_text in patterns['month_only']:
                month = int(now.strftime("%m"))
                return f"现在是{month}月"

            # Year only query
            if processed_text in patterns['year_only']:
                year = now.strftime("%Y")
                return f"现在是{year}年"

        else:  # English responses
            if processed_text in patterns['current_time']:
                formatted_time = self.format_for_tts(now.strftime("%H:%M"), "time", lang)
                return f"It's {formatted_time}"

            if processed_text in patterns['full_datetime']:
                formatted_time = self.format_for_tts(now.strftime("%H:%M"), "time", lang)
                formatted_date = self.format_for_tts(now.strftime("%Y-%m-%d"), "date", lang)
                weekday = now.strftime("%A")
                return f"It's {formatted_time} on {weekday}, {formatted_date}"

            if processed_text in patterns['date_only']:
                formatted_date = self.format_for_tts(now.strftime("%Y-%m-%d"), "date", lang)
                return f"Today is {formatted_date}"

            if processed_text in patterns['weekday_only']:
                weekday = now.strftime("%A")
                return f"Today is {weekday}"

            # Month only query
            if processed_text in patterns['month_only']:
                month = now.strftime("%B")
                return f"It's {month}"

            # Year only query
            if processed_text in patterns['year_only']:
                year = now.strftime("%Y")
                return f"It's {year}"

        return None


    def include_time_keywords(self, query: str) -> str:
        """
        Process all time-related queries and return a unified English response.
        Returns complete time information when any time-related keyword is detected.

        Args:
            query: User's input query

        Returns:
            str: Complete formatted time response in English
        """
        # Define time-related keywords with separate Chinese and English categories
        time_keywords = {
            'english': {
                'time': ['time', 'hour', 'clock', 'oclock'],
                'date': ['date', 'day'],
                'week': ['week', 'weekday'],
                'month': ['month'],
                'year': ['year'],
                'period': ['morning', 'afternoon', 'evening', 'night'],
                'query': ['now', 'current', 'today', 'this', 'at this moment', 'currently',
                        'presently', 'right now']
            },
            'chinese': {
                'time': ['时间', '时候', '时', '点', '几点', '钟点', '点钟', '时分', '时刻表',
                        '现在几点钟', '分钟', '小时'],
                'date': ['日期', '号', '几号', '日子', '今天', '哪天', '具体日期', '今日日期',
                        '日历', '多少天', '天'],
                'week': ['星期', '周', '礼拜', '星期几', '周几', '礼拜几', '本周周数'],
                'month': ['月份', '几月', '月', '这个月', '当前月份', '月份名称'],
                'year': ['年份', '哪年', '年', '当前年份', '年份数字', '今年是'],
                'period': ['上午', '中午', '下午', '晚上', '早上'],
                'query': ['现在', '当前', '此刻', '实时', '眼下', '今', '请问']
            }
        }

        # Preprocess text
        processed_text, lang = self.preprocess_text(query)

        # Check if any time-related keyword is present from either language
        main_categories = ['time', 'date', 'week', 'month', 'year', 'period']
        has_time_keyword = any(
            any(word in processed_text for word in time_keywords['english'][cat] + time_keywords['chinese'][cat])
            for cat in main_categories
        )

        # If no time-related keyword is found, return None
        if not has_time_keyword:
            return None

        # Get current time information
        now = datetime.now()

        # Determine period label
        if now.hour < 6:
            period_label = "early morning"
        elif now.hour < 12:
            period_label = "morning"
        elif now.hour < 13:
            period_label = "noon"
        elif now.hour < 18:
            period_label = "afternoon"
        else:
            period_label = "evening"

        # Format complete time information
        formatted_time = self.format_for_tts(now.strftime("%H:%M"), "time", "english")
        formatted_date = self.format_for_tts(now.strftime("%Y-%m-%d"), "date", "english")
        weekday = now.strftime("%A")
        month = now.strftime("%B")
        year = self.format_for_tts(now.strftime("%Y"), "year", "english")

        return f"(Current local time: {formatted_time}, {weekday}, {month} {now.day}, {year})"

# Test code
if __name__ == "__main__":
    time_handler = TimeHandler()
    logger.debug(time_handler.include_time_keywords("When is Christmas Day?"))
    logger.debug(time_handler.check_time_query("What time is it"))