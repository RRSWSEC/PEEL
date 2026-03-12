# PEEL: Parse, Enumerate, Enrich, Log
You give it anything — a database, a text file, a CSV, a URL, a single address — in any format, any delimiter, any mess. 

It pulls out every valid onion address, checks each one for life through Tor, scrapes all available text metadata from the page, and writes everything to a clean timestamped CSV.

One script. No config. No database required. Works standalone anywhere you have Python and Tor.

**CSAM-DETECTION AND SAFETY: Created for checking Tor lists for Alive/dead status, sorting by page title. Does not touch images or video.  Initially used to report CSAM for Interpol. Avoids/significantly reduces accidental exposure to CSAM when exploring lists of .onion's by being able to sort or filter out by keywords.** This helps non-leo investigators stay legal and avoid psychological harm.

# install dependencies (making a lot of assumptions)
pip install requests PySocks --break-system-packages
Install prerequisites: sudo apt update && sudo apt install apt-transport-https gnupg -y.
Add GPG key: wget -qO- https://deb.torproject.org/torproject.org/A3C4F0F979CAA22CDBA8F512EE8CBC9E886DDD89.asc | gpg --dearmor | sudo tee /usr/share/keyrings/deb.torproject.org-keyring.gpg >/dev/null.
Configure repository: Add the repository for your Debian version to /etc/apt/sources.list.d/tor.sources (using deb822 format).
Install tor: sudo apt update && sudo apt install tor deb.torproject.org-keyring -y.
Manage Service: The daemon starts automatically; use sudo systemctl for management. 

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

# example pull and check whatever dark.fail is currently listing
./peel.py https://dark.fail --out darkfail_$(date +%Y%m%d).csv
