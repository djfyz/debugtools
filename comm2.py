import os,logging,time,re,sys
import usb.core
import usb.util
import numpy as np
import ctypes
import msvcrt
from socket import *
import easygui as g
import zlib as z
import datetime

BOOT_CONFIG_ID                   = "BOOT_CONFIG"
F35_APP_CODE_ID                  = "F35_APP_CODE"
APP_CONFIG_ID                    = "APP_CONFIG"
DISP_CONFIG_ID                   = "DISPLAY"
IMAGE_FILE_MAGIC_VALUE           = 0x4818472b
FLASH_AREA_MAGIC_VALUE           = 0x7c05e516
PDT_START_ADDR                   = 0x00e9
PDT_END_ADDR                     = 0x00ee
#UBL_FN_NUMBER                    = 0x35
F35_CTRL3_OFFSET                 = 18
F35_CTRL7_OFFSET                 = 22
F35_WRITE_FW_TO_PMEM_COMMAND     = 4
UBL_FN_NUMBER                    = "0035"

HDL_INVALID                      = 0
HDL_TOUCH_CONFIG_TO_PMEM         = 1 
HDL_DISPLAY_CONFIG_TO_PMEM       = 2
HDL_DISPLAY_CONFIG_TO_RAM        = 3

CMD_DOWNLOAD_CONFIG              = "30"
CMD_CONTINUE_WRITE               = "01"

hdl_version                      = 1

f35_error_code = {
0:"SUCCESS",
1:"UNKNOWN_FLASH_PRESENT",
2:"MAGIC_NUMBER_NOT_PRESENT",
3:"INVALID_BLOCK_NUMBER",
4:"BLOCK_NOT_ERASED",
5:"NO_FLASH_PRESENT",
6:"CHECKSUM_FAILURE",
7:"WRITE_FAILURE",
8:"INVALID_COMMAND",
9:"IN_DEBUG_MODE",
10:"INVALID_HEADER",
11:"REQUESTING_FIRMWARE",
12:"INVALID_CONFIGURATION",
13:"DISABLE_BLOCK_PROTECT_FAILURE",
}


class image_info:
    boot_config_size = 0
    boot_config_data = []
    boot_config_flash_addr = 0
    app_firmware_size = 0
    app_firmware_data = []
    app_firmware_flash_addr = 0
    app_config_size = 0
    app_config_data = []
    app_config_flash_addr = 0
    disp_config_size = 0
    disp_config_data = []
    disp_config_flash_addr = 0
    def __init__(self):
        pass

STD_INPUT_HANDLE = -10
STD_OUTPUT_HANDLE= -11
STD_ERROR_HANDLE = -12
VDDH_VOLTAGE  = 1200
VDDIO_VOLTAGE = 1800

