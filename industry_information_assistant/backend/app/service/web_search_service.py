
import http.client
import json
from typing import Dict, Any, List

from config.settings import settings

class WebSearchService:
    """ 使用 Serper API 执行网络搜索的服务 """

    def __init__(self, api_key: str = None):
        """
        使用 API 密钥初始化 WebSearchService。

        参数:
            api_key: Serper.dev 的 API 密钥。如果未提供，将从统一配置（环境变量）中读取。
        """
        self.api_key = api_key or settings.serper_api_key
        self.host = settings.serper_host
        self.headers = {
            'X-API-KEY': self.api_key,
            'Content-Type': 'application/json'
        }
    
    def search(self, 
              query: str, 
              gl: str = "cn", 
              hl: str = "zh-cn", 
              autocorrect: bool = True, 
              page: int = 1,
              search_type: str = "search") -> Dict[str, Any]:
        """
        使用 Serper API 执行网络搜索。
        
        参数:
            query:        搜索查询文本
            gl:           Google 国家代码（默认: "us"）
            hl:           语言代码（默认: "en"）
            autocorrect:  是否启用自动纠错（默认: True）
            page:         搜索结果页码（默认: 1）
            search_type:  搜索类型（默认: "search"）
            
        返回:
            搜索结果的字典
        """
        conn = http.client.HTTPSConnection(self.host)
        
        payload = json.dumps({
            "q": query,
            "gl": gl,
            "hl": hl,
            "autocorrect": autocorrect,
            "page": page,
            "type": search_type
        })
        
        try:
            conn.request("POST", "/search", payload, self.headers)
            res = conn.getresponse()
            data = res.read()
            return json.loads(data.decode("utf-8"))
        except Exception as e:
            return {
                "error": True,
                "message": f"Search failed: {str(e)}"
            }
        finally:
            conn.close()
    
    def extract_search_results(self, search_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        从 API 响应中提取格式化后的搜索结果。
        
        参数:
            search_results: 来自 search 方法的完整 API 响应
            
        返回:
            简化后的搜索结果项列表
        """
        results = []
        
        # Add knowledge graph if present
        if "knowledgeGraph" in search_results:
            kg = search_results["knowledgeGraph"]
            results.append({
                "type": "knowledgeGraph",
                "title": kg.get("title", ""),
                "description": kg.get("description", ""),
                "source": kg.get("descriptionSource", ""),
                "link": kg.get("descriptionLink", ""),
                "attributes": kg.get("attributes", {})
            })
            
        # Add organic search results
        if "organic" in search_results:
            for item in search_results["organic"]:
                results.append({
                    "type": "organic",
                    "title": item.get("title", ""),
                    "link": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                    "position": item.get("position", 0)
                })
                
        # Add people also ask
        if "peopleAlsoAsk" in search_results:
            for item in search_results["peopleAlsoAsk"]:
                results.append({
                    "type": "peopleAlsoAsk",
                    "question": item.get("question", ""),
                    "snippet": item.get("snippet", ""),
                    "title": item.get("title", ""),
                    "link": item.get("link", "")
                })
                
        # Add related searches
        if "relatedSearches" in search_results and search_results["relatedSearches"]:
            related = [item.get("query", "") for item in search_results["relatedSearches"] if "query" in item]
            if related:
                results.append({
                    "type": "relatedSearches",
                    "queries": related
                })
                
        return results 