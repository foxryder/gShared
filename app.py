#!/usr/bin/env python
# -*- coding: utf-8 -*-

import youtube_dl
from flask import Flask
from flask_restful import reqparse, abort, Api, Resource
import eyed3
import re
import logging
from logging.handlers import RotatingFileHandler
from acrcloud.recognizer import ACRCloudRecognizer
import json
import sys
import shutil
import os.path
import urllib2
import urllib
import threading
from pyfcm import FCMNotification
from config import *


app = Flask(__name__)
api = Api(app)


parser = reqparse.RequestParser()
parser.add_argument('url')
parser.add_argument('remixFlag')
parser.add_argument('token')

class ReceiveRequest(Resource):
    def post(self):
        try:
            args = parser.parse_args()
            if 'youtu' in args['url']:
                app.logger.info("Request: " + args['url'])
                t = threading.Thread(target=youtubedl,args=(args,))
                t.start()
            else:
                return {'error':202}

            return {'error': 0}
        except:
            app.logger.error('Failed to parse link '+ args['url'])
            return {'error': 154}

    def get(self):
        return

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
        save_token(args)
        link = args['url']
	remix = args['remixFlag']
	print (type(remix))
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
            if int(remix) != 0:
		manualTagging(video_title,fileid)
	    else:
	        if start_reckon(fileid) is False:
                    manualTagging(video_title,fileid)
            app.logger.info('Successfully downloaded '+ video_title+ ' at '+ link)
	    print "Done"

    except Exception, e:
        app.logger.error('Download failed: '+ repr(e))

def manualTagging(video_title,fileid):
    try:
        tag = re.split("-+|\[?",video_title)
        audiofile = eyed3.load(fileid)
        if len(tag)>=2:
            title = tag[1].strip()
            artist = tag[0].strip()
            audiofile.tag.artist = artist
            audiofile.tag.title = title
            audiofile.tag.album_artist = artist
        else:
            title = tag[0].strip()
            audiofile.tag.title = title
        audiofile.tag.save()
        moveFile(artist+' - '+title,fileid)
    except Exception as e:
        app.logger.error('Manual tagging failed: '+ repr(e))

def moveFile(filename,fileid):
    try:
	push_notify('Neuer Song auf Plex!', filename + u' ist jetzt verfügbar.')
	newPath = filename +'.mp3'
        shutil.move(fileid, location+newPath)
    except Exception as e:
        app.logger.error('Moving file failed: '+str(e))

def fingerprint(rec,offset,fileid):
    try:
        if offset > 120:
            return false
        response = rec.recognize_by_file(fileid, offset)
	#f = open('song.json','w')
	#f.write(response)
	#f.close()
        parsed_json = json.loads(response)
        if (parsed_json['status']['code'] is 0):
            app.logger.info("Song found")
            return parsed_json
        else:
            return fingerprint(rec,offset+30,fileid)


    except:
        app.logger.error("Error while fingerprinting")


def get_external_ids(json,service):
    try:
        return  json['metadata']['music'][0]['external_metadata'][service]['track']['id']
    except Exception, e:
	app.logger.info("No id for "+service +' available')
	return 0


def get_cover_url(parsed_json):
    try:
        spotify_id = get_external_ids(parsed_json,'spotify')
        itunes_id = get_external_ids(parsed_json,'itunes')


        if spotify_id != 0:
            api_response  = urllib2.urlopen('https://api.spotify.com/v1/tracks/'+spotify_id)
            music_service_json = json.load(api_response)
	    if music_service_json['album']['artists'][0]['name'] is "Various Artists":
	        cover_url = 0
	    else:
		app.logger.info("Cover Art found")
                cover_url = music_service_json['album']['images'][0]['url']
		return cover_url


	if itunes_id != 0:
            api_response  = urllib2.urlopen('https://itunes.apple.com/lookup?id='+str(itunes_id))
            music_service_json = json.load(api_response)
	    if music_service_json['results'][0]['collectionArtistName'] is "Various Artists":
		cover_url = 0
	    else:
                cover_url = music_service_json['results'][0]['artworkUrl100']
                cover_url = cover_url.replace('100x100','500x500')
		app.logger.info("Cover Art found")
		return cover_url

        app.logger.info("No Cover Art found")
	return cover_url

    except Exception, e:
	app.logger.error("Cover URl retrieval failed: "+ repr(e))
	return 0



def start_reckon(fileid):
    try:

        '''This module can recognize ACRCloud by most of audio/video file.
            Audio: mp3, wav, m4a, flac, aac, amr, ape, ogg ...
            Video: mp4, mkv, wmv, flv, ts, avi ...'''
        rec = ACRCloudRecognizer(acrcloud_config)

        parsed_json = fingerprint(rec,60,fileid)

	cover_url = get_cover_url(parsed_json)

        album = parsed_json['metadata']['music'][0]['album']['name']
        artists = parsed_json['metadata']['music'][0]['artists']
        title = parsed_json['metadata']['music'][0]['title']
        artist_list = []
        for artist in artists:
            artist_list.append(artist['name'])
        artist_string= ', '.join(artist_list)
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
        moveFile(artist_string+ ' - ' +title,fileid)
        return True
    except Exception, e:
        app.logger.error("Tagging Error: "+ repr(e))
        return False


def save_token(args):
    try:
	id = args['token']
        if not os.path.exists(tokenLocation):
            with open(tokenLocation,'w') as f:
                f.write('{"Token":[]}')
        with  open(tokenLocation,'r') as token_file:
            tokens = json.loads(token_file.read())
        if id  not in tokens['Token']:
            tokens['Token'].append(id)
            with open(tokenLocation,'w') as token_file:
                json.dump(tokens,token_file)
    except Exception as e:
        app.logger.error("Error saving token: "+ repr(e))






def push_notify(title,body):
    try:
        push_service = FCMNotification(api_key=firebase_api)
        with open(tokenLocation,'r') as file:
            token_json  = json.loads(file.read())
        registration_ids=token_json["Token"]
        valid_registration_ids = push_service.clean_registration_ids(registration_ids)
        result = result = push_service.notify_multiple_devices(registration_ids=valid_registration_ids, message_title=title, message_body=body)
    except Exception as e:
        app.logger.error("Error sending push notification: "+ repr(e))

class Debug(Resource):
    def get(self):
	start_reckon()


api.add_resource(ReceiveRequest, '/')


if __name__ == '__main__':
    if not app.debug:
        formatter = logging.Formatter("[%(asctime)s] {%(pathname)s:%(lineno)d} %(levelname)s - %(message)s")
        handler = RotatingFileHandler(logLocation+'info.log', maxBytes=100000, backupCount=1)
        app.logger.addHandler(handler)
        app.logger.setLevel(logging.INFO)
        handler.setFormatter(formatter)
    app.logger.info("Start Server")
    app.run(host='0.0.0.0')
