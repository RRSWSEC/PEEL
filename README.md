# PEEL: Parse, Enumerate, Enrich, Log
You give it anything — a database, a text file, a CSV, a URL, a single address — in any format, any delimiter, any mess. 

It pulls out every valid onion address, checks each one for life through Tor, scrapes all available text metadata from the page, and writes everything to a clean timestamped CSV.

One script. No config. No database required. Works standalone anywhere you have Python and Tor.

# install dependency (only one)
pip install requests PySocks --break-system-packages

# make it executable
chmod +x peel.py

# Basic usage:
bash./peel.py onions.db                        # SQLite DB — alive addresses only
./peel.py targets.txt                      # any text file
./peel.py dump.csv                         # CSV, HTML, JSON — anything
./peel.py https://dark.fail                # live URL fetched through Tor
./peel.py abc123xyzabc123x.onion           # single address
# With options:
bash./peel.py onions.db --workers 30           # more parallel workers (default 20)
./peel.py targets.txt --timeout 15         # tighter per-request timeout (default 30s)
./peel.py targets.txt --no-scrape          # alive check only, skip HTML
./peel.py targets.txt --out results.csv    # custom output filename

# check a paste of onion links someone shared
./peel.py ~/downloaded_list.txt --workers 40 --timeout 20

# pull and check whatever dark.fail is currently listing
./peel.py https://dark.fail --out darkfail_$(date +%Y%m%d).csv

# quick alive check on a single site, no scraping
./peel.py duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczad.onion --no-scrape
Output always lands in enriched_<source>_<timestamp>.csv so repeated runs never overwrite each other.
