import websearch_function

class WebHandler:
    def __init__(self):
        pass

    def check_web_search_query(self, query: str) -> tuple[str, bool]:
        """
        Check if the query is requesting a web search and perform the search if needed

        This function detects if a user query is requesting to search the web
        by checking if it starts with specific search-related keywords in both
        Chinese and English.

        Args:
            query: User's query text

        Returns:
            tuple: (Search result or empty string, Boolean indicating if query was handled)
        """
        # Remove leading/trailing spaces
        clean_query = query.strip()

        # Define web search keywords (both Chinese and English)
        search_keywords = {
            'chinese': [
                '帮我找', '帮我找看看', '帮我搜', '帮我搜索', '帮我搜看看',
                '搜索', '查询', '网上搜索', '网上查询', '查一查',
                '搜一搜', '找一找', '检索', '上网查', '查找',
                '搜查', '谷歌一下', '必应一下'
            ],
            'english': [
                'search for', 'look up', 'find information about', 'google',
                'search the web for', 'search online for', 'find out about',
                'web search', 'internet search', 'look for', 'search about'
            ]
        }

        # Check if query starts with any of the keywords
        has_chinese = any('\u4e00' <= char <= '\u9fff' for char in clean_query)
        keywords = search_keywords['chinese'] if has_chinese else search_keywords['english']

        # Check if query starts with any of the search keywords
        for keyword in keywords:
            if clean_query.lower().startswith(keyword.lower()):
                # Extract the search query (remove the keyword)
                search_content = clean_query[len(keyword):].strip()

                # If there's no actual search content after the keyword
                if not search_content:
                    return "Please specify what you would like to search for." if not has_chinese else "请说明您想要搜索什么内容。", True

                try:
                    # Perform web search
                    search_result = websearch_function.basic_search(search_content)


                    return search_result, True

                except Exception as e:
                    error_msg = f"Error performing web search: {str(e)}" if not has_chinese else f"进行网络搜索时出错：{str(e)}"
                    return error_msg, True

        # Not a web search query
        return "", False

    def check_web_query(self, query: str) -> tuple[str, bool]:
        """
        Process web search queries and generate appropriate responses

        Args:
            query: User's query text

        Returns:
            tuple: (Search result or error message, Boolean indicating if query was handled)
        """
        search_result, is_search_query = self.check_web_search_query(query)

        # If it's a search query, we've already handled it in check_web_search_query
        if is_search_query:
            return search_result, True

        # Not a web search query
        return "", False


if __name__ == "__main__":
    # Test the web search query function
    web_handler = WebHandler()
    test_query = "Help me find the latest news about Malacca."
    result, handled = web_handler.check_web_query(test_query)
    print(f"Query: {test_query}\nResult: {result}\nHandled: {handled}")