SPI_MODE=3
SPI_SPEED=5000
USAGE='''
Released on Dec.5, 2019, by Rover Shen.
This is a tool for cdci console replacement when using MPC04 to connect with TouchComm module.
You need to install filter driver over MPC04 USB devices provided by LibUSB-Win32 toolkit before using it.
LibUSB-Win32 can be downloaded here:
https://sourceforge.net/projects/libusb-win32/
Example:
cmd=05c0  #enable c0 report and read until $01(OK) response is received
rd=1200   #read 1200 bytes from interface
wr=1f     #enter bootloader and read a response
wrnr=04   #software reset without reading anything
check     #try to read a packet
run       #keep reading packet, any key to stop
quit      #quit the script
'''
class Color:
  ''''' See http://msdn.microsoft.com/library/default.asp?url=/library/en-us/winprog/winprog/windows_api_reference.asp 
  for information on Windows APIs.'''  
    
  FOREGROUND_BLACK = 0x0  
  FOREGROUND_BLUE = 0x01 # text color contains blue.  
  FOREGROUND_GREEN= 0x02 # text color contains green.  
  FOREGROUND_RED = 0x04 # text color contains red.  
  FOREGROUND_YELLOW = 0x06
  FOREGROUND_INTENSITY = 0x08 # text color is intensified.  
  
  BACKGROUND_BLUE = 0x10 # self.BACKground color contains blue.  
  BACKGROUND_GREEN= 0x20 # self.BACKground color contains green.  
  BACKGROUND_RED = 0x40 # self.BACKground color contains red.  
  BACKGROUND_INTENSITY = 0x80 # self.BACKground color is intensified.  
  std_out_handle = ctypes.windll.kernel32.GetStdHandle(STD_OUTPUT_HANDLE)  
    
  def set_cmd_color(self, color, handle=std_out_handle):  
      """(color) -> bit 
      Example: set_cmd_color(self.FOREGROUND_RED | self.FOREGROUND_GREEN | self.FOREGROUND_BLUE | self.FOREGROUND_INTENSITY) 
      """  
      bool = ctypes.windll.kernel32.SetConsoleTextAttribute(handle, color)  
      return bool  
    
  def reset_color(self):  
      self.set_cmd_color(self.FOREGROUND_RED | self.FOREGROUND_GREEN | self.FOREGROUND_BLUE)  
    
  def print_red_text(self, print_text,end='\n',flush=True):  
      self.set_cmd_color(self.FOREGROUND_RED | self.FOREGROUND_INTENSITY)  
      print(print_text,end=end,flush=flush) 
      self.reset_color()  
        
  def print_green_text(self, print_text,end='\n',flush=True):  
      self.set_cmd_color(self.FOREGROUND_GREEN | self.FOREGROUND_INTENSITY)  
      print(print_text,end=end,flush=flush) 
      self.reset_color()  
    
  def print_blue_text(self, print_text,end='\n',flush=True):   
      self.set_cmd_color(self.FOREGROUND_BLUE | self.FOREGROUND_INTENSITY)  
      print(print_text,end=end,flush=flush) 
      self.reset_color()  
      
  def print_yellow_text(self, print_text,end='\n',flush=True):   
      self.set_cmd_color(self.FOREGROUND_YELLOW | self.FOREGROUND_INTENSITY)  
      print(print_text,end=end,flush=flush) 
      self.reset_color()  

class comm2:
  def __init__(self,
    ip='localhost',
    busAddr=None,
    vddh=3300,
    vddio=1800,
    debug=False):
    
    self.clr=Color()
    self.voltage = {"vled":vddh,"vdd":vddio,"vddtx":1800,"vpu":1800}
    self.interface=ip
    self.port = 10001
    
    if self.interface=='i2c':
      self.prefix='target=0 raw bus-addr={}'.format(busAddr)
    else:
      self.prefix='target=0 raw'
    
    self.debug=debug
    self.busAddr = busAddr
    
    if self.interface=='i2c' or self.interface=='spi':
      self.usb = usb.core.find(idVendor=0x06CB, idProduct=0x000F)
      if self.usb is None:
        print('Cannot connect to mpc04, make sure it\'s plugged in USB port.')
        self.connected=False
        return
      self.out_endpoint_addr = 0x1
      self.in_endpoint_addr = 0x82
      self.usb.set_configuration()    
      
      # get an endpoint instance
      cfg = self.usb.get_active_configuration()
      intf = cfg[(0, 0)]
      self.ep_in = usb.util.find_descriptor(
        intf,
        # match the first IN endpoint
        custom_match= \
          lambda e: \
            usb.util.endpoint_direction(e.bEndpointAddress) == \
            usb.util.ENDPOINT_IN)
      
      if self.ep_in == None:
        print("Error: USB endpoint_in Error")
        self.connected=False
        return
      self.connected=True
    else:
      # ===== initial socket =====    
      self.ip = bytes(ip,'utf-8')
      self.socket = socket(AF_INET, SOCK_STREAM)
      try: 
        self.socket.connect((self.ip,self.port))
      except:
        self.connected=False
        print('Cannot connect to redremote server, make sure RedRemote is running.')
        return      
      # 設定recv的timeout時間
      self.socket.settimeout(0.2)
      self.connected=True

    # Init device
    self.err, self.current_mode = self.DeviceInit()
    if self.current_mode=="APP":
      self.tcmDevice=True
      return
    else:
      self.tcmDevice=False
    # read extra-command that didnt finished for last connection (For A511(2d))
    # make sure all of A511 command have been executed

  def sendidentify(self):
     ret = self.usbWrite("identify")
     print(ret)

  def usbWrite(self, command):
    if self.debug:
      print(command)
    command = command + '\n'
    if self.interface=='spi' or self.interface=='i2c':
      self.usb.write(self.out_endpoint_addr, command, 30000)
    else:
      cmd = bytes(command, "UTF-8")
      self.socket.send(cmd)

