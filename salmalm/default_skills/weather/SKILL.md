# Weather
> Get current weather and forecasts for any location.

## Instructions
1. Use `web_fetch` to get weather from wttr.in:
   - Current: `web_fetch(url="https://wttr.in/{city}?format=j1")`
   - Simple: `web_fetch(url="https://wttr.in/{city}?format=3")`
2. Parse the JSON response for temperature, conditions, humidity, wind
3. Present in a clean format with emoji indicators

## Examples
- "What's the weather in Seoul?" → `web_fetch(url="https://wttr.in/Seoul?format=j1")`
- "Will it rain tomorrow in Tokyo?" → Check `weather[1]` in the JSON response
