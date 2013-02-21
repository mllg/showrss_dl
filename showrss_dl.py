#!/usr/bin/env python3

"""
https://github.com/mllg/showrss_dl
"""

import argparse
import subprocess
import feedparser
import pickle
import atexit
import re
from os.path import exists, expanduser
from sys import exit, stdout, stderr

__version__ = '0.1'

class ConsoleOutput:
    def __init__(self, verbose):
       self.__verbose = verbose
    def info(self, msg):
        if self.__verbose:
            stdout.write('[INFO] %s\n' % msg)
            stdout.flush()
    def warn(self, msg):
        stdout.write('[WARN] %s\n' % msg)
        stdout.flush()
    def error(self, msg, exit_code = 1):
        stderr.write('[ERROR] %s\n' % msg)
        stderr.flush()
        exit(exit_code)


class MagnetCache:
    cachesize = 120
    needsupdate = False
    def __init__(self, fn):
        self.fn = expanduser(fn)
        self.hashs = []
        if exists(self.fn):
            with open(self.fn, 'rb') as f:
                self.hashs = pickle.load(f)
    def add(self, new):
        self.hashs.append(new)
        self.needsupdate = True
    def check(self, hash):
        return hash in self.hashs
    def write(self):
        if self.needsupdate:
            with open(self.fn, 'wb') as f:
                pickle.dump(self.hashs[-self.cachesize:], f)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description = 'showRSS downloader')

    parser.add_argument('--feed',
            required = True,
            help = 'showRSS feed with magnet links as generated on the website.')
    parser.add_argument('--auth',
            default = None,
            help = 'RPC authentication for transmission-remote as <user:passwd>. Defaults to no authentication.')
    parser.add_argument('--verbose',
            action = 'store_true',
            help = 'Be more verbose. Helpful for debugging.')
    parser.add_argument('--cachefile',
            default = '~/.magnetcache',
            help = 'File to store known magnet links. Default is "~/.magnetcache".')
    args = parser.parse_args()
    
    out = ConsoleOutput(verbose = args.verbose)
    cmd = ['transmission-remote']
    if args.auth is not None:
        cmd += ['--auth', args.auth]
    
    feed = feedparser.parse(args.feed)
    if feed.bozo:
        out.error('Bozo feed in "%s" (%s)' % (args.feed, feed.bozo_exception.getMessage()))
    
    try:
        cache = MagnetCache(args.cachefile)
    except (IOError) as e:
        out.error('Could not read cache file "%s"' % args.cachefile)
    
    pat = re.compile(r'xt=urn:btih:([^&/]+)')
    cache = MagnetCache(args.cachefile)
    atexit.register(cache.write)
    
    for entry in reversed(feed.entries):
        if not entry.has_key('title'):
            out.warn('No title found in feed, skipping')
            continue
        title = entry['title']
        
        if not entry.has_key('link'):
            out.warn('Entry "%s": no magnet link available, skipping' % title)
            continue
        link = entry['link']
        
        if not link[:7] == 'magnet:':
            out.warn('Entry "%s": malformed magnet link (%s), skipping' % (title, link))
            continue

        match = pat.search(link)
        if match is None:
            out.warn('Entry "%s": no hash in magnet link (%s), skipping' % (title, link))
            continue
        hash = match.groups()[0]

        if cache.check(hash):
            out.info('Entry "%s" found in cache, skipping' % title)
            continue
        
        try:
            output = subprocess.check_output(cmd + ['--add', link], stderr = subprocess.STDOUT)
        except OSError as e:
            out.warn('Entry "%s" could not be send to transmission (%s)' % (title, e))
        except subprocess.CalledProcessError:
            out.warn('Entry "%s" could not be send to transmission (%s)' % (title, output))
        else:
            cache.add(hash)
            out.info('Send torrent with hash "%s"' % hash)
    
    out.info('Finished')
