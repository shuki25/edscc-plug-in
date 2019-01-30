import urllib2
import sys
import ttk
import requests
import json
import time
from Queue import Queue
from threading import Thread

import Tkinter as tk
from ttkHyperlinkLabel import HyperlinkLabel
import myNotebook as nb

from config import appname, applongname, appversion, config
import companion
import plug

this = sys.modules[__name__]
this.session = requests.Session()
this.queue = Queue()
this.msg = " "
this.cmdr = None
this.defaultApiHost = 'https://edscc.ddns.net/api/edmc'

_TIMEOUT = 20

def plugin_start():
    this.thread = Thread(target = worker, name = 'EDSCC Worker')
    this.thread.daemon = True
    this.thread.start()
    return 'EDSCC'

def plugin_stop():
    # Signal thread to close and wait for it
    this.queue.put(None)
    this.thread.join()
    this.thread = None

def cmdr_data(data, is_beta):
    
    this.cmdr = data['commander']['name']

    if config.getint('edsm_out') and not is_beta and credentials(this.cmdr):
        form_data = {
            'commander' : data['commander'],
            'lastSystem' : data['lastSystem'],
            'ship' : data['ship']
        }       
        this.queue.put((this.cmdr, 'commander', form_data))
        print 'Added cmdr_data to queue'

