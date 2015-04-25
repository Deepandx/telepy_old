# -*- coding: utf-8 -*-
# Deal with py2 and py3 differences
try: # this only works in py2.7
    import configparser
except ImportError:
    import ConfigParser as configparser
from mtproto.Session import Session
from layers.Crypt import CryptLayer
from layers.MessageHandler import MessageHandler
from layers.Transport import TCPTransportLayer
from layers.Session import SessionLayer
from time import sleep
from mtproto import TL

config = configparser.ConfigParser()
# Check if credentials is correctly loaded (when it doesn't read anything it returns [])
if not config.read('credentials'):
    print("File 'credentials' seems to not exist.")
    exit(-1)
ip = config.get('App data', 'ip_address')
port = config.getint('App data', 'port')


tcptransport = TCPTransportLayer(ip, port)
cryptlayer = CryptLayer(underlying_layer=tcptransport)
messagehandler = MessageHandler(underlying_layer=cryptlayer)
session = SessionLayer(underlying_layer=messagehandler)