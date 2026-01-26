# Usage Examples

This guide provides practical examples of how to use VigilantCore for different monitoring scenarios.

## Example 1: Winter Storm & Power Outage Monitoring

Monitor winter storm conditions and potential power outages in your area.

### Configuration

**Settings:**
- Subject: `Winter Storm and Power Outages`
- Monitoring Question: `What is the expected time and date of the highest risk of electric outage in Princeton, NJ during the current winter storm?`
- Location: `Princeton, NJ`
- ZIP Code: `08544`
- Latitude: `40.3431`
- Longitude: `-74.6551`
- Radius: `30 km`
- Polling Interval: `5 minutes`

**Custom RSS Feeds:**
```
https://alerts.weather.gov/cap/nj.php?x=0
https://www.nj.com/news/rss/
https://www.centraljersey.com/search/?f=rss
```

### Expected Output

The insight card will show:
> **Summary:** A winter storm warning is in effect for Mercer County through Tuesday evening. Peak risk for power outages is expected Monday night between 10 PM and 2 AM when wind gusts may reach 45 mph combined with heavy wet snow accumulation.
>
> **Explanation:** PSE&G has prepositioned crews across central New Jersey. The National Weather Service forecasts 8-12 inches of heavy wet snow for the Princeton area. JCP&L and PSE&G outage maps show isolated outages beginning in the region. Based on historical patterns and current conditions, the highest probability of outages coincides with the period of strongest winds and maximum snow load on power lines...

---

## Example 2: Driveway & Road Conditions Monitoring

Track conditions to decide when to clear snow or if travel is safe.

### Configuration

**Settings:**
- Subject: `Snow Accumulation and Road Conditions Princeton NJ`
- Monitoring Question: `Should I clear my driveway now, or should I wait? When is the best time to shovel based on snowfall timing?`
- Location: `Princeton University`
- ZIP Code: `08544`
- Radius: `15 km`
- Polling Interval: `10 minutes`
- News Time Window: `3 hours`

**Custom RSS Feeds:**
```
https://alerts.weather.gov/cap/nj.php?x=0
https://www.weather.gov/rss_page.php?site_name=phi
```

### Expected Output

> **Summary:** Wait until after 6 AM Tuesday to clear your driveway. Snow is expected to continue through 4 AM with an additional 3-4 inches overnight.
>
> **Explanation:** The NWS Philadelphia office forecasts snow tapering off by early Tuesday morning. Current accumulation in Princeton is approximately 6 inches with 3-4 more inches expected overnight. Clearing now would require a second clearing tomorrow. Road crews will begin treating main roads after midnight. Temperature will drop to 18°F by morning, so early clearing is recommended before snow compacts into ice...

---

## Example 3: School & Office Closure Monitoring

Track closings and delays affecting your daily schedule.

### Configuration

**Settings:**
- Subject: `School Closings and Delays Mercer County NJ`
- Monitoring Question: `Are Princeton schools or Mercer County offices closed or delayed due to the winter storm?`
- Location: `Princeton, NJ`
- ZIP Code: `08544`
- Radius: `25 km`
- Polling Interval: `15 minutes`

**Custom RSS Feeds:**
```
https://www.nj.com/mercer/rss/
https://princetoninfo.com/feed/
https://www.centraljersey.com/search/?f=rss
```

### Expected Output

> **Summary:** Princeton Public Schools announced a 2-hour delay for Monday. Mercer County government offices will open at 10 AM.
>
> **Explanation:** As of 9 PM Sunday, Princeton Regional Schools has announced a delayed opening. The district will make a final decision on full closure by 5:30 AM. Mercer County College has moved to remote operations. Princeton University remains open with reduced shuttle service...

---

## Example 4: Utility Status & Restoration Monitoring

Track power restoration efforts during an outage.

### Configuration

