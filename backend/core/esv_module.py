"""
External Search & Validation Module (ESV) - Mô-đun tìm kiếm và xác thực ngoài
Cầu nối với thế giới thực để xác thực thông tin

Lưu ý về DuckDuckGo Instant Answer API:
- API này là miễn phí (không cần API key), nhưng chỉ trả về Instant Answers/RelatedTopics, KHÔNG phải full search results.
- Trạng thái HTTP 202 có thể xảy ra khi máy chủ yêu cầu thêm thời gian để chuẩn bị câu trả lời hoặc từ chối vì tần suất cao.
- Không có rate-limit chính thức công khai; thực tế nên áp dụng rate-limit bảo thủ (≥1-2s/request) và backoff khi gặp 202.
- Tham khảo tài liệu/nguồn cộng đồng: Instant Answer API limitations, non-guaranteed SERP access.
"""

import asyncio
import aiohttp
import json
import logging
import re
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

@dataclass
class SearchQuery:
    """Cấu trúc cho search query"""
    query: str
    query_type: str  # "trend", "competitor", "market_size", "technology", "general"
    priority: str = "medium"  # "low", "medium", "high"
    timeout: int = 30
    max_results: int = 10

@dataclass
class SearchResult:
    """Kết quả tìm kiếm"""
    source: str
    title: str
    url: str
    snippet: str
    confidence: float  # 0-1
    relevance: float  # 0-1
    timestamp: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ValidationResult:
    """Kết quả xác thực"""
    query: SearchQuery
    results: List[SearchResult]
    summary: str
    confidence: float
    validation_status: str  # "confirmed", "refuted", "inconclusive", "partial"
    key_findings: List[str]
    sources_count: int
    processed_at: datetime = field(default_factory=datetime.now)

