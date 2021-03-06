# from urllib.parse import quote
import sys
# import ttk
import requests
import json
import time
from queue import Queue
from threading import Thread

import tkinter as tk
from ttkHyperlinkLabel import HyperlinkLabel
import myNotebook as nb

from config import appname, applongname, appversion, config
import companion
import plug
import sys
import codecs

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
# sys.stdout = codecs.getwriter('utf8')(sys.stdout)
# sys.stderr = codecs.getwriter('utf8')(sys.stderr)

this = sys.modules[__name__]
this.session = requests.Session()
this.queue = Queue()
this.msg = " "
this.cmdr = None
this.defaultApiHost = 'https://beta.edscc.net/api/edmc'

_TIMEOUT = 20
_EDSCC_LOG = True
_EDSCC_LOG_LEVEL = 2


def edscc_log(msg, level=1):
    if (_EDSCC_LOG and _EDSCC_LOG_LEVEL >= level):
        print('EDSCC: %s - %s' % (time.asctime(), msg))


def plugin_start3(plugin_dir):
    edscc_log('Start Plugin', 0)
    this.thread = Thread(target=worker, name='EDSCC Worker')
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

    if config.getint('edscc_out') and not is_beta and credentials(this.cmdr):
        form_data = {
            'commander': data['commander'],
            'lastSystem': data['lastSystem'],
            'ship': data['ship']
        }
        this.queue.put((this.cmdr, 'commander', form_data))
        edscc_log('Added cmdr_data to queue')


def journal_entry(cmdr, is_beta, system, station, entry, state):
    entry['timestamp'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    if config.getint('edscc_out') and not is_beta and credentials(cmdr):
        edscc_log('New Event: %s' % entry['event'], 2)
        form_data = []

        if entry['event'] in ['Statistics', 'LoadGame', 'Commander', 'Rank', 'Progress', 'Statistics', 'Docked',
                              'Undocked', 'Bounty', 'CapShipBond', 'FactionKillBond', 'RedeemVoucher',
                              'MultiSellExplorationData', 'SellExplorationData', 'SAAScanComplete', 'MarketBuy',
                              'MarketSell', 'MiningRefined', 'CommunityGoalReward', 'MissionCompleted', 'CommitCrime',
                              'SquadronStartup', 'AppliedToSquadron', 'LeftSquadron', 'RedeemVoucher']:
            form_data.append(entry)

        if form_data:
            this.queue.put((cmdr, 'journal', form_data))
            edscc_log("Added '%s' event to queue" % entry['event'], 2)


def plugin_prefs(parent, cmdr, is_beta):
    PADX = 10
    BUTTONX = 12  # indent Checkbuttons and Radiobuttons
    PADY = 2  # close spacing

    frame = nb.Frame(parent)
    frame.columnconfigure(1, weight=1)

    HyperlinkLabel(frame, text='EDSCC', background=nb.Label().cget('background'), url='https://beta.edscc.net/',
                   underline=True).grid(columnspan=2, padx=PADX, sticky=tk.W)  # Don't translate
    this.log = tk.IntVar(value=config.getint('edscc_out') and 1)
    this.log_button = nb.Checkbutton(frame, text=_('Send flight log and Cmdr status to EDSCC'), variable=this.log,
                                     command=prefsvarchanged)
    this.log_button.grid(columnspan=2, padx=BUTTONX, pady=(5, 0), sticky=tk.W)

    nb.Label(frame).grid(sticky=tk.W)  # big spacer
    this.label = HyperlinkLabel(frame, text=_('EDSCC credentials'), background=nb.Label().cget('background'),
                                url='https://beta.edscc.net/settings-api',
                                underline=True)  # Section heading in settings
    this.label.grid(columnspan=2, padx=PADX, sticky=tk.W)

    this.apikey_label = nb.Label(frame, text=_('API Key'))  # EDSCC setting
    this.apikey_label.grid(row=12, padx=PADX, sticky=tk.W)
    this.apikey = nb.Entry(frame)
    this.apikey.grid(row=12, column=1, padx=PADX, pady=PADY, sticky=tk.EW)

    this.edscchost_label = nb.Label(frame, text=_('EDSCC API Server'))  # EDSCC setting
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
    this.label['state'] = this.apikey_label['state'] = this.apikey['state'] = this.edscchost_label['state'] = \
        this.edscchost['state'] = cmdr and not is_beta and this.log.get() and tk.NORMAL or tk.DISABLED


def prefsvarchanged():
    this.label['state'] = this.apikey_label['state'] = this.apikey['state'] = this.edscchost_label['state'] = \
        this.edscchost['state'] = this.log.get() and this.log_button['state'] or tk.DISABLED


def prefs_changed(cmdr, is_beta):
    config.set('edscc_out', this.log.get())

    if cmdr and not is_beta:
        this.cmdr = cmdr
        this.FID = None
        cmdrs = config.get('edscc_cmdrs') or []
        apikeys = config.get('edscc_apikeys') or []
        edscchosts = config.get('edscc_edscchosts') or []
        edscc_log('Current Configs: %s %s %s %s' % (cmdrs, cmdrs, apikeys, edscchosts), 2)
        if cmdr in cmdrs:
            idx = cmdrs.index(cmdr)
            apikeys.extend([''] * (1 + idx - len(apikeys)))
            apikeys[idx] = this.apikey.get().strip()
            edscchosts.extend([''] * (1 + idx - len(edscchosts)))
            edscchosts[idx] = this.edscchost.get().strip()
        else:
            config.set('edscc_cmdrs', cmdrs + [cmdr])
            apikeys.append(this.apikey.get().strip())
            edscchosts.append(this.edscchost.get().strip())
        config.set('edscc_apikeys', apikeys)
        config.set('edscc_edscchosts', edscchosts)
        edscc_log('Configs saved: %s %s' % (apikeys, edscchosts), 2)


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
            return  # Closing
        else:
            (cmdr, data_type, form_data) = item
            (apiKey) = credentials(cmdr)
            (edscchost) = apihost(cmdr)

        edscc_log('Sending event to EDSCC', 1)
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
                    edscc_log('Event received. Post Successful.', 1)
                    this.msg = 'EDSCC Post Succeeded.'
                else:
                    edscc_log('API Post Fail: [' + str(r.status_code) + '] ' + reply['message'], 1)
                    edscc_log('JSON dump: %s' % json.dumps(data, ident=2, separators=(',', ': ')), 2)
                    this.msg = 'EDSCC Post Failed.'

                if this.msg:
                    # Log fatal errors
                    plug.show_error(_(this.msg))
                break
            except:
                if __debug__: print_exc()
                retrying += 1
                edscc_log('in exception, retrying %s' % retrying)
        else:
            plug.show_error(_("Error: Can't connect to EDSCC"))