**Settings:**
- Subject: `Power Outage and Restoration Princeton NJ`
- Monitoring Question: `When is power expected to be restored in the Princeton 08544 area? How many customers are currently without power?`
- Location: `Princeton, NJ`
- ZIP Code: `08544`
- Radius: `20 km`
- Polling Interval: `5 minutes`

**Custom RSS Feeds:**
```
https://www.nj.com/news/rss/
https://alerts.weather.gov/cap/nj.php?x=0
```

**Enable:**
- DuckDuckGo search: `Yes`
- NewsAPI (if available)

### Expected Output

> **Summary:** Approximately 2,400 PSE&G customers in the Princeton area are without power. Estimated restoration time is Tuesday by 8 PM.
>
> **Explanation:** PSE&G reports crews are actively working in Mercer County. The main cause is downed trees on power lines along Route 206 and in the Riverside area. Priority restoration is focused on critical facilities. Customers can report outages at 1-800-436-7734 or via the PSE&G app...

---

## Example 5: Travel Safety Monitoring

Monitor road conditions before traveling.

### Configuration

**Settings:**
- Subject: `Road Conditions and Travel Advisories New Jersey Turnpike I-95`
- Monitoring Question: `Is it safe to drive from Princeton to Newark Airport (EWR) right now? Are there any travel advisories on I-95 or NJ Turnpike?`
- Location: `Princeton, NJ`
- ZIP Code: `08544`
- Radius: `75 km`
- Polling Interval: `10 minutes`

**Custom RSS Feeds:**
```
https://www.511nj.org/rss/
https://www.nj.com/traffic/rss/
https://alerts.weather.gov/cap/nj.php?x=0
```

### Expected Output

> **Summary:** Travel is not recommended. The New Jersey Turnpike has reduced speed limits to 45 mph with multiple accidents reported. Allow an extra 90 minutes if travel is essential.
>
> **Explanation:** NJDOT reports hazardous conditions on I-95 from Exit 7A to Exit 14. Three accidents have been cleared but residual delays remain. Visibility is reduced to 1/4 mile in heavy snow bands. Newark Airport (EWR) is experiencing 2-hour departure delays. Consider postponing travel until Tuesday afternoon when conditions improve...

---

## Running the Examples

### Start Monitoring

1. Configure settings in the UI or edit `config.json`
2. Start VigilantCore:
   ```bash
   ./run.sh web    # Web dashboard
   # or
   ./run.sh qt     # Desktop app
   ```
3. Visit http://127.0.0.1:8765 (for web)

### View Results

- **Insight Card**: Shows AI-generated answer to your monitoring question
- **Alerts List**: Individual news items with impact scores
- **Data Page**: Full database of collected alerts

### Adjust Settings

If results are too broad or narrow:
- **Too few results**: Enable "Relax location filter" or add more RSS feeds
- **Too many results**: Decrease radius, make subject more specific
- **Irrelevant results**: Make monitoring question more focused

---

## Command Line Quick Reference

```bash
# Start web dashboard (default)
./run.sh

# Start Qt desktop app
./run.sh qt

# Run both (web in background)
./run.sh both

# Check status
./run.sh status

# Stop all instances
./run.sh stop
```

---

## Tips for Best Results

1. **Be specific with your subject** - "Winter Storm Princeton NJ" works better than "Weather"

2. **Craft focused monitoring questions** - Ask specific, answerable questions like "When should I shovel?" rather than "What's the weather?"

3. **Add relevant RSS feeds** - NWS alerts and local news sources improve storm coverage

4. **Adjust timing based on urgency**:
   - Active emergency: 3-5 minute polling
   - Pre-storm monitoring: 15-30 minute polling

5. **Use location filtering wisely**:
   - Tight radius (15-30km) for hyperlocal conditions
   - Wider radius (75km+) for regional travel advisories

6. **Combine data sources**:
   - NWS RSS for official alerts
   - NewsAPI for local news coverage
   - DuckDuckGo for recent web content and utility updates