#    time.sleep(0.01)
    return self.usbRead()

  def usbRead(self):
    if self.interface=='spi' or self.interface=='i2c':
      buf = []
      while True:
        try:
          # 讀取第一次response (為了讓buf不是空的array)
          data = self.usb.read(self.in_endpoint_addr, self.ep_in.wMaxPacketSize,30000)
          buf.extend(data)

          # 檢查 response是否結束，以避免以下狀況 : 
          # 1_讀取速度太快，其中有幾次讀不到資料造成資料讀取不完整
          # 2_該command會多次返回，例如 identify
          # =====================================
          # 10(0x0a) is end code of usb response, 
          # get 10(0x0a) means the response is complete
          while buf[-1] != 10:
            buf.extend(self.usb.read(self.in_endpoint_addr, self.ep_in.wMaxPacketSize))
        except Exception as e:
          print(e)
          print('Please replug USB cable, retry')
          time.sleep(0.01)
          input("continue?")
          continue

        # 把 hex-string 轉成 ascii
        decode_packet = "".join(chr(item) for item in buf)
        if self.debug:
          print(decode_packet.strip())
        break
      return decode_packet
    else:
      result=[]
      while True:
        try:
          result.append(self.socket.recv(4096).decode("UTF-8"))
        except:        
          break
      # 串接所有結果
      result = ''.join(result).upper()
      if self.debug:
        print(result)
      return result.__repr__()
      
  def autoScanAddr(self):
    addrs = ['20','2c','70','4b','67','3c']
    for addr in addrs:
      self.prefix='target=0 raw bus-addr={}'.format(addr)
      result = self.usbWrite('{} wr=02'.format(self.prefix))

      check = re.findall("err",result)
      if check == []:
        print('Found I2C device at address 0x{}.'.format(addr))
        self.busAddr = addr
        break

    if self.busAddr == None:
      print("Error : can\'t find I2C Address among {}".format(addrs))
      self.tcmDevice=False
    else:
      print("Found TouchComm device at address: 0x{}.".format(addr))
      self.tcmDevice=True

    self.clearCmd()
    
  def Config(self, rmi):
    state = ["raw", "rmi"]
    if self.interface == 'i2c':
      cmd = 'target=0 config {} pl=i2c pull-ups=yes speed=400'.format(state[rmi])
    elif self.interface == 'spi':
#      cmd = 'target=0 config {} pl=spi spiMode={} bitRate={} byteDelay=0 pull-ups=yes ssActive=low mode=slave'.format(state[rmi],SPI_MODE,SPI_SPEED)
      cmd = "target=0 config {} pl=spi pull-ups=yes spiMode=3 byteDelay=10 bitRate=500 attn=low ssActive=low mode=slave base64=yes".format(state[rmi])
