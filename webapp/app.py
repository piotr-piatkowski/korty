#!/usr/bin/env python
# coding: utf-8

import time
import logging
import paramiko
import os

from scp import SCPClient
from random import random
from flask import Flask, send_file
from redis import Redis
from multiprocessing import Process
from threading import Thread
from contextlib import closing
from Queue import Queue
from PIL import Image

DEBUG=True
SSH_KEY="/home/korty/.ssh/id_rsa"
SSH_KNOWN_HOSTS="/home/korty/.ssh/known_hosts"
REMOTE_PICTURE="pictures/current.jpg"
LOCAL_PICTURE="/home/korty/current.jpg"
LOCAL_THUMBNAIL="/home/korty/current-small.jpg"

app = Flask('korty')
running = True

class ImageRequest(object):
    def __init__(self):
        self.done = False
        self.local_mtime = None
        self.remote_mtime = None
        self.last_sync_ts = None
        self.picture_path = LOCAL_PICTURE
        self.thumbnail_path = LOCAL_THUMBNAIL

    def complete(self, local_mtime, remote_mtime, last_sync_ts):
        self.local_mtime = local_mtime
        self.remote_mtime = remote_mtime
        self.last_sync_ts = last_sync_ts
        self.done = True

    def wait(self):
        while not self.done:
            time.sleep(0.1)

request_queue = Queue()

def setup_logging():
    fmt = logging.Formatter('%(asctime)s [%(process)5d] %(name)-14s ' +
            '%(levelname)-6s %(message)s')
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG if DEBUG else logging.INFO)
    handler.setFormatter(fmt)
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.DEBUG)

def wait_for_request():
    pass

def wait_for_update(timeout=20):
    pass

def ssh_connect():
    ssh = paramiko.client.SSHClient()
    ssh.load_host_keys(SSH_KNOWN_HOSTS)
    ssh.set_missing_host_key_policy(paramiko.client.AutoAddPolicy())
    app.logger.debug("connecting...")
    ssh.connect('127.0.0.1', port=22222, username='camera',
            key_filename=SSH_KEY)
    app.logger.debug("connected!")
    return ssh

def get_remote_mtime(ssh):
    try:
        app.logger.debug("exec_command ...")
        stdin, stdout, stderr = ssh.exec_command(
            "stat -c %Y {}".format(REMOTE_PICTURE)
        )
        output = stdout.read()
        app.logger.debug("stdout={}".format(output))
        error = stderr.read()
        app.logger.debug("stderr={}".format(error))
        return int(output)
    except Exception as exc:
        app.logger.error("Error running remote stat: {}".format(exc))
        return None

def update_pictures(ssh):
    app.logger.debug("Updating pictures...")
    try:
        tmplocal = LOCAL_PICTURE + '.tmp'
        tmpthumbnail = LOCAL_THUMBNAIL + '.tmp'
        with SCPClient(ssh.get_transport()) as scp:
            scp.get(REMOTE_PICTURE, tmplocal)
        im = Image.open(tmplocal)
        im.thumbnail((640, 480), Image.ANTIALIAS)
        im.save(tmpthumbnail, "JPEG")
        os.rename(tmpthumbnail, LOCAL_THUMBNAIL)
        os.rename(tmplocal, LOCAL_PICTURE)
        return True
    except Exception as exc:
        app.logger.error("update_pictures error: {}".format(exc))
        return False

def update_loop():
    local_mtime = 0
    remote_mtime = 0
    last_sync_ts = 0
    ssh = None
    req = None
    while running:
        try:
            if ssh is None:
                ssh = ssh_connect()
            req = request_queue.get()
            app.logger.debug("Got new request")
            now = time.time()
            if last_sync_ts < now - 15:
                rmt = get_remote_mtime(ssh)
                if rmt:
                    app.logger.debug("Remote mtime={}".format(rmt))
                    last_sync_ts = now
                    remote_mtime = rmt

            if remote_mtime > local_mtime:
                if update_pictures(ssh):
                    local_mtime = remote_mtime

            req.complete(local_mtime, remote_mtime, last_sync_ts)

        except SSHException as exc:
            if req:
                request_queue.put(req)
            ssh = None
        except Exception as exc:
            app.logger.error("Exception: {}".format(exc))

def human_time_period(t):
    if t <= 60:
        return '{} s'.format(int(t))
    elif t <= 3600:
        return 'ponad {} min'.format(int(t/60))
    else:
        return '{} h {} min'.format(int(t/3600), int(t/60) % 60)

@app.route('/camera/info.html')
def camera_info():
    req = ImageRequest()
    request_queue.put(req)
    req.wait()
    if req.last_sync_ts == 0:
        return (
            '<div style="color: red">' +
            'Brak danych z komputera na kortach' +
            '</div>'
        )
    elif req.last_sync_ts < time.time() - 60:
        return (
            '<div style="color: red">' +
            'Brak połączenia z komputerem na kortach od {}'.format(
                human_time_period(time.time() - req.last_sync_ts)) +
            '</div>'
        )
    elif req.remote_mtime < time.time() - 300:
        return (
            '<div style="color: red">' +
            'Brak nowego obrazu z kamery od {}'.format(
                human_time_period(time.time() - req.remote_mtime)) +
            '</div>'
        )
    else:
        return (
            '<div style="color: green">' +
            'Ostatnia aktualizacja {} temu'.format(
                human_time_period(time.time() - req.local_mtime)) +
            '</div>'
        )

@app.route('/camera/current.jpg')
def camera_current():
    req = ImageRequest()
    request_queue.put(req)
    req.wait()
    img_age = time.time() - req.remote_mtime
    return send_file(req.picture_path, cache_timeout=60-img_age,
            last_modified=req.remote_mtime)

@app.route('/camera/current-small.jpg')
def camera_current_small():
    req = ImageRequest()
    request_queue.put(req)
    req.wait()
    img_age = time.time() - req.remote_mtime
    return send_file(req.thumbnail_path, cache_timeout=60-img_age,
            last_modified=req.remote_mtime)

setup_logging()

# Start picture updating process
p = Thread(target=update_loop)
p.start()

app.run()
running = False
p.join()
