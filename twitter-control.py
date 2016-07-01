#!/usr/bin/env python
import logging, yaml
import requests
import signal, threading
import sys, time
import twitter

def main():
    global cfg
    global cfgfile
    global log
    global shutdown
    
    # Change to point to your config YAML
    cfgfile = 'config.yml'

    # Leave this False :)
    shutdown = False

    # Logging setup
    log = logging.getLogger()
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('%(asctime)s [%(levelname)-8s] %(name)-12s - %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)
    log.setLevel(logging.DEBUG)
    log.debug('--- Starting ---')
    log.info('Reading config from %s', cfgfile)

    # Load config and setup Twitter API
    with open(cfgfile, 'r') as ymlfile:
        cfg = yaml.load(ymlfile)

    log.info('Config loaded from %s', cfgfile)
    if _check_cfg(cfg) is False:
        return False

    log.info('Looking for DMs starting with \'%s\'. Sending DM replies to user ID %s', cfg['twitter']['command_start_character'], cfg['twitter']['my_id'])
    
    twitter_api = twitter.Api(consumer_key=cfg['twitter']['consumer_key'],
                    consumer_secret=cfg['twitter']['consumer_secret'],
                    access_token_key=cfg['twitter']['access_token'],
                    access_token_secret=cfg['twitter']['access_secret'])

    log.info('Twitter API connected')

    log.debug('Setting up signal handlers')
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    #signal.signal(signal.SIGHUP, signal_handler)
    log.info('Press ^C to save config and exit')

    log.info('Checking Twitter DMs every 2 minutes')
    while True:
        if shutdown is True:
            log.info('Shutdown detected - exiting.')
            return True

        log.debug('Checking Twitter DMs now')
        get_direct_messages(cfg, twitter_api)
        time.sleep(120)

def signal_handler(signum, frame):
    global cfg
    global cfgfile
    global log
    global shutdown

    log.warning('CTRL+C caught - saving the config')
    with open(cfgfile, "w") as ymlfile:
        yaml.dump(cfg, ymlfile, default_flow_style=False)

    shutdown = True

def get_direct_messages(cfg, twitter_api):
    global log

    # Get Direct Messages to myself
    dms = twitter_api.GetDirectMessages(since_id=cfg['twitter']['last_seen'], count=50, include_entities=False, full_text=True)
    dms_sorted = sorted(dms, key=_dm_key)
    log.debug('Got %i DMs', len(dms_sorted))

    changed = False
    for dm in dms_sorted:
        if dm.sender_id == dm.recipient_id:
            log.debug('Found a DM where sender = receiver')

            # Each DM contains commands, one per line
            command_blobs = dm.text.split('\n')

            for command_line in command_blobs:
                # Check the command 'header' exists
                if command_line[0] == cfg['twitter']['command_start_character']:
                    log.debug('DM line begins with command_start_character')
                    
                    # Remove the command_start_character
                    command_line_no_start_char = command_line[1:]

                    # Tokenize the command line by colons ':'
                    # The first part before the first colon denotes the command
                    # The second part after the first colon are the arguments to that command
                    command_line_tokens = command_line_no_start_char.split(':')

                    # Get the last word in the first part of the line
                    # This should be 'show', or 'movie', or 'status', etc... 
                    command = command_line_tokens[0].split(' ')[-1]
                    # Everything to the right of the : is an argument
                    args = command_line_tokens[1:]

                    # Attempt to execute the command
                    _process_command(cfg, twitter_api, command, args)

            # Ensure we don't see this again in the future
            cfg['twitter']['last_seen'] = dm.id
            changed = True

    if changed:
        log.debug('Saving the config - last_seen has changed')
        # Save the config (last_seen has changed)
        with open(cfgfile, "w") as ymlfile:
            yaml.dump(cfg, ymlfile, default_flow_style=False)

def _dm_key(item):
    return item.id

def _process_command(cfg, twitter_api, command, args):
    global log

    command = command.lower()
    args = ''.join(args).strip()
    log.debug('Processing command: %s | %s', command, args)

    dm_msg = 'Something went wrong?'
    if command == 'show' or command == 'series':
        ret, msg = _sonarr_add(cfg, args)
        log.debug('Added show "%s" which returned [%s] with message %s', args, ret, msg)

        dm_msg = msg + ' (' + args + ')'
    elif command == 'movie' or command == 'film':
        if _couchpotato_add(cfg, args):
            log.debug('Movie "%s" added successfully', args)
            dm_msg = 'Movie success (' + args + ')'
        else:
            log.debug('Movie "%s" failed to add', args)
            dm_msg = 'Movie failure (' + args + ')'
    elif command == 'stats' or command == 'status':
        stats = _sab_stats(cfg)
        if stats is not False:
            dm_msg = '--- Server Stats ---\n'
            dm_msg += 'Load: ' + stats['load'] + '\n'
            dm_msg += 'Status: ' + stats['state'] + '\n'
            dm_msg += 'Disk Space Remaining: ' + stats['diskleft'] + '\n'
            dm_msg += 'Download Size Remaining: ' + stats['sizeleft'] + '\n'
            dm_msg += 'Download Speed: ' + stats['speed']
        else:
            dm_msg = 'I couldn\'t get the stats'
            log.debug('Failed to get stats')
    elif command == 'help':
        dm_msg = '[' + cfg['twitter']['command_start_character'] + '] show|series: <name>, movie|film: <IMDB ID>, stats|status, help'
    else:
        dm_msg = 'I\'m not sure what I have to do'

    _send_dm(cfg, twitter_api, dm_msg)
    log.debug('Sent DM reply: %s', dm_msg)

def _send_dm(cfg, twitter_api, message):
    twitter_api.PostDirectMessage(message, cfg['twitter']['my_id'])

def _couchpotato_add(cfg, imdb_movie_id):
    if cfg['couchpotato']['ssl'] is True:
        schema = 'https://'
    else:
        schema = 'http://'

    # CouchPotato API is usually at http://localhost:5050/api/<api key>/
    apiurl = "{schema}{host}:{port}/api/{apikey}".format(schema=schema,
                                                        host=cfg['couchpotato']['host'],
                                                        port=cfg['couchpotato']['port'],
                                                        apikey=cfg['couchpotato']['apikey'])

    fullurl = "{api}/movie.add/?identifier={imdb_movie_id}&profile_id={profile_id}&category_id=-1".format(
                                                        api=apiurl,
                                                        imdb_movie_id=imdb_movie_id,
                                                        profile_id='ed59153d41b148cd827607ddc5d1530e')

    resp = requests.get(url=fullurl)
    data = resp.json()

    if data['success'] is True:
        return True
    else:
        return False

def _sonarr_add(cfg, show_name):
    if cfg['sonarr']['ssl'] is True:
        schema = 'https://'
    else:
        schema = 'http://'

    # Sonarr API is usually at http://localhost:8989/api/
    apiurl = "{schema}{host}:{port}/api".format(schema=schema,
                                                host=cfg['sonarr']['host'],
                                                port=cfg['sonarr']['port'])

    fullurl = "{api}/series/lookup?apikey={apikey}&term={show_name}".format(
                                                        api=apiurl,
                                                        apikey=cfg['sonarr']['apikey'],
                                                        show_name=show_name)

    resp = requests.get(url=fullurl)
    data = resp.json()[0]

    if 'tvdbId' in data:
        # After searching for and finding the Show, we must add it
        fullurl = "{api}/series?apikey={apikey}".format(api=apiurl, apikey=cfg['sonarr']['apikey'])

        # Not sure what these do, but the Sonarr Web UI sets them this way
        data['addOptions'] = {'ignoreEpisodesWithFiles': True,
                              'ignoreEpisodesWithoutFiles': False,
                              'searchForMissingEpisodes': True}

        # Create a folder for each season
        data['seasonFolder'] = True
        
        # Drop the episodes/seasons in this directory when downloaded
        data['rootFolderPath'] = cfg['tv_show_dir']

        # Choose the 720p/1080p quality profile
        data['profileId'] = 6

        # Set every season except for 0 to monitored (again, this is how Sonarr does it)
        for season in data['seasons'][1:]:
            season['monitored'] = True

        resp = requests.post(url=fullurl, json=data)
        data = resp.json()

        # Two success cases: Show gets added or Show is already added, in which case
        # we will get 1 error message back saying precisely that.
        if 'tvdbId' in data:
            return (True, 'Show added to my list')
        elif len(data) == 1:
            if 'propertyName' in data[0] and data[0]['propertyName'] == 'TvdbId':
                if 'errorMessage' in data[0] and  data[0]['errorMessage'] == 'This series has already been added':
                    return (True, 'I already have that show')
        else:
            return (False, 'Something weird happened when trying to add the show')
    else:
        return (False, 'I couldn\'t find that show, sorry')

def _sab_stats(cfg):
    if cfg['sab']['ssl'] is True:
        schema = 'https://'
    else:
        schema = 'http://'

    # SABnzbd API is usually at http://localhost:8080/sabnzbd/api?apikey=<api key>
    apiurl = "{schema}{host}:{port}/sabnzbd/api?apikey={apikey}".format(schema=schema,
                                                        host=cfg['sab']['host'],
                                                        port=cfg['sab']['port'],
                                                        apikey=cfg['sab']['apikey'])

    fullurl = "{api}&mode=queue&start=0&limit=-1&output=json".format(api=apiurl)

    resp = requests.get(url=fullurl)
    data = resp.json()

    if 'queue' in data:
        return dict(sizeleft=data['queue']['sizeleft'],
                    diskleft=data['queue']['diskspace1_norm'],
                    state=data['queue']['status'],
                    speed=data['queue']['speed'],
                    load=data['queue']['loadavg'])
    else:
        return False

def _check_cfg(cfg):
    global cfgfile
    global log
    
    if ('twitter' not in cfg or
        'tv_show_dir' not in cfg or
        'consumer_key' not in cfg['twitter'] or
        'consumer_secret' not in cfg['twitter'] or
        'access_token' not in cfg['twitter'] or
        'access_secret' not in cfg['twitter'] or
        'my_id' not in cfg['twitter'] or
        cfg['tv_show_dir'] == '' or
        cfg['twitter']['consumer_key'] == '' or
        cfg['twitter']['consumer_secret'] == '' or
        cfg['twitter']['access_token'] == '' or
        cfg['twitter']['access_secret'] == '' or
        cfg['twitter']['my_id'] == ''
        ):
            log.error('Config file %s is incomplete. Exiting', cfgfile)
            return False
    else:
        return True
        
if __name__ == '__main__':
    main()