#     cmd = 'target=0 config rmi pl=spi pull-ups=yes spiMode=3 byteDelay=10 bitRate=500 attn=low ssActive=low mode=slave base64=yes' #ds6
    else:
      cmd = 'target=0 config {} pl=native attn=none'.format(state[rmi])

    r = self.usbWrite(cmd)
    if r is None:
      return 1;
    else:
      return 0;

  def PowerOn(self,vdd=1800,vpu=1800,vled=3300,vddtx=1800):
    self.usbWrite('target=0 power on vdd={} vpu={} vled={} vddtx={}'.format(vdd,vpu,vled,vddtx))

  def PowerOff(self):
    self.usbWrite('target=0 power off')

  def DeviceInit(self):
    rmi = 1
    err=self.Config(rmi)
    if err:
      return err, None
    if self.interface=='spi' or self.interface=='i2c':
      self.PowerOn(vdd=self.voltage['vdd'],
        vpu=self.voltage['vpu'],
        vled=self.voltage['vled'],
        vddtx=self.voltage['vddtx'])

      self.usbWrite('target=0 rmi waitOnTimeout=30000')
      # wait for power-up
      time.sleep(0.5)

      # one more 
      err=self.Config(rmi)
      if err:
        return err, None
      self.PowerOn(vdd=self.voltage['vdd'],
        vpu=self.voltage['vpu'],
        vled=self.voltage['vled'],
        vddtx=self.voltage['vddtx'])
      self.usbWrite('target=0 rmi waitOnTimeout=30000')
      time.sleep(0.5)

      r=self.usbWrite('target=0 rmi wr=80e9 rd=6')
      data=r.split("\"")[3]
      print(r)

      #not in ubl state, use app configuration
      if data.startswith("00") or data.startswith("FF"):
        rmi = 0
        err=self.Config(rmi)
        self.PowerOn(vdd=self.voltage['vdd'],
          vpu=self.voltage['vpu'],
          vled=self.voltage['vled'],
          vddtx=self.voltage['vddtx'])

        self.usbWrite('target=0 raw waitOnTimeout=30000')
        # wait for power-up
        time.sleep(0.5)
        #DS6 do the following 3 steps
        #print(self.usbWrite('target=0 rmi wr=80ff rd=1'))
        #print(self.usbWrite('target=0 rmi wr=00ff00'))
        #print(self.usbWrite('target=0 rmi wr=80e9 rd=6'))
        r = self.readMsg()
        print("h1", r)
        if (r is not None):
          current_mode = "APP"
        else:
          current_mode = "UNKNOWN"
        return err, current_mode
      else:
        data_base = data[6:8]
        fn_number = data[-4:]
        if fn_number == UBL_FN_NUMBER:
          error_code=self.usbWrite('target=0 rmi wr=80{} rd=1'.format(data_base)).split("\"")[3]
          error_code=string_to_uint(error_code)
          if (error_code != 0x4b):
            print("f35 status = 0x%x" % error_code)
            current_mode = "UBL"
          else:
            current_mode = "HDL"
        else:
          current_mode = "UNKNOWN"
        return err, current_mode
    else:
      self.getDatabyCmd('02','01')
      self.socket.settimeout(0.05)

    if self.interface=='i2c' and self.busAddr == None:
      self.autoScanAddr()

  def printPacket(self,str):
    line_len=32
    if str=='A5000000':
      return
    data = [int(str[index:index+2],16) for index in range(0,len(str),2)]
    self.clr.print_red_text('Header={}, Length={}'.format(str[0:8],data[2]|data[3]<<8))
    if len(str)==8:
      return
    print('     ',end='')
    for i in range(0,line_len):
      self.clr.print_yellow_text('{:02d} '.format(i),end='')
    data=data[4:]
    address=0
    for index,item in enumerate(data):
      if index%line_len==0:
        print('\n{:04d}:'.format(address),end='')
        address=address+line_len
      self.clr.print_blue_text('{:02X} '.format(item),end='')
    print('')

  def readPackrat(self):
    raw = self.getDatabyCmd(cmdCode='02', statusCode='01')
    B1 = raw[18]
    B2 = raw[19]
    B3 = raw[20]
    B4 = raw[21]
    
    packrat = B4 << 24 | B3 << 16 | B2 << 8 | B1
    return packrat

  def sendCmd(self,cmd,needResponse=False,response=None):
    retry=5
    ret=''
    if cmd!='':
      ret=self.usbWrite('{} {}'.format(self.prefix,cmd))
      if needResponse:
        while True:
          ret=self.getResponse()
          if response==None:
            break
          if ret[2:4]=='00' or ret[2:4]==response:
            break
          else:
            print('Header={}, need retry'.format(ret[0:8]))
            retry=retry-1
            if retry:
              continue
            else:
              break
      else:
        r = re.search('"A5\S+"',ret)          
        if r == None:
          return None
        else:
          r = r.group().strip()
          ret = re.sub('"','',r)
    self.printPacket(ret)
    return ret
    
  def readMsg(self):
    str1=''
    str2=''
    # ===== Get data-length =====
    r = self.usbWrite('{} rd=4'.format(self.prefix))
    # ===== check and make sure startCode is correct =====
    r = re.search('"A5\S+"',r)          
    if r == None:
      return None
    else:
      r = r.group().strip()
      r = re.sub('"','',r)
      if r=='A5000000':
        return r
    str1=r
    str2=''
    length = 3 + (int(r[4:6],16)|int(r[6:],16)<< 8)
    if length>3:
      # ===== Get real data =====
      r = self.usbWrite('{} rd={}'.format(self.prefix,length))
      try:
        # A503 = Continues Read
        data = re.search('"A503\S+5A"',r).group().strip()

        # Strip " string at begin and end, then remove A5(startCode)、03(ContinueReadCode)、5A(endCode)
        data = re.sub('"','',data)[4:-2]
        str2=data     
      except:
        assert False,"ERROR: can't get complete data : {}".format(r)
    return str1+str2
  
  def getResponse(self):
    retry=5
    while True:
      r = self.readMsg()
      if r=='A5000000':
        retry=retry-1
        if retry:
          time.sleep(0.01)
          continue
        else:
          break
      elif r==None:
        continue
      else:
        break
    return r

  def getDatabyCmd(self,cmdCode, statusCode):
    msg='A5{}'.format(statusCode)
    self.usbWrite('{} wr={}0000'.format(self.prefix,cmdCode))
    while True:
      r = self.readMsg()
      if r=='A5000000':
        time.sleep(0.01)
        continue
      elif r==None:
        continue
      elif msg==r[0:4]:
        break
    #print(r)
    r=r[8:]
    data = [int(r[index:index+2],16) for index in range(0,len(r),2)]
    return data
  
  def getStaticCfg(self):
    return self.getDatabyCmd(cmdCode='21',statusCode='01')

  def clearCmd(self):
    while True:
      r = self.usbWrite('{} rd=4'.format(self.prefix))
      if self.debug:
        print(r)
      status = re.search('"A5000000"',r)
      if status == None:
        pass
      else:
        break

  def check_uboot(self, r):
    r = r.split("\"")[3]
    """
    query_base = r[:2]
    command_base = r[2:4]
    control_base = r[4:6]
    data_base = r[6:8]
    """
    fn_number = r[-4:]
    if fn_number == UBL_FN_NUMBER:
      return 1
    else:
      return 0

  def Quit(self):
    if self.interface=='i2c' or self.interface=='spi':
      self.PowerOff()
      if self.usb is not None:
        usb.util.dispose_resources(self.usb)
    else:
      self.socket.close()

  def download_disp_config(self, image_info):
    chunk_size = 255
    size = ((image_info.disp_config_size+3)&0xfffffffc)+4
    chunks= int(size/chunk_size)
    image_info.disp_config_data.insert(0,HDL_DISPLAY_CONFIG_TO_RAM)
    image_info.disp_config_data.insert(0,hdl_version)
    image_info.disp_config_data.insert(0,size>>8&0xff)
    image_info.disp_config_data.insert(0,size&0xff)

    for idx in list(range(chunks)):
      data = "".join("{:02X}".format(p) for p in image_info.disp_config_data[idx*chunk_size:idx*chunk_size+chunk_size])
      if idx == 0:
        data=CMD_DOWNLOAD_CONFIG+data
      else:
        data=CMD_CONTINUE_WRITE+data
      print(self.usbWrite("target=0 raw wr={}".format(data)))

    data = "".join("{:02X}".format(p) for p in image_info.disp_config_data[chunks*chunk_size:])
    data=CMD_CONTINUE_WRITE+data
    print(self.usbWrite("target=0 raw wr={}".format(data)))

  def download_app_config(self, image_info):
    chunk_size = 255
    size = ((image_info.app_config_size+3)&0xfffffffc)+4
    payload_length = size -2
    chunks= int(size/chunk_size)
    image_info.app_config_data.insert(0,HDL_TOUCH_CONFIG_TO_PMEM)
    image_info.app_config_data.insert(0,hdl_version)
    image_info.app_config_data.insert(0,payload_length>>8&0xff)
    image_info.app_config_data.insert(0,payload_length&0xff)

    for idx in list(range(chunks)):
      data = "".join("{:02X}".format(p) for p in image_info.app_config_data[idx*chunk_size:idx*chunk_size+chunk_size])
      if idx == 0:
        data=CMD_DOWNLOAD_CONFIG+data
      else:
        data=CMD_CONTINUE_WRITE+data
      print(self.usbWrite("target=0 raw wr={}".format(data)))

    data = "".join("{:02X}".format(p) for p in image_info.app_config_data[chunks*chunk_size:])
    data=CMD_CONTINUE_WRITE+data
    print(self.usbWrite("target=0 raw wr={}".format(data)))

  def download_fw(self, image_info):
    print("hello1", self.usbWrite('target=0 hdl crc at=0 size={}'.format(image_info.app_firmware_size)))
    print(datetime.datetime.now().strftime('%H:%M:%S.%f'))
    chunk_size = 512
    chunks= int(image_info.app_firmware_size / chunk_size)

    for idx in list(range(chunks)):
      data = "".join("{:02X}".format(p) for p in image_info.app_firmware_data[idx*chunk_size:idx*chunk_size+chunk_size])
      r=self.usbWrite("target=0 hdl send idx={} data={}".format(idx,data))

    data = "".join("{:02X}".format(p) for p in image_info.app_firmware_data[chunks*chunk_size:])
    r=self.usbWrite("target=0 hdl send idx={} data={}".format(idx+1, data))
    print(datetime.datetime.now().strftime('%H:%M:%S.%f'))
    print("hello", self.Config(0))
    time.sleep(0.05)
    print("world", self.usbWrite('target=0 asic reset level=low output=open-drain time=1000'))
    print("hi", self.usbWrite('target=0 raw wr=001804'))
    print("hih", self.usbWrite('target=0 raw wr=001c download at=0 size=72912'))
    time.sleep(0.5)
    print("h0", self.usbWrite('target=0 raw waitOn=attnLow rd=4'))
    print("h01", self.usbWrite('target=0 raw waitOn=attnLow rd=27'))

    """
    struct firmware_status{
        uint16_t invalid_static_config:1;
        uint16_t need_disp_config:1;
        uint16_t need_app_config:1;
        uint16_t has_frame_crc:1;
        uint16_t has_bumpiness:1;
        uint16_t has_lot:1;
        uint16_t has_displayConfigMemType:2;
        uint16_t has_uncompressed_image:1;
        uint16_t reserved:7;
    } __packed;
    """
    #get fw status
    print("h00", self.usbWrite('target=0 raw waitOn=attnLow rd=4'))
    r=self.usbWrite('target=0 raw waitOn=attnLow rd=5')
    print(r)
    r=string_to_uint(r.split("\"")[1][4:6])
    print("config data = {:02X}".format(r))
    time.sleep(0.01)
    if r>>1&1:
      self.download_disp_config(image_info)
    elif r>>2&1:
      self.download_app_config(image_info)
    time.sleep(0.2)
    print("h000", self.usbWrite('target=0 raw waitOn=attnLow rd=4'))
    print("h001", self.usbWrite('target=0 raw waitOn=attnLow rd=5'))
     

