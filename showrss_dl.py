#!/usr/bin/env python3


"""
https://github.com/mllg/showrss_dl
"""
__version__ = '0.2'


import argparse
import feedparser
import atexit
import re
import subprocess
from urllib.request import urlretrieve
from pickle import load, dump
from os import path
from os import getcwd
from sys import exit, stdout, stderr


class ConsoleOutput:
    def __init__(self, verbose):
       self.verbose = verbose
    def info(self, msg):
        if self.verbose:
            stdout.write('[INFO] %s\n' % msg)
            stdout.flush()
    def warn(self, msg):
        stdout.write('[WARN] %s\n' % msg)
        stdout.flush()
    def error(self, msg, exit_code = 1):
        stderr.write('[ERROR] %s\n' % msg)
        stderr.flush()
        exit(exit_code)


class RotatingCache:
    cachesize = 120
    needsupdate = False
    def __init__(self, fn):
        self.fn = path.expanduser(fn)
        self.items = []
        if path.exists(self.fn):
            with open(self.fn, 'rb') as f:
                self.items = load(f)
    def add(self, new):
        self.items.append(new)
        self.needsupdate = True
    def write(self):
        if self.needsupdate:
            with open(self.fn, 'wb') as f:
                dump(self.items[-self.cachesize:], f)


class SendMagnet:
    msg = None
    cmd = ['transmission-remote']
    pat = re.compile(r'xt=urn:btih:([^&/]+)')
    def __init__(self, auth):
        if auth is not None:
            self.cmd += ['--auth', auth]
    def send(self, link):
        if not link[:7] == 'magnet:':
            self.msg = 'Malformed magnet link (%s)' % link
            return False
        if self.pat.search(link) is None:
            self.msg = 'No hash in magnet link (%s)' % link
            return False
        
        try:
            subprocess.check_output(self.cmd + ['--add', link], stderr = subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            print(e.output)
            self.msg = 'Error sending to transmission (%s)' % str(e.output)
            return False
        except (OSError, Exception) as e:
            self.msg = 'Error sending to transmission (%s)' % e
            return False
        return True


class SendTorrent:
    msg = None
    def __init__(self, dir):
        self.dir = path.expanduser(dir)
    def send(self, link):
        try:
            fn = path.join(self.dir, path.basename(link.strip('/')))
            urlretrieve(link, fn)
        except Exception as e:
            self.msg = 'Error fetching torrent (%s)' % e
            return False
        return True


# parse arguments
parser = argparse.ArgumentParser(description = 'showRSS downloader')
parser.add_argument('--watchdir',
        default = getcwd(),
        help = 'Directory to store torrent files, defaults to current directory.')
parser.add_argument('--auth',
        default = None,
        help = 'RPC authentication for transmission-remote as <user:passwd>.' +  
               'Only required for magnet links. Defaults to no authentication.')
parser.add_argument('--verbose',
        action = 'store_true',
        help = 'Be more verbose. Helpful for debugging.')
parser.add_argument('--cachefile',
        default = '~/.showrss_cache',
        help = 'File to store known torrent ids. Default is "~/.showrss_cache".')
parser.add_argument('feed', metavar = 'feed', nargs = '?', type = str,
        help = 'showRSS feed with magnet links as generated on the website.')
args = parser.parse_args()

# set up simple console output
out = ConsoleOutput(args.verbose)

# add namespace=true to the feed url if it is missing
feed = args.feed
if feed.find('namespaces=true') == -1:
    feed += '&namespaces=true'

out.info("Using feed: %s" % feed)

# initialize the cache
if path.exists(args.cachefile) and path.isdir(args.cachefile):
    out.error('Argument cachefile points to a directory ("%s")' % args.cachefile)
cache = RotatingCache(args.cachefile)
atexit.register(cache.write)

# determine the mode: torrents to store or magnets to send directly
magnets = feed.find('magnets=true') > -1
if magnets:
    handler = SendMagnet(args.auth)
else:
    if not path.isdir(args.watchdir):
        out.error('Directory "%s" not found or file in place' % args.watchdir)
    handler = SendTorrent(args.watchdir)

# get the feed
feed = feedparser.parse(feed)
if feed.bozo:
    out.error('Bozo feed in "%s" (%s)' % (feed, feed.bozo_exception.getMessage()))

# iterate over the entries
for entry in reversed(feed.entries):
    if not entry.has_key('title'):
        out.warn('Item with missing title found ... skipping')
        continue
    title = entry['title']
    
    if not entry.has_key('link'):
        out.warn('Entry "%s": no link available ... skipping' % title)
        continue
    link = entry['link']

    if not entry.has_key('showrss_episode'):
        out.warn('Entry "%s": no episode id available ... skipping' % title)
        continue
    id = entry['showrss_episode']
    
    if id in cache.items:
        out.info('Entry "%s" already downloaded ... skipping' % title)
        continue
    
    if not handler.send(link):
        out.warn('Entry "%s": %s ... skipping' % (title, handler.msg))
    else:
        cache.add(id)

exit(0)
