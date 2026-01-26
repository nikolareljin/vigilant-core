#!/usr/bin/env python3
"""
Test integration with the existing MonitorEngine NewsAPI functionality.
This demonstrates that the codebase already has proper NewsAPI integration.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add parent directory to path to allow importing from project modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.monitor import MonitorEngine
from utils.config import load_config


async def test_monitor_engine_newsapi():
    """Test the existing MonitorEngine NewsAPI integration."""
    
    config = load_config()
    if not config.news_api_key:
        print("❌ No NewsAPI key found in configuration")
        print("   Please set NEWS_API_KEY environment variable or configure through the app")
        return
        
    print("🔧 Testing MonitorEngine NewsAPI integration...")
    print(f"   Search subject: {config.subject}")
    print(f"   Location: {config.location_name}")
    print(f"   Time window: {config.news_time_window_hours} hours")
    
    # Create monitor engine instance
    engine = MonitorEngine(config)
    
    try:
        # Fetch news items using the actual engine code
        items = await engine.fetch_news_api_items()
        
        print("\n✅ MonitorEngine NewsAPI Test Results:")
        print(f"   Items retrieved: {len(items)}")
        
        if items:
            print("   Sample articles:")
            for i, item in enumerate(items[:3]):
                print(f"     {i+1}. {item.title}")
                print(f"        Source: {item.source}")
                print(f"        URL: {item.url}")
                print(f"        Published: {item.published_at or 'Unknown'}")
                if item.snippet:
                    snippet = item.snippet[:100] + "..." if len(item.snippet) > 100 else item.snippet
                    print(f"        Description: {snippet}")
                print()
        
        # Create a summary report
        report = {
            "timestamp": str(asyncio.get_event_loop().time()),
            "engine_test": "PASS" if items else "FAIL",
            "config": {
                "subject": config.subject,
                "location_name": config.location_name,
                "time_window_hours": config.news_time_window_hours,
                "sort_by": config.news_sort_by
            },
            "results": {
                "total_items": len(items),
                "items": [
                    {
                        "title": item.title,
                        "source": item.source,
                        "url": item.url,
                        "published_at": item.published_at,
                        "snippet": item.snippet
                    } for item in items[:10]  # Store first 10 items
                ]
            }
        }
        
        # Save report
        output_path = Path(__file__).parent.parent / "tests" / "monitor_engine_results.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
            
        print(f"📄 Detailed results saved to: {output_path}")
        
    except Exception as e:
        print(f"❌ MonitorEngine test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_monitor_engine_newsapi())