def le4_to_uint(m):
    return (m[0] | m[1] << 8 | m[2] << 16 | m[3] << 24)

def list_to_string(l):
    return "".join(chr(p) for p in l)

def string_to_uint(s):
    value = 0
    #reverse string
    s=s[::-1]
    for i, p in enumerate(s):
        if p >= "0" and p <= "9":
            value += (ord(p) - 48) * pow(16, i)
        elif p >= "A" and p <= "F":
            value += (ord(p) - 55) * pow(16, i)
        else:
            print("Invalid number")

    return value

def select_fw():
    return g.fileopenbox(msg='{} FW Image...'.format("Select"),default="*.img", filetypes=['*.img'])

def parse_fw(filename, image_info):
    err = 0
    offset = 0
    num_of_areas = 0

    try:
        f = open(filename, "rb")
        image = list(bytearray(f.read()))

        m = image[:4]
        offset += 4
        magic_value = le4_to_uint(m)
        if magic_value != IMAGE_FILE_MAGIC_VALUE:
            err = 1
            print("Image file magic value mismatch: %X, %X" %(magic_value, IMAGE_FILE_MAGIC_VALUE))
            return err

        m = image[offset:offset+4]
        offset += 4
        num_of_areas = le4_to_uint(m)

        """
        struct area_descriptor {
            magic_value[4];
            uint8_t id_string[16];
            uint8_t flags[4];
            uint8_t flash_addr_words[4];
            uint8_t length[4];
            uint8_t checksum[4];
        }; 
        """
        desc_size = 4 + 16 + 4 + 4 + 4 + 4
        for idx in list(range(num_of_areas)):
            addr = le4_to_uint(image[offset : offset + 4])
            offset += 4
            descriptor = image[addr : addr + desc_size]
            magic_value = le4_to_uint(descriptor[:4])
            if (magic_value != FLASH_AREA_MAGIC_VALUE and idx < 4):
                print("Flash area magic value mismatch, id = %d" %(idx))
                continue

            id_string = list_to_string(descriptor[4 : 4 + 16]).strip()
            flags = descriptor[20 : 20 + 4]
            flash_addr = le4_to_uint(descriptor[24 : 24 + 4]) * 2
            length = le4_to_uint(descriptor[28 : 28 + 4])
            checksum = le4_to_uint(descriptor[32 : 32 + 4])
            content = image[addr + desc_size : addr + desc_size + length]
            print("checksum = 0x%X" % checksum)

            if id_string == BOOT_CONFIG_ID:
                if checksum != z.crc32(bytearray(content), 0):
                    print("Boot config checksum error")
                    err = 1
                    return err

                image_info.boot_config_size = length;
                image_info.boot_config_data = content;
                image_info.boot_config_flash_addr = flash_addr;
                print("Boot config size = %d" % length);
                print("Boot config flash address = 0x%08x" % flash_addr);

            elif id_string == F35_APP_CODE_ID: 
                if checksum != z.crc32(bytearray(content), 0):
                    print("Application firmware checksum error")
                    err = 1
                    return err

                image_info.app_firmware_size = length;
                image_info.app_firmware_data = content;
                image_info.app_firmware_flash_addr = flash_addr;
                print("Application firmware size = %d" % length);
                print("Application firmware flash address = 0x%08x" % flash_addr);
            elif id_string == APP_CONFIG_ID: 
                if checksum != z.crc32(bytearray(content), 0):
                    print("Application config checksum error")
                    err = 1
                    return err

                image_info.app_config_size = length;
                image_info.app_config_data = content;
                image_info.app_config_flash_addr = flash_addr;
                print("Application config size = %d" % length);
                print("Application config flash address = 0x%08x" % flash_addr);
            elif id_string == DISP_CONFIG_ID: 
                if checksum != z.crc32(bytearray(content), 0):
                    print("Display config checksum error")
                    err = 1
                    return err

                image_info.disp_config_size = length;
                image_info.disp_config_data = content;
                image_info.disp_config_flash_addr = flash_addr;
                print("Display config size = %d" % length);
                print("Display config flash address = 0x%08x" % flash_addr);

    except Exception as e:
        print(e)
    finally:
        f.close()

