twitter-control
===============

A vaguely named bot which looks for DMs you send to yourself in order to remotely control Sonarr, CouchPotato, and SABnzbd.

Installation
------------

Dependencies:

* pip
  * python-requests
  * PyYAML
  * python-twitter
* supervisord

```
# cd /opt
# git clone https://github.com/vladionescu/twitter-control.git
# pip install -r requirements.txt
```

```
# cd /opt/twitter-control
# cp supervisord.conf /etc/supervisord.conf
# cp config.yml.sample config.yml
# echo "Edit config.yml please"
# systemctl restart supervisord
```

This script is maintained with `supervisord` (a sample `supervisord.conf` is included) which expects the script to live in /opt. The included `supervisord.conf` attempts to run the script as the `plex` user.

The included `config.yml.sample` will fail if you try to run the script as-is. The script expects a `config.yml` file in the same directory. Please add the relevant API keys and your Twitter user ID (numeric) to `config.yml` or the script will print an error and exit.

If using `supervisord` then after installing the `.conf` do

```# supervisorctl start twitter-control```

Logs are printed to stdout/stderr. If using the included `supervisord.conf` they will live in /opt/twitter-control/logs.

Commands
--------

Commands are ingested from a DM where the sender == the receiver. Each DM can be a multiline message. Each line is processed separately.

Lines will only be processed if they begin with the `command_start_character` specified in `config.yml`. If you don't want this functionality, leave that option blank.

* help - prints the available commands in an abbreviated form
* stats or status - prints SABnzbd server info (load avgs, downloading/paused state, disk space remaining, size left to download, and download speed)
* show: <name> or series: <name> - searches for <name> in Sonarr and adds the show if found
* movie: <IMDB ID> or film: <IMDB ID> - adds the film denoted by it's IMDB ID to CouchPotato
* pause or resume - stops and starts SABnzbd **NOT IMPLEMENTED YET

Example DM chat:

```
Me: ~stats

Me: --- Server Stats ---
    Load: 0.08 | 0.05 | 0.01 | V=2594M R=202M
    Status: Downloading
    Disk Space Remaining: 57.5 G
    Download Size Remaining: 8.5 GB
    Download Speed: 397 K

Me: ~show: seinfeld

Me: Show added to my list (seinfeld)
```
