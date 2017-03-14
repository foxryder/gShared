#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import logging
import os.path
import re
import shutil
import sys
import threading
import urllib
import urllib2
from logging.handlers import RotatingFileHandler
from config.config import *
from fuzzywuzzy import fuzz

import eyed3
import youtube_dl
from acrcloud.recognizer import ACRCloudRecognizer
from flask import Flask
from flask_restful import Api, Resource, abort, reqparse
from pyfcm import FCMNotification
from fuzzywuzzy import fuzz

from config.config import *

app = Flask(__name__)
api = Api(app)



parser = reqparse.RequestParser()
parser.add_argument('mode')
parser.add_argument('url')
parser.add_argument('token')
parser.add_argument('library')



libraries = json.loads(library)

class ReceiveRequest(Resource):
    def post(self):
        try:
            args = parser.parse_args()

            mode = int(args['mode'])
            if mode == 1:
                if newUser(args):
                    return {'error':0}
                else:
                    return {'error':42}
            elif mode == 2:
                if download(args):
                    return {'error':0}
                else:
                    return {'error':43}
            elif mode == 3:
                app.logger.info('Library Request')
                save_token(args)
                l = []
                for library in libraries['libraries']:
                    d = {}
                    d['name'] = library['name']
                    l.append(d)
                return l
            else:
                app.logger.info('Wrong mode argument ' + args['mode'])
        except Exception as e:
            app.logger.error('Error parsing mode argument '+ repr(e))
        return {'error':45}

    def get(self):
        return

def newUser(args):
    try:
        save_token(args)
        return True
    except Exception as e:
        app.logger.error('Error setting new User '+ repr(e))
    return False

def download(args):
    try:
        if 'youtu' in args['url']:
            app.logger.info("Request: " + args['url'])
            t = threading.Thread(target=youtubedl,args=(args,))
            t.start()
            return True
        else:
            return False

    except Exception as e:
        app.logger.error('Failed to parse link: '+ args['url'] +' , '+ repr(e))
        return False


class MyLogger(object):
    def debug(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        print(msg)


def my_hook(d):
    if d['status'] == 'finished':
        print('Done downloading, now converting ...')


def youtubedl(args):
    try:
        #save_token(args)
        link = args['url']
        libLocation = ''
        library = args['library']
        for lib in libraries['libraries']:
            if lib['name'] == args['library']:
                libLocation = lib['location']
        if not libLocation: 
            app.logger.error("No such library as "+ args['library'])
            return False
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': '%(id)s.%(ext)s',
            'logger': MyLogger(),
            'progress_hooks': [my_hook],
        }
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(link, download=True)
            video_title = info_dict.get('title', None)
            id = info_dict.get('id', None)
            fileid = id + '.mp3'
            if start_reckon(fileid,video_title, libLocation,library) is False:
                manualTagging(video_title, fileid, libLocation,library)
            app.logger.info('Successfully downloaded '+ video_title+ ' at '+ link)
        print "Done"

    except Exception, e:
        app.logger.error('Download failed: '+ repr(e))

def manualTagging(video_title, fileid, libLocation, library):
    try:
        tag = re.split("-+|\[?", video_title)
        audiofile = eyed3.load(fileid)
        if len(tag) >= 2:
            title = tag[1].strip()
            artist = tag[0].strip()
            id = search_api(artist,title)
            if (id != 0):
                audiofile.tag.album = get_album_by_id(id)
                urllib.urlretrieve(cover_url, "cover.jpg")
                imagedata = open("cover.jpg", "rb").read()
                audiofile.tag.images.set(3, imagedata, "image/jpeg", unicode(album))
            audiofile.tag.artist = artist
            audiofile.tag.title = title
            audiofile.tag.album_artist = artist
            title = artist+' - '+title
        else:
            title = tag[0].strip()
            audiofile.tag.title = title
        audiofile.tag.save()
        moveFile(title, fileid, libLocation,library)
    except Exception as e:
        app.logger.error('Manual tagging failed: '+ repr(e))

