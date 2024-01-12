# -*- coding: utf-8 -*-
import urllib2
import requests

url = 'http://data.zz.baidu.com/urls?site=disenone.github.io&token=gjZXbMTC0FfXAEuZ'

def run():
    sitemap = urllib2.urlopen('http://disenone.github.io/sitemap.txt')
    sites = sitemap.read()
    sites = sites.split('\n')
    sites = [x for x in sites if x]
    sites = '\n'.join(sites)

    res = requests.post(url, data=sites)
    return res.status_code, res.text

if __name__ == '__main__':
    print run()
