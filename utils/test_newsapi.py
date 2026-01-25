#!/usr/bin/env python3
"""
NewsAPI testing utility for VigilantCore application.
Provides comprehensive testing and data retrieval capabilities.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

# Add parent directory to path to allow importing from utils
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.config import load_config

logger = logging.getLogger(__name__)


class NewsAPITester:
    """Test NewsAPI connectivity and capture response data."""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize with optional API key."""
        config = load_config()
        self.api_key = api_key or config.news_api_key or os.getenv("NEWS_API_KEY")
        self.base_url = "https://newsapi.org/v2/everything"
        
    def test_api_connectivity(self, search_query: str = "bitcoin") -> Dict[str, Any]:
        """
        Test NewsAPI connectivity and capture full response data.
        
        Args:
            search_query: Query string to search for news
            
        Returns:
            Dictionary containing test results and API response data
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        test_results = []
        overall_status = "PASS"
        
        # Test with API key if available
        if self.api_key:
            result = self._test_with_api_key(search_query)
            test_results.append(result)
            if result["status"] == "FAIL":
                overall_status = "FAIL"
        else:
            # Test without API key (should get 401)
            result = self._test_without_api_key(search_query)
            test_results.append(result)
            if result["status"] == "FAIL":
                overall_status = "FAIL"
        
        return {
            "timestamp": timestamp,
            "overall_status": overall_status,
            "search_text": search_query,
            "total_tests": len(test_results),
            "tests": test_results
        }
    
    def _test_with_api_key(self, search_query: str) -> Dict[str, Any]:
        """Test NewsAPI with authentication key."""
        headers = {"X-Api-Key": self.api_key}
        params = {
            "q": search_query,
            "pageSize": 50,
            "sortBy": "popularity",
            "language": "en"
        }
        
        try:
            with httpx.Client(timeout=20.0) as client:
                response = client.get(self.base_url, params=params, headers=headers)
                
                if response.status_code == 200:
                    api_data = response.json()
                    total_results = api_data.get("totalResults", 0)
                    articles_count = len(api_data.get("articles", []))
                    
                    return {
                        "name": "newsapi_with_key",
                        "status": "PASS",
                        "description": "Test NewsAPI with authentication key",
                        "details": f"HTTP {response.status_code} - Found {total_results} total results, {articles_count} articles returned",
                        "api_response": api_data
                    }
                else:
                    return {
                        "name": "newsapi_with_key",
                        "status": "FAIL",
                        "description": "Test NewsAPI with authentication key",
                        "details": f"HTTP {response.status_code} - Expected 200",
                        "api_response": response.json() if self._is_json_response(response) else {"raw": response.text}
                    }
                    
        except Exception as e:
            logger.exception("NewsAPI request with key failed")
            return {
                "name": "newsapi_with_key",
                "status": "FAIL",
                "description": "Test NewsAPI with authentication key",
                "details": f"Request failed: {str(e)}",
                "api_response": {"error": str(e)}
            }
    
    def _test_without_api_key(self, search_query: str) -> Dict[str, Any]:
        """Test NewsAPI without authentication key (should return 401)."""
        params = {
            "q": search_query,
            "pageSize": 50,
            "sortBy": "popularity",
            "language": "en"
        }
        
        try:
            with httpx.Client(timeout=20.0) as client:
                response = client.get(self.base_url, params=params)
                
                if response.status_code == 401:
                    return {
                        "name": "newsapi_without_key",
                        "status": "PASS",
                        "description": "Test NewsAPI without authentication key",
                        "details": f"HTTP {response.status_code} - Expected unauthorized response",
                        "api_response": response.json() if self._is_json_response(response) else {"raw": response.text}
                    }
                else:
                    return {
                        "name": "newsapi_without_key",
                        "status": "FAIL",
                        "description": "Test NewsAPI without authentication key",
                        "details": f"HTTP {response.status_code} - Expected 401",
                        "api_response": response.json() if self._is_json_response(response) else {"raw": response.text}
                    }
                    
        except Exception as e:
            logger.exception("NewsAPI request without key failed")
            return {
                "name": "newsapi_without_key",
                "status": "FAIL",
                "description": "Test NewsAPI without authentication key",
                "details": f"Request failed: {str(e)}",
                "api_response": {"error": str(e)}
            }
    
    def _is_json_response(self, response: httpx.Response) -> bool:
        """Check if response contains JSON data."""
        content_type = response.headers.get("content-type", "")
        return "application/json" in content_type
    
    def save_results(self, results: Dict[str, Any], output_path: Optional[str] = None) -> str:
        """
        Save test results to JSON file.
        
        Args:
            results: Test results dictionary
            output_path: Optional custom output path
            
        Returns:
            Path where results were saved
        """
        if output_path is None:
            # Default to tests/results.json in project root
            project_root = Path(__file__).parent.parent
            output_path = project_root / "tests" / "python_results.json"
        else:
            output_path = Path(output_path)
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        return str(output_path)
    
    def display_results(self, results: Dict[str, Any]) -> None:
        """Display results in a formatted way."""
        print("\n" + "="*60)
        print(f"NewsAPI Test Results - {results['timestamp']}")
        print("="*60)
        
        for test in results["tests"]:
            status_symbol = "✅" if test["status"] == "PASS" else "❌" if test["status"] == "FAIL" else "⏭️"
            print(f"\n{status_symbol} {test['name'].upper()}")
            print(f"   Description: {test['description']}")
            print(f"   Details: {test['details']}")
            
            if "api_response" in test and isinstance(test["api_response"], dict):
                if "totalResults" in test["api_response"]:
                    print(f"   Total Results Available: {test['api_response']['totalResults']}")
                if "articles" in test["api_response"]:
                    articles = test["api_response"]["articles"]
                    print(f"   Articles Returned: {len(articles)}")
                    if articles:
                        print("   Sample Articles:")
                        for i, article in enumerate(articles[:3]):  # Show first 3
                            print(f"     {i+1}. {article.get('title', 'No title')}")
                            print(f"        Source: {article.get('source', {}).get('name', 'Unknown')}")
                            print(f"        Published: {article.get('publishedAt', 'Unknown')}")
        
        print(f"\n{'='*60}")
        print(f"Overall Status: {results['overall_status']} | Tests: {results['total_tests']} | Search: '{results['search_text']}'")
        print("="*60)


def main():
    """Command line interface for testing NewsAPI."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test NewsAPI connectivity and capture data")
    parser.add_argument("search_query", nargs="?", default="bitcoin", 
                       help="Search query (default: bitcoin)")
    parser.add_argument("--api-key", help="NewsAPI key (overrides config)")
    parser.add_argument("--output", help="Output file path for JSON results")
    parser.add_argument("--quiet", action="store_true", help="Only output JSON, no formatted display")
    
    args = parser.parse_args()
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    
    # Run tests
    tester = NewsAPITester(api_key=args.api_key)
    results = tester.test_api_connectivity(args.search_query)
    
    # Save results
    output_path = tester.save_results(results, args.output)
    if not args.quiet:
        print(f"Results saved to: {output_path}")
        tester.display_results(results)
    else:
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()