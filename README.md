# HORECA Lens

HORECA Lens is a small Flask web app that estimates direct competition for a cafe, restaurant, or hotel at a given address. It geocodes the address, looks up nearby matching venues on OpenStreetMap, and produces a rule-based competition assessment, with an optional PDF report.

## Requirements

- Python 3
- Quarto 

## Setup and run

```
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000 in your browser.

## How the app works

1. **Nominatim geocoding** — the entered address is sent to the Nominatim
   API (`nominatim.openstreetmap.org/search`), which returns a latitude and
   longitude for the address.
2. **Overpass query** — that latitude/longitude is used to query the
   Overpass API for venues tagged with the selected category (e.g.
   `amenity=cafe`) within a 1000 m radius. The app retries on rate-limit and
   gateway errors, falls back to a second Overpass mirror if needed, and
   caches successful results in memory.
3. **Haversine distance** — for each venue returned, the great-circle
   distance from the search point is calculated with the haversine formula,
   and venues are sorted by distance.
4. **Rule-based assessment** — the total venue count and the closest
   distance are passed into a plain Python function that returns a
   competition level plus a nearby-competitor note when applicable. No LLM
   is involved.

## Competition rule

| Matching venues | Competition level |
|---|---|
| 0-1 | Lower observed direct competition |
| 2-4 | Moderate observed direct competition |
| 5+ | Higher observed direct competition |

If the closest matching venue is under 250 m away, the app adds a separate
note that a direct competitor is very nearby.

## Generating the PDF report

After a successful search, click **Generate PDF report** on the results
page. This writes the current search data to `report_data.json` and runs
`quarto render report.qmd`, which reads that JSON file and produces
`report.pdf` (using the `typst` format, so no LaTeX install is required).
The finished PDF is sent to your browser as a download.

## Limitations

- OpenStreetMap data is volunteer-maintained and can be incomplete or out
  of date.
- Distances are straight-line ("as the crow flies"), not walking distance.
- Results are an indication only, not a market survey — validate findings
  with local field research before making any business decision.

## Reflection

### What worked well?

Nominatim geocoding worked on the first attempt and never failed during testing. Separating the logic in app.py from the display in index.html also made it easy to change one without breaking the other. Building in
three stages — search, assessment, report — meant that when something broke I knew which stage caused it.


### What did not work at first?

- Error one(JSONDecodeError):
The code expected a JSON response, but what arrived was HTML. The error message said: app.py line 44, in query_overpass — so it was in the Overpass function, not Nominatim, that told me that geocoding had succeeded and the failure was in the next step.
The code assumed success every time without ever checking whether the request had actually succeeded.

- Error two(429 and 504):
After I added printing of the status code, this showed up:
429 : Too Many Requests: slow down
504: Gateway Timeout: the server is overloaded

That's because Overpass is a free public server serving the whole world. When it's busy it rejects requests and the proof about that is when the exact same request succeeded sometimes and failed other times.

### What is one issue I solved by iterating with the coding harness?

Error two(429 and 504): when the web stopped and gave the JSONDecodeError I brought the harness the full error message and asked it to check the status_code before parsing JSON and then print the case number and a part of the response. The printing showed that the error is from Overpass and not really a code bug because sometimes it works and sometimes it doesn't. The last thing was checking myself if it's now working well by putting two addresses and two categories. The step that actually solved it was asking for the response to be printed, not asking for a fix — without knowing the cause I would have been guessing.

### What is one thing I still do not understand or want to discuss?

- Sassenheim returned 8 restaurants and The Hague returned 105 cafes, but both are labelled higher observed direct competition. Is a fixed count threshold meaningful in a dense city centre?

- If an area is poorly mapped, the app reports few competitors and concludes lower observed direct competition — the opposite of a safe answer. Should the app try to detect low data quality?