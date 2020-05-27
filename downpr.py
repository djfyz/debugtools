from urllib import request
from enum import Enum
import os
import sys
import re
import socket

class status(Enum):
    OK = 0
    ERROR = -1

#determine whether the file in download path, which same as the downloaded file, will be overwrite or not  
overwrite = 1

config_filepath=hex_filepath="C:\\Users\\rding\\Documents\\HuaCapital\\Design Studio 6\\Download\\"
#config_filepath="C:\\Users\\rding\\Documents\\HuaCapital\\Design Studio 6\\Download\\"
image_filepath="C:\\Users\\rding\\Documents\\HuaCapital\\Design Studio 6\\Download\\"

url_format = 'https://packrat.tddi.ovt.com/packrat/getFile.cgi?packrat_id={}&filename={}'
hex_url_format = 'https://packrat.tddi.ovt.com/packrat/gethex.cgi?packrat_id={}'
query_url_format = 'https://packrat.tddi.ovt.com/packrat/view.cgi?packrat_id={}'

def callbackfunc(blocknum, blocksize, totalsize):
    if (totalsize == -1 and blocknum > 1):
        print("\rDownloaded: %s KB" % (str(blocknum*blocksize/1024)), end="", flush=True)
    elif (totalsize > 0):
        percent = 100.0 * blocknum * blocksize / totalsize
        if percent > 100:
            percent = 100
        print ("\r%.2f%% %d %d %u" % (percent, blocknum, blocksize, totalsize), end="", flush=True)

def getfwlevel(content):
    level = 1 #default level1
    if (content.find("not reproducible, or no info") >= 0):
        level = 0
    elif (content.find("not in sync with source control") >= 0):
        level = 1
    elif (content.find("in sync with source control") >= 0):
        level = 2
    else:
        print("get fw level failed, maybe PR number is invalid, anyway, going on with default value(level1)")
        return level

    print("\nPR level: L%d\n" % level)
    return level

def searchfilename(content, level, pr):
    fwname=''
    hexname=''
    configname=''
    filename = re.search("(filename=[a-z]+.*\.img)", content)
    if (filename is None):
        print("Cannot find the image file name, may be the packrat server is abnormal")
    else:
        fwname = re.search("(filename=[a-z]+.*\.img)", content).group(0)
        fwname=fwname[9:]
        hexname=fwname.replace(".img", ".hex")
        configname="config_private.json"
    return fwname, hexname, configname

def generatefilename(pr, level, fwname, hexname, configname):
    fwname="PR" + pr + "-" + fwname
    hexname=fwname.replace(".img", ".hex")
    configname="PR" + pr + "-" + "config_private.json"
    if (level < 2):
        fwname=fwname.replace(".img", "_FOR_TEST_ONLY.img") 
    return fwname, hexname, configname

def download(url, filetype, filename, callbackfunc):
    errflag = 0
    ans = "n"
    while True:
        try:
            if (errflag == 0):
                savefilename = filename
                name = os.path.basename(filename)
                dirname = os.path.dirname(filename)
                name = "Unconfirmed_" + name
                filename = os.path.join(dirname, name)
            print("Download %s file: %s" % (filetype, name))
            if (os.path.exists(filename)):
                os.remove(filename)
            request.urlretrieve(url, filename, callbackfunc)
            print(", Actual size: %.2f KB" % (os.path.getsize(filename)/1024))
            if (os.path.exists(savefilename)):
                if (overwrite):
                    os.remove(savefilename)
                else:
                    ans = input("overwrite? y/n: ")
                    if (ans == "y" or ans == "Y" or ans == ""):
                        os.remove(savefilename)
                    else:
                        while True:
                            fname = savefilename.split(".")
                            savefilename = fname[0] + "-Copy." + fname[1]
                            if (os.path.exists(savefilename)):
                                continue
                            else:
                                break
            os.rename(filename, savefilename)
        except Exception as e:
            errflag = 1
            print("\n" + str(e))
        finally:
            ans = "n"
            if (errflag):
                ans = input("Retry? y/n: ")

        if (errflag):
            if (ans == "y" or ans == "Y" or ans == ""):
                continue
            else:
                return status.ERROR
        else:
            break

    return status.OK

def getdownloadparameter(pr):
    hex_url = ""
    config_url = ""
    image_url = ""
    hex_file = ""
    config_file = ""
    image_file = ""

    while True:
        errflag = 0
        try:
            req = request.Request(query_url_format.format(pr))
            response = request.urlopen(req)
            webcontent = response.read().decode('utf-8')
        except Exception as e:
            errflag = 1
            print("\n" + str(e))
        else:
            fwlevel = getfwlevel(webcontent)
            fwname, hexname, configname = searchfilename(webcontent, fwlevel, pr)
            if (fwname == '' or hexname == '' or configname == ''):
                errflag = 1

            config_url = url_format.format(pr, configname)
            image_url = url_format.format(pr, fwname)
            hex_url = hex_url_format.format(pr)

            fwname, hexname, configname = generatefilename(pr, fwlevel, fwname, hexname, configname)
            image_file=image_filepath + fwname
            config_file=config_filepath + configname
            hex_file=hex_filepath + hexname
        finally:
            ans = "n"
            if (errflag):
                ans = input("Retry? y/n: ")

        if (errflag):
            if (ans == "y" or ans == "Y" or ans == ""):
                continue
            else:
                break
        else:
            break

    return errflag, hex_url, config_url, image_url, hex_file, config_file, image_file

def main(pr):
    #set download timeout 30s
    socket.setdefaulttimeout(10)

    #get download parameters
    errflag, hex_url, config_url, image_url, hex_file, config_file, image_file = getdownloadparameter(pr)
    if (errflag):
        return

    #Download image file
    if (download(image_url, "image", image_file, callbackfunc) != status.OK):
        return

    #Download config file
    if (download(config_url, "config", config_file, callbackfunc) != status.OK):
        return

    #Download hex file
    if (download(hex_url, "hex", hex_file, callbackfunc) != status.OK):
        return

    print("Done")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Please specifies a PR number")
        sys.exit(0)

    try:
        main(sys.argv[1])
    except BaseException as e:
        if isinstance(e, KeyboardInterrupt):
            sys.exit(0)
        else:
            print(e)
