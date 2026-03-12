## PEEL - Parse, Enumerate, Enrich, Log

PEEL accepts almost any input format and extracts valid Tor .onion addresses from it.  
Supported inputs include databases, text files, CSV files, URLs, or even a single address.

The tool parses the input, identifies valid onion addresses, checks whether each service is reachable through Tor, and optionally collects basic text metadata from the page such as titles and visible text elements. Results are written to a clean, timestamped CSV file.

PEEL is designed to run as a simple standalone script. It requires only Python and a running Tor service. No database or external configuration is required.

# CSAM detection and safety

This tool was originally created to help researchers quickly determine whether onion services in large lists are alive or dead, and to sort them by page title or keywords. The scraper intentionally avoids downloading or processing images and video.

By limiting collection to text metadata only, PEEL helps investigators filter suspicious services without directly exposing themselves to illegal or psychologically harmful material. This workflow can assist researchers in responsibly identifying and reporting illegal content such as CSAM to appropriate authorities while minimizing accidental exposure.

# Dependencies

PEEL requires Python along with the requests and PySocks libraries, as well as a working Tor installation.

# Example dependency installation:

pip install requests PySocks --break-system-packages

Example Tor installation (Debian / Ubuntu systems):

sudo apt update  
sudo apt install apt-transport-https gnupg -y  

wget -qO- https://deb.torproject.org/torproject.org/A3C4F0F979CAA22CDBA8F512EE8CBC9E886DDD89.asc \
| gpg --dearmor \
| sudo tee /usr/share/keyrings/deb.torproject.org-keyring.gpg >/dev/null  

Add the Tor repository for your Debian version to  
/etc/apt/sources.list.d/tor.sources (deb822 format).

sudo apt update  
sudo apt install tor deb.torproject.org-keyring -y  

The Tor daemon starts automatically after installation.  
Service management can be handled with systemctl if needed.

# Running the script

Make the script executable:

chmod +x peel.py

# Basic usage examples

*Scan a SQLite database containing onion addresses:*

./peel.py onions.db

*Scan any text file containing addresses:*

./peel.py targets.txt

*Scan a CSV or structured data dump:*

./peel.py dump.csv

*Fetch and parse a live site through Tor:*

./peel.py https://dark.fail

*Check a single onion service:*

./peel.py abc123xyzabc123x.onion

# Optional parameters

*Increase parallel workers:*

./peel.py onions.db --workers 30

*Adjust request timeout:*

./peel.py targets.txt --timeout 15

*Check service availability only (skip scraping):*

./peel.py targets.txt --no-scrape

*Specify a custom output file:*

./peel.py targets.txt --out results.csv

# Example workflows

*Checking a shared paste or downloaded list of onion links:*

./peel.py ~/downloaded_list.txt --workers 40 --timeout 20

*Pulling and checking whatever services are currently listed on dark.fail:*

./peel.py https://dark.fail --out darkfail_$(date +%Y%m%d).csv