def journal_entry(cmdr, is_beta, system, station, entry, state):
    print 'in journal_entry'
    entry['timestamp'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    if config.getint('edsm_out') and not is_beta and credentials(cmdr):
        print 'event: %s' % entry['event']
        form_data = []

        if entry['event'] in ['Statistics', 'LoadGame', 'Commander', 'Rank', 'Progress', 'Bounty', 'CapShipBond', 'FactionKillBond', 'MultiSellExplorationData', 'SellExplorationData', 'SAAScanComplete', 'MarketBuy', 'MarketSell', 'MiningRefined', 'CommunityGoalReward', 'MissionCompleted', 'CommitCrime']:
            form_data.append(entry)

        if form_data:
            this.queue.put((cmdr, 'journal', form_data))
            print 'Added journal_entry to queue'

def plugin_prefs(parent, cmdr, is_beta):

    PADX = 10
    BUTTONX = 12        # indent Checkbuttons and Radiobuttons
    PADY = 2            # close spacing

    frame = nb.Frame(parent)
    frame.columnconfigure(1, weight=1)

    HyperlinkLabel(frame, text='EDSCC', background=nb.Label().cget('background'), url='https://edscc.ddns.net/', underline=True).grid(columnspan=2, padx=PADX, sticky=tk.W)     # Don't translate
    this.log = tk.IntVar(value = config.getint('edscc_out') and 1)
    this.log_button = nb.Checkbutton(frame, text=_('Send flight log and Cmdr status to EDSCC'), variable=this.log, command=prefsvarchanged)
    this.log_button.grid(columnspan=2, padx=BUTTONX, pady=(5,0), sticky=tk.W)

    nb.Label(frame).grid(sticky=tk.W)   # big spacer 
    this.label = HyperlinkLabel(frame, text=_('EDSCC credentials'), background=nb.Label().cget('background'), url='https://edscc.ddns.net/settings-api', underline=True)        # Section heading in settings
    this.label.grid(columnspan=2, padx=PADX, sticky=tk.W)

    this.apikey_label = nb.Label(frame, text=_('API Key'))      # EDSM setting
    this.apikey_label.grid(row=12, padx=PADX, sticky=tk.W)
    this.apikey = nb.Entry(frame)
    this.apikey.grid(row=12, column=1, padx=PADX, pady=PADY, sticky=tk.EW)

    this.edscchost_label = nb.Label(frame, text=_('EDSCC API Server'))      # EDSM setting
    this.edscchost_label.grid(row=14, padx=PADX, sticky=tk.W)
    this.edscchost = nb.Entry(frame)
    this.edscchost.grid(row=14, column=1, padx=PADX, pady=PADY, sticky=tk.EW)

    prefs_cmdr_changed(cmdr, is_beta)

    return frame

def prefs_cmdr_changed(cmdr, is_beta):
    this.log_button['state'] = cmdr and not is_beta and tk.NORMAL or tk.DISABLED
    this.apikey['state'] = tk.NORMAL
    this.edscchost['state'] = tk.NORMAL
    this.apikey.delete(0, tk.END)
    this.edscchost.delete(0, tk.END)
    if cmdr:
        cred = credentials(cmdr)
        edscchost = apihost(cmdr)
        if cred:
            this.apikey.insert(0, cred)
            this.edscchost.insert(0, edscchost)
    this.label['state'] = this.apikey_label['state'] = this.apikey['state'] = this.edscchost_label['state'] = this.edscchost['state'] = cmdr and not is_beta and this.log.get() and tk.NORMAL or tk.DISABLED

def prefsvarchanged():
    this.label['state'] = this.apikey_label['state'] = this.apikey['state'] = this.edscchost_label['state'] = this.edscchost['state'] = this.log.get() and this.log_button['state'] or tk.DISABLED

def prefs_changed(cmdr, is_beta):
    changed = config.getint('edscc_out') != this.log.get()
    config.set('edscc_out', this.log.get())

    if cmdr and not is_beta:
        this.cmdr = cmdr
        this.FID = None
        cmdrs = config.get('edscc_cmdrs') or []
        apikeys = config.get('edscc_apikeys') or []
        edscchosts = config.get('edscc_edscchosts') or []
        if cmdr in cmdrs:
            idx = cmdrs.index(cmdr)
            apikeys.extend([''] * (1 + idx - len(apikeys)))
            changed |= (apikeys[idx] != this.apikey.get().strip())
            apikeys[idx] = this.apikey.get().strip()
            edscchosts.extend([''] * (1 + idx - len(apikeys)))
            changed |= (edscchosts[idx] != this.edscchost.get().strip())
            edscchosts[idx] = this.edscchost.get().strip()
        else:
            config.set('edscc_cmdrs', cmdrs + [cmdr])
            changed = True
            apikeys.append(this.apikey.get().strip())
            edscchosts.append(this.edscchost.get().strip())
        config.set('edscc_apikeys', apikeys)
        config.set('edscc_edscchosts', edscchosts)

def credentials(cmdr):
    # Credentials for cmdr
    if not cmdr:
        return None

    cmdrs = config.get('edscc_cmdrs') or []
    if cmdr in cmdrs and config.get('edscc_apikeys'):
        return config.get('edscc_apikeys')[cmdrs.index(cmdr)]
    else:
        return None

def apihost(cmdr):
    # Credentials for cmdr
    if not cmdr:
        return None

    cmdrs = config.get('edscc_cmdrs') or []
    
    if cmdr in cmdrs and config.get('edscc_edscchosts'):
        host = config.get('edscc_edscchosts')[cmdrs.index(cmdr)].strip() or this.defaultApiHost
        return host
    else:
        return this.defaultApiHost

# Worker thread
def worker():
    while True:
        item = this.queue.get()
        if not item:
            return	# Closing
        else:
            (cmdr, data_type, form_data) = item
            (apiKey) = credentials(cmdr)
            (edscchost) = apihost(cmdr)

        retrying = 0

        while retrying < 3:
            try:
                data = {
                    'fromSoftware': applongname,
                    'fromSoftwareVersion': appversion,
                    'data': json.dumps(form_data, ensure_ascii=False).encode('utf-8'),
                    'data_type': data_type
                }
                header = {
                    'x-api-key': apiKey
                }
                r = this.session.post(edscchost, data=data, timeout=_TIMEOUT, headers=header)
                this.msg = ''
                reply = r.json()
                if r.status_code == 200:
                    this.msg = 'EDSCC Post Succeeded'
                else:
                    print ('EDSCC API Post Fail: [' + str(r.status_code) + '] ' + reply['message'])
                    this.msg = 'EDSCC Post Failed'
                    
                if this.msg:
                    # Log fatal errors
                    print this.msg
                    plug.show_error(_(this.msg))

                break
            except:
                if __debug__: print_exc()
                retrying += 1
                print 'in exception, retrying %s' % retrying
        else:
            plug.show_error(_("Error: Can't connect to EDSCC"))
