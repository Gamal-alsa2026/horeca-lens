# HORECA Competition Lens — Project Explained

Reference document for everything we built. Use it to revise before the workshop and to write the README.

---

## 1. What we actually built

A web app that runs only on your machine (not deployed). What it does:

You enter an address, pick a category (cafe / restaurant / hotel) → it shows the 5 closest matching places within a 1 km radius, gives a competition assessment, and has a button that turns all of it into a PDF.

The practical idea: someone wants to open a cafe and needs to see how many cafes already exist nearby before deciding.

---

## 2. The files

```
horeca-lens/
├─ app.py                 ← the brain: all the logic
├─ templates/index.html   ← the face: what you see in the browser
├─ report.qmd             ← the report template
├─ report_data.json       ← generated at runtime (the handoff box)
├─ requirements.txt       ← list of required libraries
└─ prompts.txt / fix.txt / stage2.txt / stage3.txt  ← record of our work
```

### Why separate `app.py` from `index.html`?

This is an old, well-known pattern called **separation of logic and presentation**:
- `app.py` thinks and calculates
- `index.html` only displays

If you mix them, any change to the look risks breaking the calculations and vice versa. Flask uses an engine called **Jinja2** that lets HTML display variables coming from Python (like a loop that walks the results and produces one table row for each).

---

## 3. The journey of one click

When you press Search, five steps happen in order:

**1.** The browser sends the address and category to `app.py`

**2. Nominatim** — you give it `"Hoofdstraat, Sassenheim"`, it returns `52.2245, 4.5210`

Because maps don't understand addresses, only coordinates. This process is called **geocoding**.

**3. Overpass** — you give it the coordinates + `amenity=restaurant` + a 1000 m radius, it returns every mapped restaurant

**4. Haversine** — calculates the distance to each place, sorts by nearest, takes the first five

**5.** Displays the result

---

## 4. Nominatim vs Overpass

Both are OpenStreetMap services, but they do completely different jobs:

| | Takes | Returns |
|---|---|---|
| **Nominatim** | a text address | coordinates |
| **Overpass** | coordinates + a type | a list of places |

**Nominatim** = an address translator
**Overpass** = a search engine inside the map

Two separate services, separate servers, and each can fail on its own. That's what helped us during the error: the line number told us Nominatim had worked and the problem was in Overpass.

---

## 5. Tags — how OSM classifies places

OpenStreetMap is a map built by **volunteers**, not a company. Every place has tags — `key = value` pairs.

A restaurant on the map looks like this:

```
amenity  = restaurant
name     = Op Eigen Wijze
website  = https://www.opeigenwijze.nl/
```

The `amenity` tag means "public facility", and the value defines the type:

| Our category | OSM tag |
|---|---|
| cafe | `amenity=cafe` |
| restaurant | `amenity=restaurant` |
| hotel | `tourism=hotel` |

**Watch the hotel** — the key is different (`tourism`, not `amenity`), because OSM classifies hotels as tourism rather than facilities. That's why the code stores the key and value together:

```python
TAG_MAP = {
    "cafe":       ("amenity", "cafe"),
    "restaurant": ("amenity", "restaurant"),
    "hotel":      ("tourism", "hotel"),
}
```

### And here's why some website fields are empty

In The Hague, three cafes came back with no website (`—`). Why? Because the volunteer who added them filled in the name and location and never completed the rest.

**This is exactly the core of the limitations statement:** the data is incomplete because volunteers build it, not an official commercial survey. There may well be a cafe that exists in reality and isn't mapped at all. That's why the report says "indication", not "final answer".

---

## 6. `nwr` and `out center` — an important detail

In the query we wrote `nwr`, not `node`. Why?

OSM stores things in three forms:
- **node** = a single point (a small cafe marked as a dot)
- **way** = a line or polygon (a restaurant building drawn with its outline)
- **relation** = a composite group (a hotel spanning several buildings)

If we had written only `node`, we'd lose every restaurant drawn as a building — and those are common. `nwr` = all three.

And `out center;` means: for shapes that aren't points, give me their centre point. Without it, ways and relations come back with no coordinates and we can't calculate distance.

---

## 7. Haversine — why not Pythagoras

Distance between two points on a flat surface = Pythagoras. But the Earth is a **sphere**, and the error grows the further apart the points are.

**Haversine** is a formula that calculates distance on a spherical surface from latitude and longitude. It's written directly in the code (a few lines) rather than pulling in a whole library for it.

The distance we calculate is **straight-line** — a straight line on the map, not walking distance. So 365 m in the report might be 500 m of actual walking. That belongs in the limitations too.

---

## 8. The errors we hit (most important part for the workshop)

### Error one: `JSONDecodeError`

