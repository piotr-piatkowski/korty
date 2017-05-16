#!/usr/bin/env python
# coding: utf-8

import os
import re
import shutil
import logging

logger = logging.getLogger("camera-update")

DIR = "/home/camera/pictures"
CUR_PATH = DIR + "/current.jpg"
CUR_PATH_TMP = CUR_PATH + ".tmp"

def is_complete(path):
    return True

while True:
    files = os.listdir(DIR)
    newest = (None, 0)
    for f in files:
        fpath = DIR + "/" + f
        if re.match(r'172\..*\.jpg', f) and is_complete_jpg(fpath):
            mtime = os.stat(fpath).st_mtime
            if mtime > newest[1]:
                newest = (fpath, mtime)

    if newest[0]:
        shutil.copyfile(newest[0], CUR_PATH_TMP)
        os.rename(CUR_PATH_TMP, CUR_PATH)
        logger.debug("Copied {} to {}".format(newest[0], CUR_PATH))

    time.sleep(1)
