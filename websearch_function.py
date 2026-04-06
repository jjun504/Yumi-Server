from tavily import TavilyClient
from unified_config import get_config
client = TavilyClient(get_config("web_search.tavily_api_key"))

def basic_search(query):
    global client
    response = client.search(
        query=query,
        include_answer="basic"
    )
    response_info = {
        "query": response["query"],
        "answer": response["answer"],
        "result": response["results"][0]["title"],
        "url": response["results"][0]["url"],
    }
    return response_info

def news_search(query):
    global client
    response = client.search(
        query=query,
        topic="news",
        include_answer="basic"
    )
    print(response["answer"])
    return response["answer"]

if __name__ == "__main__":
    # Basic search("Johor News")
    print(basic_search("Johor recently News"))