```
requests.exceptions.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```

**What happened:** the code expected a JSON response, but what arrived was HTML.

**How we located it:** the error message said `app.py line 44, in query_overpass` — so it was in the Overpass function, not Nominatim. That told us geocoding had succeeded and the failure was in the next step.

**Root cause:** the code assumed success every time. It called `resp.json()` without ever checking whether the request had actually succeeded.

### Error two: `429` and `504`

After we added printing of the status code, this showed up:

```
status=429  ← Too Many Requests: slow down
status=504  ← Gateway Timeout: the server is overloaded
```

**Cause:** Overpass is a free public server serving the whole world. When it's busy it rejects requests. The proof: the exact same request succeeded sometimes and failed other times — **not a bug in the code, a problem with an external service.**

### The fixes we applied

| Fix | What it does |
|---|---|
| **Check status_code** | Don't try to parse JSON unless the response actually succeeded |
| **Retry with backoff** | Retries 3 times, waiting 2 then 4 then 8 seconds |
| **Fallback mirror** | If the first server keeps failing, try a second one |
| **Cache** | Stores the result in memory, so repeating the same search doesn't hit the API |
| **Clear message** | If everything fails, a readable message instead of a stack trace |

**Exponential backoff** = the wait doubles each attempt. The logic: if a server is overloaded, hammering it at the same rate won't help — you give it progressively more room.

### The lesson (put this in the reflection)

> Any external API can fail intermittently, and any code that depends on an external service must handle the possibility of failure rather than assume success.

---

## 9. Quarto and the report

**Quarto** is a tool that takes a text file written in Markdown + Python code, runs the code, merges its output into the text, and produces a PDF.

The benefit: the report isn't written by hand. Change the data → the report updates automatically without editing a single character.

### Why `format: typst` and not `format: pdf`?

This one saved us a lot of time:

- `format: pdf` → needs **LaTeX** installed (a huge download and a lot of installation trouble)
- `format: typst` → **Typst** ships inside Quarto, works immediately

Both produce a PDF. The difference is the engine that builds it.

### Why JSON between the app and the report?

Instead of passing data around as complicated arguments, we did this:

```
app.py  →  writes report_data.json  →  report.qmd reads it  →  PDF
```

Simpler, and you can open `report_data.json` yourself and see exactly what was sent — which makes debugging much easier when something goes wrong.

### `subprocess` — what it is

`app.py` runs the command `quarto render report.qmd` as if you had typed it in the terminal yourself. `subprocess` is the Python tool that lets one program run another program.

---

## 10. The rule-based assessment

The rule:

| Count within 1 km | Assessment |
|---|---|
| 0–1 | Lower observed direct competition |
| 2–4 | Moderate observed direct competition |
| 5 or more | Higher observed direct competition |
| Closest < 250 m | + note: a direct competitor is very nearby |

### Why did the assignment insist this **not** be an LLM?

This is a deliberate teaching point:

- **A transparent rule:** you can explain why it said "higher" — 8 is greater than 5, done. And it gives the same answer every time.
- **An LLM:** gives you nicer phrasing, but might change its mind, and might add a claim that isn't grounded in your data.

The principle: **an auditable judgment is not the place for an LLM.** The LLM is optional for nice wording; the rule stays the reference.

### One small but important point

The function that computes the assessment is **a single one**, used by both the web page and the report. If it were duplicated in two places, you could edit one and forget the other, and the screen would say one thing while the report said another. This is the **single source of truth** principle.

---

## 11. Why we built it in stages

We didn't hand Claude Code the whole assignment at once. We split it:

1. Search and display
2. Rule-based assessment
3. PDF report

**The reason:** if you give it everything and something breaks, you don't know where. In stages, each error shows up in a specific place and you know what caused it.

The same principle applied to fixing: every time we gave it **the real, complete error message** plus a specific request. Not "it doesn't work, fix it".

---

## 12. Quick glossary

| Term | Meaning |
|---|---|
| **Flask** | A Python library for building websites |
| **API** | An interface that lets one program request data from another service |
| **JSON** | A text format for exchanging data between programs |
| **geocoding** | Converting an address → coordinates |
| **endpoint** | A specific address inside an API that you talk to |
| **status code** | A number saying whether the request worked: 200 success, 429 too many requests, 504 server overloaded |
| **timeout** | The maximum wait before you treat a request as failed |
| **User-Agent** | Identifying yourself to the server — Nominatim rejects requests without it |
| **cache** | Storing a result temporarily so you don't repeat the same request |
| **traceback** | The chain of errors from deepest to shallowest — **read it bottom-up** |
| **localhost / 127.0.0.1** | Your own machine. The site runs only for you |
| **subprocess** | Running one program from inside another |

---

