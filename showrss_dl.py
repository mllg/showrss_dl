#!/usr/bin/env python3


"""
https://github.com/mllg/showrss_dl
"""
__version__ = '0.3'


import argparse
import feedparser
import atexit
import subprocess
from pickle import load, dump
from os import path
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
            self.needsupdate = False

# parse arguments
parser = argparse.ArgumentParser(description = 'showRSS downloader')
parser.add_argument('--host',
        default = 'localhost',
        help = 'Base directory for downloaded files, defaults to transmission\'s default download directory')
parser.add_argument('--destination',
        default = None,
        help = 'Base directory for downloaded files, defaults to transmission\'s default download directory')
parser.add_argument('--auth',
        default = None,
        help = 'RPC authentication for transmission-remote as <user:passwd>.' +  
               'Only required for magnet links. Defaults to no authentication.')
parser.add_argument('--verbose',
        action = 'store_true',
        help = 'Be more verbose.')
parser.add_argument('feed', metavar = 'feed', nargs = 1,
        help = 'showRSS feed with magnet links as generated on the website.')
args = parser.parse_args()
feed = args.feed[0]



# set up simple console output logger
out = ConsoleOutput(args.verbose)


# try to send command to server
cmd = ['transmission-remote', args.host]
if args.auth is not None:
    cmd += ['--auth', args.auth]
try:
    lines = subprocess.check_output(cmd + ['-si'], stderr = subprocess.STDOUT, shell = True)
except subprocess.CalledProcessError as e:
    out.error('Error retrieving session info: %e' % e.decode())
except Exception as e:
    out.error('Error retrieving session info: %e' % e)


# determine destination directory
if args.destination is None:
    lines = lines.decode().split('\n')
    lines = list(filter(lambda x: 'Download directory:' in x, lines))
    if len(lines) != 1:
        out.error('Error determining download base dir: %s' % e)
    args.destination = lines[0].split(':', 1)[1].strip()


# check the feed uri
if feed.find('namespaces=true') == -1 or feed.find('magnets=true') == -1:
    out.error('Invalid feed URL. Magnets and namespaces are required')


# initialize the cache
cache = RotatingCache("~/.showrss_cache")
atexit.register(cache.write)


# try to get the feed
try:
    feed = feedparser.parse(feed)
except Exception as e:
    out.error('Error getting the feed: %e' % e)
if feed.bozo:
    out.error('Bozo feed: %s' % feed.bozo_exception.getMessage())


# iterate over the entries
for entry in reversed(feed.entries):
    if not entry.has_key('showrss_episode'):
        out.warn('Found entry with missing episode id ... skipping')
        continue
    id = entry['showrss_episode']
    
    if id in cache.items:
        out.info('Entry "%s": already downloaded ... skipping' % id)
        continue

    if not entry.has_key('showrss_showname'):
        out.warn('Entry "%s": no showname found ... skipping' % id)
        continue
    show = entry['showrss_showname']

    if not entry.has_key('link') or not entry['link'][:7] == 'magnet:':
        out.warn('Entry "%s": no magnet link available ... skipping' % id)
        continue
    link = entry['link']

    destination = path.join(args.destination, show) 
    try:
        subprocess.check_output(cmd + ['--add', link, '--download-dir', destination], stderr = subprocess.STDOUT, shell = True)
    except subprocess.CalledProcessError as e:
        out.warn('Error sending to transmission: %s' % e.output)
    except Exception as e:
        out.warn('Error sending to transmission: %s' % e)
    else:
        out.info('Storing new episode of "%s" in "%s"' % (show, destination))
        cache.add(id)
    

exit(0)