class ESVModule:
    """
    External Search & Validation Module
    """
    
    def __init__(self, config=None):
        self.config = config or {}
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Search engines configurations
        self.search_engines = {
            "google": {
                "url": "https://www.googleapis.com/customsearch/v1",
                "enabled": False,  # Requires API key
                "rate_limit": 1.0  # seconds between requests
            },
            "bing": {
                "url": "https://api.bing.microsoft.com/v7.0/search",
                "enabled": False,  # Requires API key
                "rate_limit": 1.0
            },
            "duckduckgo": {
                "url": "https://api.duckduckgo.com/",
                "enabled": True,  # Public API
                "rate_limit": 2.0
            }
        }
        
        # Specialized databases
        self.databases = {
            "crunchbase": {
                "url": "https://api.crunchbase.com/api/v4",
                "enabled": False,  # Requires API key
                "focus": ["startups", "funding", "competitors"]
            },
            "github": {
                "url": "https://api.github.com",
                "enabled": True,  # Public API with rate limits
                "focus": ["technology", "trends", "repositories"]
            }
        }
        
        # Cache
        self._cache: Dict[str, ValidationResult] = {}
        self._last_request_time: Dict[str, datetime] = {}
        
    async def __aenter__(self):
        """Async context manager entry"""
        await self.start_session()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close_session()
        
    async def start_session(self):
        """Khởi tạo aiohttp session"""
        if self.session is None:
            timeout = aiohttp.ClientTimeout(total=60)
            self.session = aiohttp.ClientSession(timeout=timeout)
            
    async def close_session(self):
        """Đóng aiohttp session"""
        if self.session:
            await self.session.close()
            self.session = None
    
    async def validate_multiple(self, queries: List[SearchQuery]) -> Dict[str, ValidationResult]:
        """Xác thực multiple queries parallel"""
        
        if not self.session:
            await self.start_session()
        
        # Check cache first
        results = {}
        queries_to_process = []
        
        for query in queries:
            cache_key = self._get_cache_key(query)
            if cache_key in self._cache:
                results[query.query] = self._cache[cache_key]
                logger.info(f"Cache hit for query: {query.query[:50]}...")
            else:
                queries_to_process.append(query)
        
        # Process uncached queries
        if queries_to_process:
            # Sort by priority
            queries_to_process.sort(key=lambda q: {"high": 3, "medium": 2, "low": 1}[q.priority], reverse=True)
            
            # Execute with rate limiting
            tasks = []
            for query in queries_to_process:
                task = self._validate_single_with_rate_limit(query)
                tasks.append(task)
            
            # Execute in batches to avoid overwhelming APIs
            batch_size = 3
            for i in range(0, len(tasks), batch_size):
                batch = tasks[i:i + batch_size]
                batch_results = await asyncio.gather(*batch, return_exceptions=True)
                
                for j, result in enumerate(batch_results):
                    query = queries_to_process[i + j]
                    
                    if isinstance(result, Exception):
                        logger.error(f"Error validating {query.query}: {str(result)}")
                        result = ValidationResult(
                            query=query,
                            results=[],
                            summary=f"Error during validation: {str(result)}",
                            confidence=0.0,
                            validation_status="inconclusive",
                            key_findings=[],
                            sources_count=0
                        )
                    
                    results[query.query] = result
                    
                    # Cache result
                    cache_key = self._get_cache_key(query)
                    self._cache[cache_key] = result
                
                # Rate limiting between batches
                if i + batch_size < len(tasks):
                    await asyncio.sleep(2.0)
        
        return results
    
    async def _validate_single_with_rate_limit(self, query: SearchQuery) -> ValidationResult:
        """Validate single query với rate limiting"""
        
        # Rate limiting
        await self._enforce_rate_limit()
        
        try:
            return await self._validate_single(query)
        except Exception as e:
            logger.error(f"Error in single validation: {str(e)}")
            return ValidationResult(
                query=query,
                results=[],
                summary=f"Validation failed: {str(e)}",
                confidence=0.0,
                validation_status="inconclusive",
                key_findings=[],
                sources_count=0
            )
    
    async def _validate_single(self, query: SearchQuery) -> ValidationResult:
        """Validate single query"""
        
        # Determine best search strategy
        search_strategy = self._determine_search_strategy(query)
        
        # Execute searches
        all_results = []
        
        for engine, enabled in search_strategy.items():
            if enabled:
                try:
                    engine_results = await self._search_with_engine(query, engine)
                    all_results.extend(engine_results)
                except Exception as e:
                    logger.warning(f"Search engine {engine} failed: {str(e)}")
        
        # Deduplicate và score results
        unique_results = self._deduplicate_results(all_results)
        scored_results = self._score_results(unique_results, query)
        
        # Analyze results
        analysis = self._analyze_results(scored_results, query)
        
        return ValidationResult(
            query=query,
            results=scored_results[:query.max_results],
            summary=analysis["summary"],
            confidence=analysis["confidence"],
            validation_status=analysis["status"],
            key_findings=analysis["key_findings"],
            sources_count=len(scored_results)
        )
    
    def _determine_search_strategy(self, query: SearchQuery) -> Dict[str, bool]:
        """Xác định chiến lược tìm kiếm tốt nhất"""
        
        strategy = {}
        
        # Default: try DuckDuckGo (always available)
        strategy["duckduckgo"] = True
        
        # Add specialized searches based on query type
        if query.query_type in ["technology", "trends"]:
            strategy["github"] = True
        
        if query.query_type in ["startups", "competitors", "funding"]:
            strategy["crunchbase"] = self.databases["crunchbase"]["enabled"]
        
        # Add major engines if available
        strategy["google"] = self.search_engines["google"]["enabled"]
        strategy["bing"] = self.search_engines["bing"]["enabled"]
        
        return strategy
    
    async def _search_with_engine(self, query: SearchQuery, engine: str) -> List[SearchResult]:
        """Tìm kiếm với một search engine cụ thể"""
        
        if engine == "duckduckgo":
            return await self._search_duckduckgo(query)
        elif engine == "github":
            return await self._search_github(query)
        elif engine == "google":
            return await self._search_google(query)
        elif engine == "bing":
            return await self._search_bing(query)
        else:
            logger.warning(f"Unknown search engine: {engine}")
            return []
    
    async def _search_duckduckgo(self, query: SearchQuery) -> List[SearchResult]:
        """Tìm kiếm với DuckDuckGo API (Instant Answer). Có backoff khi gặp 202."""
        
        max_attempts = 3
        backoff = 1.0
        
        for attempt in range(1, max_attempts + 1):
            try:
                url = "https://api.duckduckgo.com/"
                params = {
                    "q": query.query,
                    "format": "json",
                    "no_html": "1",
                    "skip_disambig": "1"
                }
                
                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return self._parse_duckduckgo_results(data, query)
                    elif response.status == 202:
                        logger.warning("DuckDuckGo API returned 202 - likely warming up or rate-limited. Retrying...")
                        await asyncio.sleep(backoff)
                        backoff *= 2
                        continue
                    else:
                        logger.warning(f"DuckDuckGo API returned {response.status}")
                        return []
            except Exception as e:
                logger.error(f"DuckDuckGo search error: {str(e)}")
                if attempt == max_attempts:
                    return []
                await asyncio.sleep(backoff)
                backoff *= 2
        
        return []
    
    async def _search_github(self, query: SearchQuery) -> List[SearchResult]:
        """Tìm kiếm repositories trên GitHub"""
        
        try:
            # GitHub Search API
            url = "https://api.github.com/search/repositories"
            params = {
                "q": query.query,
                "sort": "stars",
                "order": "desc",
                "per_page": min(query.max_results, 10)
            }
            
            headers = {
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "MCTS-ESV-Module"
            }
            
            async with self.session.get(url, params=params, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_github_results(data, query)
                else:
                    logger.warning(f"GitHub API returned {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"GitHub search error: {str(e)}")
            return []
    
    async def _search_google(self, query: SearchQuery) -> List[SearchResult]:
        """Tìm kiếm với Google Custom Search API (requires API key)"""
        
        api_key = self.config.get("google_api_key")
        search_engine_id = self.config.get("google_search_engine_id")
        
        if not api_key or not search_engine_id:
            logger.info("Google API credentials not configured")
            return []
        
        try:
            url = self.search_engines["google"]["url"]
            params = {
                "key": api_key,
                "cx": search_engine_id,
                "q": query.query,
                "num": min(query.max_results, 10)
            }
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_google_results(data, query)
                else:
                    logger.warning(f"Google API returned {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"Google search error: {str(e)}")
            return []
    
    async def _search_bing(self, query: SearchQuery) -> List[SearchResult]:
        """Tìm kiếm với Bing Search API (requires API key)"""
        
        api_key = self.config.get("bing_api_key")
        
        if not api_key:
            logger.info("Bing API key not configured")
            return []
        
        try:
            url = self.search_engines["bing"]["url"]
            headers = {
                "Ocp-Apim-Subscription-Key": api_key
            }
            params = {
                "q": query.query,
                "count": min(query.max_results, 10),
                "responseFilter": "Webpages"
            }
            
            async with self.session.get(url, params=params, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_bing_results(data, query)
                else:
                    logger.warning(f"Bing API returned {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"Bing search error: {str(e)}")
            return []
    
    def _parse_duckduckgo_results(self, data: Dict[str, Any], query: SearchQuery) -> List[SearchResult]:
        """Parse DuckDuckGo results"""
        
        results = []
        
        # Abstract (instant answer)
        if data.get("Abstract"):
            results.append(SearchResult(
                source="duckduckgo_abstract",
                title=data.get("AbstractText", "")[:100],
                url=data.get("AbstractURL", ""),
                snippet=data.get("AbstractText", ""),
                confidence=0.8,
                relevance=0.9,
                metadata={"type": "instant_answer"}
            ))
        
        # Related topics
        for topic in data.get("RelatedTopics", [])[:5]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append(SearchResult(
                    source="duckduckgo_related",
                    title=topic.get("Text", "")[:100],
                    url=topic.get("FirstURL", ""),
                    snippet=topic.get("Text", ""),
                    confidence=0.6,
                    relevance=0.7,
                    metadata={"type": "related_topic"}
                ))
        
        return results
    
    def _parse_github_results(self, data: Dict[str, Any], query: SearchQuery) -> List[SearchResult]:
        """Parse GitHub search results"""
        
        results = []
        
        for item in data.get("items", []):
            results.append(SearchResult(
                source="github",
                title=item.get("full_name", ""),
                url=item.get("html_url", ""),
                snippet=item.get("description", ""),
                confidence=min(item.get("stargazers_count", 0) / 1000, 1.0),
                relevance=0.8,
                timestamp=datetime.fromisoformat(item.get("updated_at", "").replace("Z", "+00:00")) if item.get("updated_at") else None,
                metadata={
                    "stars": item.get("stargazers_count", 0),
                    "language": item.get("language", ""),
                    "forks": item.get("forks_count", 0)
                }
            ))
        
        return results
    
    def _parse_google_results(self, data: Dict[str, Any], query: SearchQuery) -> List[SearchResult]:
        """Parse Google Custom Search results"""
        
        results = []
        
        for item in data.get("items", []):
            results.append(SearchResult(
                source="google",
                title=item.get("title", ""),
                url=item.get("link", ""),
                snippet=item.get("snippet", ""),
                confidence=0.9,
                relevance=0.8,
                metadata={"displayLink": item.get("displayLink", "")}
            ))
        
        return results
    
    def _parse_bing_results(self, data: Dict[str, Any], query: SearchQuery) -> List[SearchResult]:
        """Parse Bing Search results"""
        
        results = []
        
        for item in data.get("webPages", {}).get("value", []):
            results.append(SearchResult(
                source="bing",
                title=item.get("name", ""),
                url=item.get("url", ""),
                snippet=item.get("snippet", ""),
                confidence=0.9,
                relevance=0.8,
                metadata={"displayUrl": item.get("displayUrl", "")}
            ))
        
        return results
    
    def _deduplicate_results(self, results: List[SearchResult]) -> List[SearchResult]:
        """Loại bỏ kết quả trùng lặp"""
        
        seen_urls = set()
        unique_results = []
        
        for result in results:
            if result.url not in seen_urls:
                unique_results.append(result)
                seen_urls.add(result.url)
        
        return unique_results
    
    def _score_results(self, results: List[SearchResult], query: SearchQuery) -> List[SearchResult]:
        """Tính điểm relevance cho results"""
        
        query_keywords = set(query.query.lower().split())
        
        for result in results:
            # Base relevance score
            relevance_score = result.relevance
            
            # Boost based on keyword matches
            text_to_search = (result.title + " " + result.snippet).lower()
            keyword_matches = sum(1 for keyword in query_keywords if keyword in text_to_search)
            keyword_bonus = (keyword_matches / len(query_keywords)) * 0.3
            
            # Boost based on source credibility
            source_bonus = {
                "google": 0.2,
                "bing": 0.2,
                "github": 0.1,
                "duckduckgo_abstract": 0.15,
                "duckduckgo_related": 0.05
            }.get(result.source, 0.0)
            
            # Update relevance
            result.relevance = min(relevance_score + keyword_bonus + source_bonus, 1.0)
        
        # Sort by relevance
        results.sort(key=lambda r: r.relevance, reverse=True)
        
        return results
    
    def _analyze_results(self, results: List[SearchResult], query: SearchQuery) -> Dict[str, Any]:
        """Phân tích results và tạo summary"""
        
        if not results:
            return {
                "summary": "Không tìm thấy thông tin relevant cho query này.",
                "confidence": 0.0,
                "status": "inconclusive",
                "key_findings": []
            }
        
        # Count high-quality results
        high_quality_count = sum(1 for r in results if r.confidence > 0.7 and r.relevance > 0.7)
        
        # Determine validation status
        if high_quality_count >= 3:
            status = "confirmed"
            confidence = 0.8
        elif high_quality_count >= 1:
            status = "partial"
            confidence = 0.6
        else:
            status = "inconclusive"
            confidence = 0.3
        
        # Extract key findings
        key_findings = []
        for result in results[:3]:  # Top 3 results
            if result.snippet:
                finding = result.snippet[:200] + "..." if len(result.snippet) > 200 else result.snippet
                key_findings.append(f"[{result.source}] {finding}")
        
        # Create summary
        summary = f"Tìm thấy {len(results)} kết quả từ {len(set(r.source for r in results))} nguồn. "
        summary += f"Validation status: {status}. "
        summary += f"Confidence level: {confidence:.2f}."
        
        if query.query_type == "competitor":
            summary += " Đã kiểm tra sự tồn tại của competitors trong thị trường."
        elif query.query_type == "trend":
            summary += " Đã xác thực xu hướng và mức độ phổ biến."
        elif query.query_type == "market_size":
            summary += " Đã tìm kiếm dữ liệu về quy mô thị trường."
        
        return {
            "summary": summary,
            "confidence": confidence,
            "status": status,
            "key_findings": key_findings
        }
    
    async def _enforce_rate_limit(self):
        """Enforce rate limiting"""
        
        now = datetime.now()
        last_request = self._last_request_time.get("global", datetime.min)
        
        time_since_last = (now - last_request).total_seconds()
        min_interval = 1.0  # Minimum 1 second between requests
        
        if time_since_last < min_interval:
            sleep_time = min_interval - time_since_last
            await asyncio.sleep(sleep_time)
        
        self._last_request_time["global"] = datetime.now()
    
    def _get_cache_key(self, query: SearchQuery) -> str:
        """Tạo cache key cho query"""
        return f"{query.query_type}:{hash(query.query)}"
    
    def clear_cache(self):
        """Xóa cache"""
        self._cache.clear()
        logger.info("ESV cache cleared")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Lấy thống kê cache"""
        return {
            "cache_size": len(self._cache),
            "cached_queries": list(self._cache.keys())[:10]  # Show first 10
        }

# Helper functions
def create_search_query(query: str,
                       query_type: str = "general",
                       priority: str = "medium",
                       timeout: int = 30,
                       max_results: int = 10) -> SearchQuery:
    """Helper để tạo SearchQuery"""
    return SearchQuery(
        query=query,
        query_type=query_type,
        priority=priority,
        timeout=timeout,
        max_results=max_results
    )

def extract_keywords_from_text(text: str, max_keywords: int = 5) -> List[str]:
    """Extract keywords từ text để tạo search queries"""
    
    # Simple keyword extraction
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    
    # Filter out common words
    stop_words = {"the", "and", "for", "are", "but", "not", "you", "all", "can", "her", "was", "one", "our", "had", "have", "what", "there", "said", "each", "which", "their", "time", "will", "about", "would", "has", "its", "who", "oil", "sit", "now", "find", "down", "way", "been", "may", "new", "use", "she", "see", "him", "two", "how", "more", "get", "very", "man", "day", "made", "they", "these", "could", "well", "were"}
    
    keywords = [word for word in words if word not in stop_words and len(word) > 3]
    
    # Count frequency
    keyword_freq = {}
    for keyword in keywords:
        keyword_freq[keyword] = keyword_freq.get(keyword, 0) + 1
    
    # Sort by frequency
    sorted_keywords = sorted(keyword_freq.items(), key=lambda x: x[1], reverse=True)
    
    return [keyword for keyword, freq in sorted_keywords[:max_keywords]]

# Test function
async def test_esv_module():
    """Test ESV module functionality"""
    
    logger.info("Testing ESV Module...")
    
    async with ESVModule() as esv:
        # Test queries
        test_queries = [
            create_search_query("AI startup trends 2024", "trend", "high"),
            create_search_query("competitive analysis SaaS", "competitor", "medium"),
            create_search_query("market size fintech", "market_size", "medium")
        ]
        
        results = await esv.validate_multiple(test_queries)
        
        for query, result in results.items():
            print(f"\nQuery: {query}")
            print(f"Status: {result.validation_status}")
            print(f"Confidence: {result.confidence:.2f}")
            print(f"Sources: {result.sources_count}")
            print(f"Summary: {result.summary[:100]}...")

if __name__ == "__main__":
    # Example usage
    async def main():
        await test_esv_module()
    
    asyncio.run(main())
