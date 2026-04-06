import string

class ExitHandler:
    def preprocess_text(self, text: str) -> tuple[str, str]:
        """
        Preprocess text, including removing punctuation, converting to lowercase, and determining language type

        Args:
            text: Input text

        Returns:
            tuple: (Processed text, Language type ('chinese' or 'english'))
        """
        # Check if text is None or empty
        if text is None or text == "":
            return "", "english"  # Default to empty string and English

        # Define additional Chinese punctuation marks
        chinese_punctuation = '，。！？；：""''【】（）《》、…￥'

        # Create translation table to remove English and Chinese punctuation
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

    def ifend(self, text: str) -> bool:
        """
        Check if user wants to end the conversation
        """
        # Handle None or empty text
        if text is None or text == "":
            return True  # End conversation if no text

        # Preprocess text
        processed_text, lang = self.preprocess_text(text)

        # Define complete matching patterns for ending conversation
        end_patterns = {
            'chinese': [
                '结束对话',
                '结束对话吧',
                '下次再聊',
                '下次再聊吧',
                '没事了',
                '没事儿了',
                '没什么事了',
                '没有什么事了',
                '退一下吧',
                '退下吧',
                '退一下',
                '退下',
                '闭嘴',
                '再见',
                '下次再见',
                '拜拜',
                '先这样',
                '先这样吧',
                '终止对话',
                '停止对话',
            ],
            'english': [
                'end conversation',
                'end the conversation',
                'thats all',
                'goodbye',
                'bye',
                'see you',
                'see you later',
                'talk to you later',
                'stop',
                'dismiss',
                'thats it',
                'nothing else',
                'no more questions'
            ]
        }

        patterns = end_patterns.get(lang, [])

        # Check if matches any pattern completely
        if processed_text in patterns:
            return True
        return False

    def ifexit(self, text: str) -> bool:
        """
        Check if user wants to exit the program
        Using complete string matching patterns
        """
        # Handle None or empty text
        if text is None or text == "":
            return False  # Don't exit program if no text

        # Preprocess text
        processed_text, lang = self.preprocess_text(text)

        # Define complete matching patterns for exiting program
        exit_patterns = {
            'chinese': [
                '结束程序',
                '终止程序',
                '退出程序',
                '关闭程序',
                '停止程序',
                '彻底退出',
                '完全退出',
                '退出系统',
                '关机',
                '关闭系统',
                '结束应用',
                '终止应用',
                '退出应用'
            ],
            'english': [
                'power off',
                'exit program',
                'exit the program',
                'terminate program',
                'terminate the program',
                'quit program',
                'quit the program',
                'close program',
                'close the program',
                'shut down',
                'shutdown',
                'exit application',
                'quit application',
                'close application'
            ]
        }

        patterns = exit_patterns.get(lang, [])

        # Check if matches any pattern completely
        if processed_text in patterns:
            return True
        return False