def moveFile(filename, fileid, libLocation,library):
    try:
        push_notify('Neuer Song auf Plex!', filename + u' ist jetzt verfügbar.',library)
        newPath = filename +'.mp3'
        shutil.move(fileid, libLocation+newPath)
    except Exception as e:
        app.logger.error('Moving file failed: '+str(e))

def search_api(artist,title):
    try:
        search_string = artist+'+'+title
        search_string = search_string.replace(' ','+')
        api_response = urllib2.urlopen('https://api.spotify.com/v1/search?q='+search_string+'&type=track')
        music_service_json = json.load(api_response)
        for item in music_service_json['tracks']['items']:
            if fuzzy(item['artists'][0]['name'],artist) >= 60:
                return item['id']
        return 0
    except Exception as e:
        app.logger.info('Search api: '+str(e))
        return 0

def get_cover_by_id(id):
    try:
        api_response = urllib2.urlopen('https://api.spotify.com/v1/tracks/'+id)
        music_service_json = json.load(api_response)
        cover_url = music_service_json['album']['images'][0]['url']
        return cover_url
    except Exception as e:
        app.logger.error('Error in get_cover_by_id: '+str(e))
        return 0

def get_album_by_id(id):
    try:
        api_response = urllib2.urlopen('https://api.spotify.com/v1/tracks/'+id)
        music_service_json = json.load(api_response)
        return music_service_json['album']['name']
    except Exception as e:
        app.logger.error('Error in get_album_by_id: '+str(e))
        return 0 

def fingerprint(rec, offset, fileid, video_title):
    try:
        if offset > 120:
            return False
        response = rec.recognize_by_file(fileid, offset)

        parsed_json = json.loads(response)
        if parsed_json['status']['code'] is 0:
            if similar(video_title,parsed_json):
                app.logger.info("Song found")
                return parsed_json
            else:
                return fingerprint(rec, offset+30, fileid, video_title)
        else:
            return fingerprint(rec, offset+30, fileid, video_title)


    except:
        app.logger.error("Error while fingerprinting")

def similar(video_title,parsed_json):
    try:
        artists = parsed_json['metadata']['music'][0]['artists']
        title = parsed_json['metadata']['music'][0]['title']
        artist_list = []
        tagging = True
        try:
            tags = re.match(r"(.*) - ([a-zA-Z0-9_'& ]*)", video_title).groups()
            video_artist = tags[0]
            video_trackname = tags[1]
        except:
            tagging = False 
        for artist in artists:
            artist_list.append(artist['name'])
        artist_string = ', '.join(artist_list)

        app.logger.info("ACR_Artist: "+ artist_string)
        if fuzzy(video_title,artist_string) >= 40:
            return True
        else:
            return False
        if fuzzy(video_artist,artist_string) >= 60 and fuzzy(video_trackname,title) >= 60 and tagging:
            return True
        else:
            return False
    except Exception as e:
        app.logger.error('Error in function similar: '+ repr(e))

def fuzzy(a,b):
    return fuzz.partial_ratio(a,b)


def get_external_ids(json, service):
    try:
        return  json['metadata']['music'][0]['external_metadata'][service]['track']['id']
    except Exception, e:
        app.logger.info("No id for "+service +' available')
    return 0


        

def get_cover_url(parsed_json):
    try:
        spotify_id = get_external_ids(parsed_json, 'spotify')
        itunes_id = get_external_ids(parsed_json, 'itunes')
	cover_url = 0

        if spotify_id != 0:
            api_response = urllib2.urlopen('https://api.spotify.com/v1/tracks/'+spotify_id)
            music_service_json = json.load(api_response)
            if music_service_json['album']['artists'][0]['name'] is "Various Artists":
                cover_url = 0
            else:
                app.logger.info("Cover Art found")
                cover_url = music_service_json['album']['images'][0]['url']
                return cover_url


        if itunes_id != 0:
            api_response = urllib2.urlopen('https://itunes.apple.com/lookup?id='+str(itunes_id))
            music_service_json = json.load(api_response)
            if music_service_json['results'][0]['collectionArtistName'] is "Various Artists":
                cover_url = 0
            else:
                cover_url = music_service_json['results'][0]['artworkUrl100']
                cover_url = cover_url.replace('100x100', '500x500')
                app.logger.info("Cover Art found")
                return cover_url

        app.logger.info("No Cover Art found")
        return cover_url

    except Exception, e:
        app.logger.error("Cover URl retrieval failed: "+ repr(e))
        return 0