def main(argv):
  if len(argv)==1:
    interface='spi'
  else:
    if argv[1].lower()=='i2c':
      interface='i2c'
    elif argv[1].lower()=='spi':
      interface='spi'
    else:
      interface='localhost'
  cm2=comm2(ip=interface,vddh=VDDH_VOLTAGE,vddio=VDDIO_VOLTAGE)
  if cm2.connected==False or cm2.err:
    return
  #os.system("pause")
  if cm2.tcmDevice==False:
    if cm2.current_mode == "HDL":
      ans = input("HDL mode detected, HDL? (y/n,Enter for yes):")
      if (ans != "" and (ans.startswith("n") or ans.startwiths("N"))):
          cm2.Quit()
          return
      else:
        image = image_info()
        filename=select_fw()
        if filename is None:
          return
        else:
          err=parse_fw(filename,image)
        cm2.download_fw(image)
    elif cm2.current_mode == "UBL":
      print("FW mode:UBL")
      cm2.Quit()
      return
    else:
      print("FW mode:UNKNOWN")
      cm2.Quit()
      return
  else:
    print("FW mode:APP")
  return
  pr=cm2.readPackrat()
  print('Packrat={}'.format(pr))
  while True:
    str=input("Input cmd here:")
    if str:
      if '=' in str:
        cmds=str.split('=')
        cmd=cmds[0].strip()
        data=cmds[1].strip()
        if cmd=='rd':
          cm2.sendCmd(str.strip())
        else:
          if len(data)<3:
            str='wr='+data+'0000'
          else:
            id=data[0:2]
            data=data[2:]
            size=len(data)//2
            str='wr={}{:02X}{:02X}{}'.format(id,size%256,size//256,data)
          print(str)
          if cmd=='cmd':
            cm2.sendCmd(str.strip(),True,'01')
          elif cmd=='wr':
            cm2.sendCmd(str.strip(),True)
          elif cmd=='wrnr':
            cm2.sendCmd(str.strip())          
      else:
        if str=='quit':
          break
        elif str=='run':
          cnt=0;
          while True:
            cm2.printPacket(cm2.readMsg())
            time.sleep(0.003)
            cnt=cnt+1
            if msvcrt.kbhit():
              msvcrt.getch()
              break
        elif str=='check':
          cm2.printPacket(cm2.readMsg())
      
  cm2.Quit()

if __name__ == '__main__':
  print(USAGE)
  main(sys.argv)