def start_reckon(fileid, video_title, libLocation,library):
    try:

        '''This module can recognize ACRCloud by most of audio/video file.
            Audio: mp3, wav, m4a, flac, aac, amr, ape, ogg ...
            Video: mp4, mkv, wmv, flv, ts, avi ...'''
        rec = ACRCloudRecognizer(acrcloud_config)


        parsed_json = fingerprint(rec, 60, fileid, video_title)

	if parsed_json is False:
            app.logger.info("No Song found")
            return False

        cover_url = get_cover_url(parsed_json)

        album = parsed_json['metadata']['music'][0]['album']['name']
        artists = parsed_json['metadata']['music'][0]['artists']
        title = parsed_json['metadata']['music'][0]['title']
        artist_list = []
        for artist in artists:
            artist_list.append(artist['name'])
        artist_string = ', '.join(artist_list)
        audiofile = eyed3.load(fileid)
        audiofile.tag.artist = unicode(artist_string)
        audiofile.tag.album = unicode(album)
        audiofile.tag.title = unicode(title)
        audiofile.tag.album_artist = unicode(artist_string)
        if cover_url != 0:
            urllib.urlretrieve(cover_url, "cover.jpg")
            imagedata = open("cover.jpg", "rb").read()
            audiofile.tag.images.set(3, imagedata, "image/jpeg", unicode(album))
        audiofile.tag.save()
        app.logger.info('Successfully tagged ' + artist_string + ' - ' + title)
        moveFile(artist_string+ ' - ' +title, fileid, libLocation,library)
        return True
    except Exception as e:
        app.logger.error("Tagging Error: "+ repr(e))
        return False


def save_token(args):
    try:
	id = args['token']
	folder = json.loads(args['library'])
        if not os.path.exists(tokenLocation):
            l = []
            ll = []
            for library in libraries['libraries']:
                d = {}
                d['name'] = library['name']
                d['token'] =ll 
                l.append(d)
            with open(tokenLocation,'w') as f:
                f.write(json.dumps(l))
        with  open(tokenLocation,'r') as token_file:
            tokens = json.loads(token_file.read())
        for jsonobj in folder:
            for i in xrange(len(tokens)):
                if tokens[i]['name'] == jsonobj['name']:
                    if id not in tokens[i]['token']:
                        if jsonobj['checked']:
                            tokens[i]['token'].append(id)
                    else:
                        if not jsonobj['checked']:
                            tokens[i]['token'].remove(id)

                    with open(tokenLocation,'w') as token_file:
                        json.dump(tokens,token_file)
    except Exception as e:
        app.logger.error("Error saving token: "+ repr(e))






def push_notify(title,body,library):
    try:
        push_service = FCMNotification(api_key=firebase_api)
        with open(tokenLocation, 'r') as file:
            token_json = json.loads(file.read())
        for jsonobj in token_json:
            if jsonobj['name'] == library:

                registration_ids = jsonobj["token"]
                valid_registration_ids = push_service.clean_registration_ids(registration_ids)
                result = push_service.notify_multiple_devices(registration_ids=valid_registration_ids, message_title=title, message_body=body)
    except Exception as e:
        app.logger.error("Error sending push notification: "+ repr(e))

class Debug(Resource):
    def get(self):
        start_reckon()


api.add_resource(ReceiveRequest, '/')


if __name__ == '__main__':
    if not app.debug:
        formatter = logging.Formatter("[%(asctime)s] {%(pathname)s:%(lineno)d} %(levelname)s - %(message)s")
        handler = RotatingFileHandler(logLocation, maxBytes=100000, backupCount=1)
        app.logger.addHandler(handler)
        app.logger.setLevel(logging.INFO)
        handler.setFormatter(formatter)
    app.logger.info("Start Server")
    app.run(host='0.0.0.0')
